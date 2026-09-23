"""Persistent OpenCADStudio MCP stdio client for automation harnesses.

No mutation is replayed after a lost reply. An unresolved operation is an error
that requires reconciliation against the same session and request_id.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import queue
import subprocess
import threading
import time
from typing import Any, Sequence


MODERN = "2026-07-28"
META = {
    "io.modelcontextprotocol/protocolVersion": MODERN,
    "io.modelcontextprotocol/clientInfo": {"name": "ocs-automation", "version": "1"},
    "io.modelcontextprotocol/clientCapabilities": {
        "extensions": {"io.modelcontextprotocol/tasks": {}}
    },
}


class ProtocolError(RuntimeError):
    pass


class RpcTimeout(ProtocolError):
    pass


class ToolError(ProtocolError):
    """The server returned an explicit tool failure."""


class UncertainMutation(ProtocolError):
    pass


class Client:
    def __init__(self, server: Path, *, timeout: float = 15.0, max_pending: int = 64,
                 command: Sequence[str] | None = None) -> None:
        self.process = subprocess.Popen(
            list(command) if command is not None else [str(server), "--mcp"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", bufsize=1,
        )
        self.timeout = timeout
        self.max_pending = max_pending
        self.serial = 0
        self.rpc_calls = 0
        self.tool_calls = 0
        self.tasks = 0
        self.request_bytes = 0
        self.response_bytes = 0
        self._pending: dict[int, queue.Queue] = {}
        self._lock = threading.Lock()
        self._fatal: str | None = None
        self._mutations: dict[str, tuple[str, dict | None]] = {}
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _fail_all(self, message: str) -> None:
        with self._lock:
            self._fatal = message
            for slot in self._pending.values():
                slot.put(ProtocolError(message))
            self._pending.clear()

    def _read_stdout(self) -> None:
        assert self.process.stdout
        try:
            for line in self.process.stdout:
                self.response_bytes += len(line.encode("utf-8"))
                try:
                    reply = json.loads(line)
                except (ValueError, TypeError) as exc:
                    raise ProtocolError("Invalid JSON on MCP stdout") from exc
                if not isinstance(reply, dict) or reply.get("jsonrpc") != "2.0":
                    raise ProtocolError("Invalid JSON-RPC response on MCP stdout")
                if "id" not in reply:
                    continue  # Server notification.
                with self._lock:
                    slot = self._pending.pop(reply["id"], None)
                if slot is None:
                    # A late reply to a timed-out call is not another call's result.
                    continue
                slot.put(reply)
            self._fail_all("MCP stdout closed")
        except (ProtocolError, OSError, TypeError) as exc:
            self._fail_all(str(exc))

    def _drain_stderr(self) -> None:
        assert self.process.stderr
        for _ in self.process.stderr:
            pass

    def rpc(self, method: str, params: dict, *, timeout: float | None = None) -> dict:
        assert self.process.stdin
        slot: queue.Queue = queue.Queue(maxsize=1)
        with self._lock:
            if self._fatal:
                raise ProtocolError(self._fatal)
            if len(self._pending) >= self.max_pending:
                raise ProtocolError("MCP request queue full")
            self.serial += 1
            serial = self.serial
            payload = {"jsonrpc": "2.0", "id": serial, "method": method, "params": params}
            wire = json.dumps(payload, separators=(",", ":")) + "\n"
            self._pending[serial] = slot
            try:
                self.process.stdin.write(wire)
                self.process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._pending.pop(serial, None)
                raise ProtocolError("MCP write failed") from exc
            self.request_bytes += len(wire.encode("utf-8"))
            self.rpc_calls += 1
        try:
            reply = slot.get(timeout=self.timeout if timeout is None else timeout)
        except queue.Empty as exc:
            with self._lock:
                self._pending.pop(serial, None)
            raise RpcTimeout(f"MCP {method} timed out (rpc id {serial})") from exc
        if isinstance(reply, Exception):
            raise reply
        if reply.get("id") != serial:
            raise ProtocolError("MCP reply ID mismatch")
        if "error" in reply:
            raise ProtocolError(str(reply["error"]))
        if "result" not in reply:
            raise ProtocolError("MCP response has no result")
        return reply["result"]

    def handshake(self) -> dict:
        discovery = self.rpc("server/discover", {"_meta": META})
        if MODERN not in discovery.get("supportedVersions", []):
            raise ProtocolError("Server does not support the required MCP version")
        extensions = discovery.get("capabilities", {}).get("extensions", {})
        if "io.modelcontextprotocol/tasks" not in extensions:
            raise ProtocolError("Server does not support MCP tasks")
        return discovery

    def tool(self, name: str, arguments: dict, *, deadline: float | None = None) -> dict:
        if name == "ocs_execute":
            return self.mutate(arguments["ocs_session_id"], arguments["request"],
                               deadline=deadline,
                               **{key: value for key, value in arguments.items()
                                  if key not in {"ocs_session_id", "request"}})
        return self._tool_raw(name, arguments, deadline=deadline)

    def _tool_raw(self, name: str, arguments: dict, *, deadline: float | None = None) -> dict:
        if deadline is None:
            deadline = time.monotonic() + max(self.timeout, 90.0)
        self.tool_calls += 1
        result = self.rpc("tools/call", {"name": name, "arguments": arguments, "_meta": META},
                          timeout=min(self.timeout, self._remaining(deadline)))
        while result.get("resultType") == "task":
            self.tasks += 1
            task_id = result["taskId"]
            interval = max(0.01, min(result.get("pollIntervalMs", 250) / 1000, 1.0))
            while True:
                remaining = self._remaining(deadline)
                time.sleep(min(interval, remaining) if remaining is not None else interval)
                task = self.rpc("tasks/get", {"taskId": task_id, "_meta": META},
                                timeout=min(self.timeout, self._remaining(deadline)))
                if task["status"] in {"failed", "cancelled"}:
                    raise ProtocolError(f"MCP task {task_id}: {task['status']}")
                if task["status"] == "completed":
                    result = task["result"]
                    break
        structured = result.get("structuredContent")
        if structured is None or structured.get("ok") is False or result.get("isError"):
            raise ToolError(str(structured or result))
        return structured

    @staticmethod
    def _remaining(deadline: float | None) -> float | None:
        if deadline is None:
            return None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RpcTimeout("MCP operation deadline exceeded")
        return remaining

    def ready_session(self, *, session_id: str | None = None,
                      launch_if_none: bool = False, timeout: float = 90.0) -> dict:
        deadline = time.monotonic() + timeout
        launched = False
        interval = 0.1
        while True:
            try:
                sessions = self.tool("ocs_sessions", {"launch_if_none": launch_if_none and not launched},
                                     deadline=deadline)["result"]
                launched = True
                if session_id is None and len(sessions) != 1:
                    raise ProtocolError(f"Expected one session, found {len(sessions)}; specify session_id")
                matching = [s for s in sessions if s["session_id"] == session_id] if session_id else sessions
                if len(matching) != 1:
                    raise ProtocolError("Selected session is absent or ambiguous")
                return matching[0]
            except ProtocolError as exc:
                if "still starting" not in str(exc):
                    raise
                launched = True  # Never launch a second GUI during startup.
                remaining = self._remaining(deadline)
                time.sleep(min(interval, remaining))
                interval = min(interval * 1.5, 1.0)

    def mutate(self, session_id: str, request: dict, *, deadline: float | None = None,
               **options: Any) -> dict:
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("Mutation requires a stable request_id")
        digest = hashlib.sha256(json.dumps([session_id, request, options], sort_keys=True).encode()).hexdigest()
        previous = self._mutations.get(request_id)
        if previous:
            if previous[0] != digest:
                raise ValueError("request_id reused for different mutation")
            if previous[1] is not None:
                return previous[1]
            return self.recover(session_id, request_id, deadline=deadline)
        self._mutations[request_id] = (digest, None)
        try:
            result = self._tool_raw("ocs_execute", {"ocs_session_id": session_id, "request": request, **options},
                                    deadline=deadline)
        except ToolError:
            raise
        except (RpcTimeout, ProtocolError) as exc:
            # A transport failure may occur after the editor commits. Query only.
            try:
                return self.recover(session_id, request_id, deadline=deadline)
            except (RpcTimeout, ProtocolError) as recovery_exc:
                raise UncertainMutation(f"{request_id}: outcome unknown; {recovery_exc}") from exc
        self._mutations[request_id] = (digest, result)
        return result

    def recover(self, session_id: str, request_id: str, *, deadline: float | None = None) -> dict:
        operation = self.tool("ocs_read", {"ocs_session_id": session_id, "op": "operation",
                                            "parameters": {"request_id": request_id}}, deadline=deadline)
        if operation.get("status") in {"accepted", "running", "waiting_input"}:
            raise UncertainMutation(f"{request_id}: operation not complete; preserve progress")
        if operation.get("request_id") != request_id:
            raise UncertainMutation(f"{request_id}: operation identity not confirmed")
        if operation.get("ok") is not True or operation.get("status") != "completed":
            raise UncertainMutation(f"{request_id}: operation did not complete successfully")
        previous = self._mutations.get(request_id)
        if previous:
            self._mutations[request_id] = (previous[0], operation)
        return operation

    def close(self) -> None:
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            code = self.process.wait(timeout=5)
        except subprocess.TimeoutExpired as exc:
            raise ProtocolError("MCP process did not exit after stdin closed") from exc
        if self.process.stdout:
            self.process.stdout.close()
        if self.process.stderr:
            self.process.stderr.close()
        if code != 0:
            raise ProtocolError(f"MCP exited {code}; stderr was drained without logging")
