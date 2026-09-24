"""Persistent OpenCADStudio MCP stdio client for automation harnesses.

No mutation is replayed after a lost reply. An unresolved operation is an error
that requires reconciliation against the same session and request_id.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
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

    def __init__(self, result: dict):
        self.result = result
        super().__init__(str(result))


class UncertainMutation(ProtocolError):
    pass


class TraceSink:
    """Append only, intentionally omitting all RPC parameters and results."""

    def __init__(self, path: Path, run_id: str):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
            raise ValueError("Invalid trace run_id")
        self.path = path
        self.run_id = run_id
        self.sequence = 0
        self.failed = False
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError("Trace path must be new for each run")
        with path.open("x", encoding="utf-8"):
            pass

    def emit(self, *, method: str, status: str, began_ns: int,
             began_utc: str, ended_utc: str) -> None:
        # Whitelist keeps unexpected method names and exception text out of evidence.
        if method not in {"server/discover", "initialize", "tools/list", "tools/call",
                          "tasks/get", "tasks/cancel", "ping"}:
            method = "other"
        with self._lock:
            self.sequence += 1
            event = {"schema_version": "m3-rpc-trace-1", "run_id": self.run_id,
                     "sequence": self.sequence, "phase": "rpc", "method": method,
                     "status": status, "started_at_utc": began_utc,
                     "ended_at_utc": ended_utc,
                     "elapsed_ms": round((time.monotonic_ns() - began_ns) / 1_000_000, 3)}
            try:
                line = json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
                with self.path.open("a", encoding="utf-8") as target:
                    target.write(line)
                    target.flush()
                    os.fsync(target.fileno())
            except OSError:
                self.failed = True


class Client:
    def __init__(self, server: Path, *, timeout: float = 15.0, max_pending: int = 64,
                 command: Sequence[str] | None = None,
                 environment: dict[str, str] | None = None,
                 trace_path: Path | None = None, run_id: str | None = None) -> None:
        self.trace = TraceSink(trace_path, run_id) if trace_path is not None and run_id is not None else None
        if (trace_path is None) != (run_id is None):
            raise ValueError("trace_path and run_id must be supplied together")
        self.process = subprocess.Popen(
            list(command) if command is not None else [str(server), "--mcp"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", bufsize=1, env=environment,
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
        self._sessions: dict[str, dict] = {}
        self._blocked_sessions: dict[str, str] = {}
        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

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
        began_ns = time.monotonic_ns()
        began_utc = datetime.now(timezone.utc).isoformat()
        status = "completed"
        try:
            return self._rpc_impl(method, params, timeout=timeout)
        except RpcTimeout:
            status = "timeout"
            raise
        except ProtocolError:
            status = "failed"
            raise
        except Exception:
            status = "failed"
            raise
        finally:
            if self.trace is not None:
                self.trace.emit(method=method, status=status, began_ns=began_ns,
                                began_utc=began_utc,
                                ended_utc=datetime.now(timezone.utc).isoformat())

    def _rpc_impl(self, method: str, params: dict, *, timeout: float | None = None) -> dict:
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
        result = self._tool_raw(name, arguments, deadline=deadline)
        if name == "ocs_read" and arguments.get("op") == "state":
            self._remember_state(arguments["ocs_session_id"], result)
        return result

    def _remember_state(self, session_id: str, state: dict) -> None:
        if isinstance(state.get("document_id"), int) and isinstance(state.get("revision"), int):
            self._sessions[session_id] = {"document_id": state["document_id"],
                                          "revision": state["revision"]}

    def _tool_raw(self, name: str, arguments: dict, *, deadline: float | None = None) -> dict:
        result = self._tool_result(name, arguments, deadline=deadline)
        structured = result.get("structuredContent")
        if structured is None or structured.get("ok") is False or result.get("isError"):
            raise ToolError(structured or result)
        return structured

    def _tool_result(self, name: str, arguments: dict, *, deadline: float | None = None) -> dict:
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
        return result

    def capture_artifact(self, session_id: str, path: Path, *, document_id: int,
                         geometry_revision: int, camera_revision: int,
                         max_dimension: int = 1024) -> dict:
        """Store a fenced PNG locally; never put its Base64 into a trace or report."""
        if not path.is_absolute() or path.suffix.lower() != ".png" or path.exists():
            raise ValueError("Capture path must be a new absolute PNG path")
        if not 256 <= max_dimension <= 4096:
            raise ValueError("Capture max_dimension is outside the MCP contract")
        expected = {"document_id": document_id, "geometry_revision": geometry_revision,
                    "camera_revision": camera_revision}
        if any(type(value) is not int or value < 0 for value in expected.values()):
            raise ValueError("Capture document/revision identities are required")
        result = self._tool_result("ocs_capture", {"ocs_session_id": session_id,
                            "scope": "viewport", "max_dimension": max_dimension, **expected},
                            deadline=time.monotonic() + 45)
        metadata = result.get("structuredContent")
        if result.get("isError") or not isinstance(metadata, dict) or metadata.get("ok") is not True \
                or any(metadata.get(key) != value for key, value in expected.items()) \
                or metadata.get("rendered_geometry_revision") != geometry_revision \
                or metadata.get("rendered_camera_revision") != camera_revision \
                or metadata.get("render_fence") != "shader_encoded_frame":
            raise ProtocolError("Capture identity or render revision differs")
        if metadata.get("scope") != "viewport":
            raise ProtocolError("Capture scope differs from requested viewport")
        images = [item for item in result.get("content", [])
                  if item.get("type") == "image" and item.get("mimeType") == "image/png"]
        if len(images) != 1 or not isinstance(images[0].get("data"), str):
            raise ProtocolError("MCP capture did not return exactly one PNG image")
        try:
            data = base64.b64decode(images[0]["data"], validate=True)
        except (ValueError, binascii.Error) as error:
            raise ProtocolError("MCP capture Base64 is invalid") from error
        if len(data) > 20_000_000 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ProtocolError("MCP capture is not a bounded PNG")
        with path.open("xb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        return {key: metadata.get(key) for key in
                ("document_id", "revision", "geometry_revision", "camera_revision",
                 "width", "height", "scope", "rendered_geometry_revision",
                 "rendered_camera_revision", "render_fence", "timings")}

    @staticmethod
    def _remaining(deadline: float | None) -> float | None:
        if deadline is None:
            return None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RpcTimeout("MCP operation deadline exceeded")
        return remaining

    def ready_session(self, *, session_id: str | None = None,
                      launch_if_none: bool = False, wait_for_existing: bool = False,
                      timeout: float = 90.0) -> dict:
        deadline = time.monotonic() + timeout
        launched = False
        interval = 0.1
        while True:
            try:
                discovery = self.tool("ocs_sessions", {"launch_if_none": launch_if_none and not launched},
                                      deadline=deadline)
                launched = True
                if discovery.get("status") == "starting":
                    remaining = self._remaining(deadline)
                    pause = max(0.01, discovery.get("retry_after_ms", 200) / 1000)
                    time.sleep(min(pause, remaining))
                    continue
                if discovery.get("status") == "failed":
                    raise ProtocolError(f"Editor startup failed: {discovery.get('reason')}")
                if discovery.get("status") == "absent" and wait_for_existing:
                    time.sleep(min(0.2, self._remaining(deadline)))
                    continue
                sessions = discovery["result"]
                if session_id is None and len(sessions) != 1:
                    raise ProtocolError(f"Expected one session, found {len(sessions)}; specify session_id")
                matching = [s for s in sessions if s["session_id"] == session_id] if session_id else sessions
                if len(matching) != 1:
                    raise ProtocolError("Selected session is absent or ambiguous")
                self._remember_state(matching[0]["session_id"], matching[0])
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
        if deadline is None:
            deadline = time.monotonic() + max(self.timeout, 90.0)
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
        if session_id in self._blocked_sessions:
            raise UncertainMutation(
                f"Session has unresolved mutation {self._blocked_sessions[session_id]}; reconcile before editing")
        effective = request.copy()
        if request.get("op") not in {"new", "open", "stop", "activate"}:
            state = self._sessions.get(session_id)
            if state is None and ("document_id" not in effective or "revision" not in effective):
                raise ValueError("Select/read the session before editing; document_id and revision required")
            if state:
                effective.setdefault("document_id", state["document_id"])
                effective.setdefault("revision", state["revision"])
        self._mutations[request_id] = (digest, None)
        try:
            result = self._tool_raw("ocs_execute", {"ocs_session_id": session_id, "request": effective, **options},
                                    deadline=deadline)
        except ToolError as exc:
            if exc.result.get("completed_commands", 0) or exc.result.get("changes"):
                self._blocked_sessions[session_id] = request_id
            raise
        except (RpcTimeout, ProtocolError) as exc:
            # A transport failure may occur after the editor commits. Query only.
            try:
                return self.recover(session_id, request_id, deadline=deadline)
            except ToolError as recovery_exc:
                if recovery_exc.result.get("completed_commands", 0) or recovery_exc.result.get("changes"):
                    self._blocked_sessions[session_id] = request_id
                raise  # Known failed/partial operation includes progress.
            except (RpcTimeout, ProtocolError) as recovery_exc:
                self._blocked_sessions[session_id] = request_id
                raise UncertainMutation(f"{request_id}: outcome unknown; {recovery_exc}") from exc
        if result.get("status") in {"accepted", "running"}:
            return self.recover(session_id, request_id, deadline=deadline)
        if result.get("status") == "waiting_input" and not (
                request.get("op") == "action" and request.get("name") == "close_modal"):
            self._blocked_sessions[session_id] = request_id
            raise UncertainMutation(f"{request_id}: operation awaits input; preserve progress")
        self._mutations[request_id] = (digest, result)
        if isinstance(result.get("state"), dict):
            self._remember_state(session_id, result["state"])
        return result

    def recover(self, session_id: str, request_id: str, *, deadline: float | None = None) -> dict:
        if deadline is None:
            deadline = time.monotonic() + max(self.timeout, 90.0)
        while True:
            try:
                operation = self.tool("ocs_read", {"ocs_session_id": session_id, "op": "operation",
                                                    "parameters": {"request_id": request_id}}, deadline=deadline)
            except ToolError as exc:
                self._blocked_sessions[session_id] = request_id
                raise
            except ProtocolError as exc:
                self._blocked_sessions[session_id] = request_id
                raise UncertainMutation(f"{request_id}: operation cannot be reconciled; {exc}") from exc
            if operation.get("status") in {"accepted", "running"}:
                try:
                    time.sleep(min(0.1, self._remaining(deadline)))
                except RpcTimeout as exc:
                    self._blocked_sessions[session_id] = request_id
                    raise UncertainMutation(f"{request_id}: still running; preserve progress") from exc
                continue
            break
        if operation.get("status") == "waiting_input":
            self._blocked_sessions[session_id] = request_id
            raise UncertainMutation(f"{request_id}: operation awaits input; preserve progress")
        if operation.get("request_id") != request_id:
            self._blocked_sessions[session_id] = request_id
            raise UncertainMutation(f"{request_id}: operation identity not confirmed")
        if operation.get("ok") is not True or operation.get("status") != "completed":
            self._blocked_sessions[session_id] = request_id
            raise UncertainMutation(f"{request_id}: operation did not complete successfully")
        previous = self._mutations.get(request_id)
        if previous:
            self._mutations[request_id] = (previous[0], operation)
        if self._blocked_sessions.get(session_id) == request_id:
            self._blocked_sessions.pop(session_id)
        if isinstance(operation.get("state"), dict):
            self._remember_state(session_id, operation["state"])
        return operation

    def close(self) -> None:
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            code = self.process.wait(timeout=5)
        except subprocess.TimeoutExpired as exc:
            raise ProtocolError("MCP process did not exit after stdin closed") from exc
        # A reader can hold the buffered stream lock until EOF. Join with a
        # bound before closing it, so an inherited GUI handle cannot hang close.
        self._stdout_thread.join(timeout=0.5)
        self._stderr_thread.join(timeout=0.5)
        if self.process.stdout and not self._stdout_thread.is_alive():
            self.process.stdout.close()
        if self.process.stderr and not self._stderr_thread.is_alive():
            self.process.stderr.close()
        if code != 0:
            raise ProtocolError(f"MCP exited {code}; stderr was drained without logging")
