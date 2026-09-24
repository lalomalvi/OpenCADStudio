//! Client-neutral MCP adapter for the live desktop editor.
//!
//! `OpenCADStudio --mcp` speaks MCP over stdio. All drawing work is forwarded
//! to the authenticated GUI control bridge; this module contains no geometry.

use base64::{Engine as _, engine::general_purpose::STANDARD as BASE64};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::{HashMap, HashSet, VecDeque},
    fs::{File, OpenOptions},
    io::{self, BufRead, BufReader, Read, Write},
    net::TcpStream,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::atomic::{AtomicUsize, Ordering},
    sync::{Mutex, OnceLock},
    thread,
    time::{Duration, Instant},
};

const PROTOCOL_VERSION: &str = "2025-11-25";
const MODERN_PROTOCOL_VERSION: &str = "2026-07-28";
const MAX_REQUEST: usize = 1_048_576;
const MAX_RESPONSE: u64 = 16 * 1024 * 1024;
const MAX_DESCRIPTOR: u64 = 8 * 1024;
const CACHE_TTL_MS: u64 = 3_600_000;
const INSTRUCTIONS: &str = "Call ocs_sessions, then pass its session_id as ocs_session_id to ocs_read, ocs_execute and ocs_capture. Read capabilities to discover the complete CAD automation surface. Call record_schema to discover every record type, property path, JSON type, enum, unit, constraint and write rule before editing unfamiliar data. Use records to inspect every serializable entity, object, table, header and document record; filter with RFC 6901 JSON Pointer paths. Use set_properties for atomic, type-checked record edits and preserve document_id, revision and request_id. Use commands with parameters.name for a command manifest. Use run_script for a long, known sequence of complete command lines; it is resumable, strict by default and returns a compact summary. Use batch when operations other than command lines must be mixed, and request changed_entities only when resulting geometry is needed. For interactive work, call start and follow state.command.accepts, options and input_example. A run.cmd contains the command name followed by prompt answers separated by spaces; points use x,y or x,y,z. After a timeout, query the existing operation and never replay a mutation with a new request_id. waiting_input and running are not completion. Let OCS and its geometry kernel calculate geometry; use query near, contains_point and intersections for exact relationships. Before delivery call audit with the intended target_format and target_version; use save_verified with an explicit absolute path to save, reopen, hash and compare the semantic manifest.";
const READ_OPS: &[&str] = &[
    "state",
    "hello",
    "query",
    "records",
    "record_schema",
    "capabilities",
    "entities",
    "layers",
    "header",
    "properties",
    "measure",
    "history",
    "commands",
    "events",
    "operation",
    "audit",
];
const EXECUTE_OPS: &[&str] = &[
    "new",
    "open",
    "activate",
    "run",
    "start",
    "input",
    "cancel",
    "undo",
    "redo",
    "select",
    "property",
    "set_properties",
    "action",
    "embed_image",
    "save",
    "save_verified",
    "stop",
    "batch",
    "run_script",
    "shutdown_owned_session",
];
const BATCH_STEP_OPS: &[&str] = &[
    "new",
    "open",
    "activate",
    "run",
    "start",
    "input",
    "cancel",
    "undo",
    "redo",
    "select",
    "property",
    "set_properties",
    "action",
    "embed_image",
    "save",
    "stop",
];
const MAX_BATCH_STEPS: usize = 64;
const MAX_SCRIPT_COMMANDS: usize = 256;
const MAX_SCRIPT_COMMAND_BYTES: usize = 4096;
const MAX_SCRIPT_BYTES: usize = 256 * 1024;

#[derive(Clone, Deserialize)]
struct Descriptor {
    session_id: String,
    port: u16,
    token: String,
    #[serde(default)]
    pid: Option<u32>,
    #[serde(default)]
    executable: Option<String>,
    #[serde(default)]
    started_at_unix_ms: Option<u64>,
}

#[derive(Default)]
struct LaunchState {
    child: Option<Child>,
    started: Option<Instant>,
    failure: Option<String>,
    closed: Option<ClosedSession>,
}

struct ClosedSession {
    session_id: String,
    process_id: u32,
    started_at_unix_ms: u64,
    request_id: String,
    owned_root: PathBuf,
}

static LAUNCH: OnceLock<Mutex<LaunchState>> = OnceLock::new();

struct GuiClient {
    descriptor: Descriptor,
    state: Value,
    client_id: String,
    batches: VecDeque<BatchExecution>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct BatchExecution {
    id: String,
    request: Value,
    steps: Vec<Value>,
    next: usize,
    active: Option<String>,
    results: Vec<Value>,
    changes: Vec<Value>,
    state: Option<Value>,
    terminal: Option<Value>,
}

#[derive(Serialize, Deserialize)]
struct BatchJournal {
    schema_version: u32,
    session_id: String,
    batch: BatchExecution,
}

const MAX_BATCH_JOURNAL: u64 = 16 * 1024 * 1024;

fn batch_journal_dir() -> Result<PathBuf, String> {
    let dir = crate::config::config_dir()
        .ok_or_else(|| "No user configuration directory".to_string())?
        .join("automation").join("batch-journal");
    if dir.symlink_metadata().is_ok_and(|meta| meta.file_type().is_symlink()) {
        return Err("Batch journal directory must not be a symlink".into());
    }
    Ok(dir)
}

fn batch_journal_path(dir: &Path, session_id: &str, batch_id: &str) -> PathBuf {
    let mut hasher = Sha256::new();
    hasher.update(session_id.as_bytes());
    hasher.update([0]);
    hasher.update(batch_id.as_bytes());
    let digest = hasher.finalize();
    let name: String = digest.iter().map(|byte| format!("{byte:02x}")).collect();
    dir.join(format!("{name}.json"))
}

#[cfg(windows)]
fn atomic_replace(source: &Path, destination: &Path) -> Result<(), String> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{MoveFileExW, MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH};
    // canonicalize returns verbatim (\\?\) paths, required for deep worktrees.
    let source = source.canonicalize().map_err(|error| error.to_string())?;
    let parent = destination.parent().ok_or_else(|| "Journal has no parent".to_string())?
        .canonicalize().map_err(|error| error.to_string())?;
    let destination = parent.join(destination.file_name()
        .ok_or_else(|| "Journal has no file name".to_string())?);
    let source: Vec<u16> = source.as_os_str().encode_wide().chain(Some(0)).collect();
    let destination: Vec<u16> = destination.as_os_str().encode_wide().chain(Some(0)).collect();
    if unsafe { MoveFileExW(source.as_ptr(), destination.as_ptr(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) } == 0 {
        return Err(std::io::Error::last_os_error().to_string());
    }
    Ok(())
}

#[cfg(not(windows))]
fn atomic_replace(source: &Path, destination: &Path) -> Result<(), String> {
    std::fs::rename(source, destination).map_err(|error| error.to_string())
}

fn persist_batch(session_id: &str, batch: &BatchExecution) -> Result<(), String> {
    let dir = batch_journal_dir()?;
    persist_batch_in(&dir, session_id, batch)
}

fn persist_batch_in(dir: &Path, session_id: &str, batch: &BatchExecution) -> Result<(), String> {
    std::fs::create_dir_all(&dir).map_err(|error| error.to_string())?;
    let path = batch_journal_path(&dir, session_id, &batch.id);
    if path.symlink_metadata().is_ok_and(|meta| !meta.file_type().is_file()) {
        return Err("Batch journal target must be a regular file".into());
    }
    let temporary = path.with_extension(format!("{}.tmp", random_id()?));
    let wire = serde_json::to_vec(&BatchJournal {
        schema_version: 1, session_id: session_id.into(), batch: batch.clone(),
    }).map_err(|error| error.to_string())?;
    if wire.len() as u64 > MAX_BATCH_JOURNAL {
        return Err("Batch journal exceeds size limit".into());
    }
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)] {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(&temporary).map_err(|error| error.to_string())?;
    file.write_all(&wire).and_then(|_| file.sync_all()).map_err(|error| error.to_string())?;
    drop(file);
    atomic_replace(&temporary, &path)?;
    #[cfg(unix)] {
        File::open(&dir).and_then(|file| file.sync_all()).map_err(|error| error.to_string())?;
    }
    Ok(())
}

fn load_batch(session_id: &str, batch_id: &str) -> Result<Option<BatchExecution>, String> {
    load_batch_in(&batch_journal_dir()?, session_id, batch_id)
}

fn load_batch_in(dir: &Path, session_id: &str, batch_id: &str) -> Result<Option<BatchExecution>, String> {
    let path = batch_journal_path(dir, session_id, batch_id);
    let Ok(meta) = path.symlink_metadata() else { return Ok(None); };
    if !meta.file_type().is_file() || meta.len() > MAX_BATCH_JOURNAL
        || !private_descriptor(&path) {
        return Err("Batch journal is unsafe or exceeds size limit".into());
    }
    let wire = std::fs::read(path).map_err(|error| error.to_string())?;
    let journal: BatchJournal = serde_json::from_slice(&wire)
        .map_err(|_| "Batch journal is corrupt; do not replay its mutation".to_string())?;
    if journal.schema_version != 1 || journal.session_id != session_id
        || journal.batch.id != batch_id {
        return Err("Batch journal identity differs; do not replay its mutation".into());
    }
    Ok(Some(journal.batch))
}

#[cfg(test)]
fn load_batches_in(dir: &Path, session_id: &str) -> Result<VecDeque<BatchExecution>, String> {
    let Ok(entries) = dir.read_dir() else { return Ok(VecDeque::new()); };
    let mut paths: Vec<_> = entries.filter_map(Result::ok).map(|entry| entry.path())
        .filter(|path| path.extension().and_then(|extension| extension.to_str()) == Some("json"))
        .filter(|path| path.symlink_metadata().is_ok_and(|meta|
            meta.file_type().is_file() && meta.len() <= MAX_BATCH_JOURNAL))
        .collect();
    paths.sort_by_key(|path| std::cmp::Reverse(path.metadata().and_then(|meta| meta.modified()).ok()));
    let mut batches = VecDeque::new();
    for path in paths.into_iter().take(256) {
        if !private_descriptor(&path) { continue; }
        let Ok(bytes) = std::fs::read(path) else { continue; };
        let Ok(journal) = serde_json::from_slice::<BatchJournal>(&bytes) else { continue; };
        if journal.schema_version == 1 && journal.session_id == session_id {
            batches.push_back(journal.batch);
            if batches.len() == 64 { break; }
        }
    }
    Ok(batches)
}

struct McpTask {
    id: String,
    name: String,
    arguments: Value,
    created_at: String,
    last_updated_at: String,
    result: Option<Value>,
    error: Option<Value>,
}

#[derive(Default)]
struct TaskStore {
    tasks: VecDeque<McpTask>,
}

impl TaskStore {
    fn insert(&mut self, task: McpTask) {
        self.tasks.push_back(task);
    }

    fn get_mut(&mut self, id: &str) -> Option<&mut McpTask> {
        self.tasks.iter_mut().find(|task| task.id == id)
    }
}

fn random_id() -> Result<String, String> {
    let mut bytes = [0u8; 16];
    getrandom::fill(&mut bytes).map_err(|error| error.to_string())?;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

fn iso8601_now() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64;
    let days = seconds.div_euclid(86_400);
    let day_seconds = seconds.rem_euclid(86_400);
    let shifted = days + 719_468;
    let era = shifted.div_euclid(146_097);
    let day_of_era = shifted - era * 146_097;
    let year_of_era =
        (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let mut year = year_of_era + era * 400;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_prime = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * month_prime + 2) / 5 + 1;
    let month = month_prime + if month_prime < 10 { 3 } else { -9 };
    year += i64::from(month <= 2);
    let hour = day_seconds / 3_600;
    let minute = day_seconds % 3_600 / 60;
    let second = day_seconds % 60;
    format!("{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}Z")
}

#[cfg(unix)]
fn private_descriptor(path: &Path) -> bool {
    use std::os::unix::fs::MetadataExt;
    let Ok(file) = path.metadata() else {
        return false;
    };
    let Some(parent) = path.parent() else {
        return false;
    };
    let Ok(directory) = parent.metadata() else {
        return false;
    };
    file.uid() == directory.uid() && file.mode() & 0o077 == 0
}

#[cfg(not(unix))]
fn private_descriptor(_: &Path) -> bool {
    true
}

fn exchange(descriptor: &Descriptor, request: Value, timeout: Duration) -> Result<Value, String> {
    let mut object = request
        .as_object()
        .cloned()
        .ok_or_else(|| "GUI request must be an object".to_string())?;
    object.insert("token".into(), Value::String(descriptor.token.clone()));
    object.insert(
        "session_id".into(),
        Value::String(descriptor.session_id.clone()),
    );
    object.insert("protocol".into(), Value::from(1));
    let mut wire = serde_json::to_vec(&Value::Object(object)).map_err(|e| e.to_string())?;
    wire.push(b'\n');
    if wire.len() > MAX_REQUEST {
        return Err("Request exceeds 1 MiB".into());
    }

    let mut stream =
        TcpStream::connect(("127.0.0.1", descriptor.port)).map_err(|error| error.to_string())?;
    stream
        .set_read_timeout(Some(timeout))
        .map_err(|error| error.to_string())?;
    stream
        .set_write_timeout(Some(timeout))
        .map_err(|error| error.to_string())?;
    stream.write_all(&wire).map_err(|error| error.to_string())?;

    let mut response = String::new();
    BufReader::new(stream)
        .take(MAX_RESPONSE + 1)
        .read_to_string(&mut response)
        .map_err(|error| error.to_string())?;
    if response.is_empty() || response.len() as u64 > MAX_RESPONSE {
        return Err("No valid OCS response; query request_id before retrying a mutation".into());
    }
    serde_json::from_str(response.trim_end()).map_err(|error| error.to_string())
}

fn descriptors_in(directory: &Path) -> Result<Vec<(Descriptor, Value)>, String> {
    let Ok(entries) = directory.read_dir() else {
        return Ok(Vec::new());
    };
    let mut paths: Vec<PathBuf> = entries
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.extension().and_then(|value| value.to_str()) == Some("json"))
        .filter(|path| path.symlink_metadata().is_ok_and(|meta| meta.file_type().is_file()))
        .collect();
    paths.sort_by_key(|path| std::cmp::Reverse(
        path.metadata().and_then(|m| m.modified()).ok()));
    let next = AtomicUsize::new(0);
    let found = Mutex::new(Vec::new());
    thread::scope(|scope| {
        for _ in 0..paths.len().min(16) {
            let paths = &paths;
            let next = &next;
            let found = &found;
            scope.spawn(move || {
                loop {
                    let index = next.fetch_add(1, Ordering::Relaxed);
                    let Some(path) = paths.get(index) else { break };
                    if !private_descriptor(path)
                        || !path.metadata().is_ok_and(|meta| meta.len() <= MAX_DESCRIPTOR) { continue; }
                    let Ok(text) = std::fs::read_to_string(path) else { continue };
                    let Ok(descriptor) = serde_json::from_str::<Descriptor>(&text) else { continue };
                    let Ok(state) = exchange(&descriptor, json!({"op":"hello"}), Duration::from_millis(250)) else { continue };
                    if state["ok"].as_bool() == Some(true)
                        && state["session_id"].as_str() == Some(descriptor.session_id.as_str())
                    {
                        if let Ok(mut matches) = found.lock() {
                            matches.push((descriptor, state));
                        }
                    }
                }
            });
        }
    });
    let mut found = found.into_inner().map_err(|_| "Discovery lock poisoned".to_string())?;
    found.sort_by(|a, b| a.0.session_id.cmp(&b.0.session_id));
    Ok(found)
}

fn descriptors() -> Result<Vec<(Descriptor, Value)>, String> {
    let directory = crate::config::config_dir()
        .ok_or_else(|| "No user configuration directory".to_string())?
        .join("automation");
    descriptors_in(&directory)
}

fn descriptor_for_session(session_id: &str) -> Result<(Descriptor, Value), String> {
    if session_id.len() != 32 || !session_id.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err("session_id must be a 32-character hexadecimal ID".into());
    }
    let path = crate::config::config_dir()
        .ok_or_else(|| "No user configuration directory".to_string())?
        .join("automation")
        .join(format!("{session_id}.json"));
    if !path.symlink_metadata().is_ok_and(|meta| meta.file_type().is_file() && meta.len() <= MAX_DESCRIPTOR)
        || !private_descriptor(&path)
    {
        return Err("Selected session descriptor is absent or unsafe".into());
    }
    let text = std::fs::read_to_string(path).map_err(|error| error.to_string())?;
    let descriptor: Descriptor = serde_json::from_str(&text).map_err(|error| error.to_string())?;
    if descriptor.session_id != session_id {
        return Err("Selected session descriptor identity differs".into());
    }
    // A cold GUI can briefly exceed the discovery probe's 250 ms budget.
    // Probe only this selected descriptor with a bounded, longer handshake.
    let state = exchange(&descriptor, json!({"op":"hello"}), Duration::from_secs(2))?;
    if state["ok"].as_bool() != Some(true)
        || state["session_id"].as_str() != Some(session_id)
    {
        return Err("Selected session handshake failed".into());
    }
    Ok((descriptor, state))
}

fn log_file() -> Result<File, String> {
    let directory = crate::config::config_dir()
        .ok_or_else(|| "No user configuration directory".to_string())?
        .join("automation");
    std::fs::create_dir_all(&directory).map_err(|error| error.to_string())?;
    OpenOptions::new()
        .create(true)
        .append(true)
        .open(directory.join("gui.log"))
        .map_err(|error| error.to_string())
}

fn start_gui() -> Result<Child, String> {
    let executable = std::env::current_exe().map_err(|error| error.to_string())?;
    let log = log_file()?;
    let stderr = log.try_clone().map_err(|error| error.to_string())?;
    Command::new(executable)
        .arg("--new-instance")
        .stdin(Stdio::null())
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(stderr))
        .spawn()
        .map_err(|error| error.to_string())
}

fn sessions(launch_if_none: bool) -> Result<Value, String> {
    let available = descriptors()?;
    if !available.is_empty() {
        return Ok(json!({"ok":true,"status":"ready","result":
            available.into_iter().map(|(descriptor, mut state)| {
                if let Some(object) = state.as_object_mut() {
                    object.insert("process_id".into(), json!(descriptor.pid));
                    object.insert("executable_path".into(), json!(descriptor.executable));
                    object.insert("process_started_at_unix_ms".into(), json!(descriptor.started_at_unix_ms));
                }
                state
            }).collect::<Vec<_>>()}));
    }
    let mut launch = LAUNCH.get_or_init(|| Mutex::new(LaunchState::default()))
        .lock().map_err(|_| "Launch state lock poisoned".to_string())?;
    if let Some(reason) = &launch.failure {
        return Ok(json!({"ok":false,"status":"failed","reason":reason,"result":[]}));
    }
    if let Some(child) = launch.child.as_mut() {
        if child.try_wait().map_err(|error| error.to_string())?.is_some() {
            launch.failure = Some("launched_editor_exited".into());
        } else if launch.started.is_some_and(|at| at.elapsed() >= Duration::from_secs(90)) {
            launch.failure = Some("readiness_deadline_exceeded".into());
        }
        if let Some(reason) = &launch.failure {
            return Ok(json!({"ok":false,"status":"failed","reason":reason,"result":[]}));
        }
        let remaining = 90_000u128.saturating_sub(
            launch.started.map_or(0, |at| at.elapsed().as_millis()));
        return Ok(json!({"ok":true,"status":"starting","reason":"waiting_for_editor_descriptor",
            "retry_after_ms":200,"deadline_remaining_ms":remaining,"result":[]}));
    }
    if !launch_if_none {
        return Ok(json!({"ok":true,"status":"absent","result":[]}));
    }
    match start_gui() {
        Ok(child) => {
            launch.child = Some(child);
            launch.started = Some(Instant::now());
            launch.closed = None;
            Ok(json!({"ok":true,"status":"starting","reason":"editor_launch_requested",
                "retry_after_ms":200,"deadline_remaining_ms":90_000,"result":[]}))
        }
        Err(_) => {
            launch.failure = Some("editor_launch_failed".into());
            Ok(json!({"ok":false,"status":"failed","reason":"editor_launch_failed","result":[]}))
        }
    }
}

fn insert_default(object: &mut Map<String, Value>, key: &str, value: Value) {
    if !object.contains_key(key) {
        object.insert(key.into(), value);
    }
}

impl GuiClient {
    #[cfg(test)]
    fn batch_operation(&self, id: &str) -> Option<Value> {
        self.batches.iter().find(|batch| batch.id == id).map(|batch| {
            batch.terminal.clone().unwrap_or_else(|| batch_result(batch, "running", true))
        })
    }

    fn resume_batch_operation(&mut self, id: &str) -> Result<Option<Value>, String> {
        if !self.batches.iter().any(|batch| batch.id == id) {
            if let Some(batch) = load_batch(&self.descriptor.session_id, id)? {
                self.batches.push_back(batch);
            }
        }
        let Some(batch) = self.batches.iter().find(|batch| batch.id == id) else {
            return Ok(None);
        };
        if let Some(terminal) = &batch.terminal {
            return Ok(Some(terminal.clone()));
        }
        // A previous MCP response may have been lost. Resume from the saved
        // step and query an active GUI request_id; never issue it again.
        let request = batch.request.clone();
        self.execute_batch(request, 30.0).map(Some)
    }

    fn connect(session_id: &str) -> Result<Self, String> {
        let (descriptor, state) = descriptor_for_session(session_id)?;
        Ok(Self {
            descriptor,
            state,
            client_id: random_id()?,
            batches: VecDeque::new(),
        })
    }

    fn request(&mut self, request: Value, wait_seconds: f64) -> Result<Value, String> {
        let mut object = request
            .as_object()
            .cloned()
            .ok_or_else(|| "request must be an object".to_string())?;
        let op = object
            .get("op")
            .and_then(Value::as_str)
            .ok_or_else(|| "request must contain op".to_string())?
            .to_string();
        if !READ_OPS.contains(&op.as_str()) {
            insert_default(&mut object, "request_id", Value::String(random_id()?));
            insert_default(
                &mut object,
                "client_id",
                Value::String(self.client_id.clone()),
            );
            insert_default(
                &mut object,
                "document_id",
                self.state["document_id"].clone(),
            );
            insert_default(&mut object, "revision", self.state["revision"].clone());
            if ["input", "property", "run", "action", "save", "save_verified", "undo", "redo"].contains(&op.as_str())
            {
                insert_default(&mut object, "selection", self.state["selection"].clone());
            }
        }

        let request_id = object.get("request_id").cloned();
        let mut response = exchange(
            &self.descriptor,
            Value::Object(object),
            Duration::from_secs(15),
        )?;
        let wait = wait_seconds.clamp(0.0, 60.0);
        let deadline = Instant::now() + Duration::from_secs_f64(wait);
        while matches!(response["status"].as_str(), Some("accepted" | "running"))
            && Instant::now() < deadline
        {
            let Some(request_id) = request_id.clone() else {
                break;
            };
            thread::sleep(Duration::from_millis(50));
            response = exchange(
                &self.descriptor,
                json!({"op":"operation","request_id":request_id}),
                Duration::from_secs(15),
            )?;
        }
        if response.get("state").is_some() {
            self.state = response["state"].clone();
        } else if matches!(op.as_str(), "hello" | "state") && response["ok"].as_bool() == Some(true)
        {
            self.state = response.clone();
        }
        Ok(response)
    }

    fn execute_batch(&mut self, request: Value, wait_seconds: f64) -> Result<Value, String> {
        let id = required_string(&request, "request_id")?.to_owned();
        if !self.batches.iter().any(|batch| batch.id == id) {
            if let Some(saved) = load_batch(&self.descriptor.session_id, &id)? {
                self.batches.push_back(saved);
            }
        }
        let mut batch = if let Some(position) = self.batches.iter().position(|batch| batch.id == id)
        {
            let batch = self
                .batches
                .remove(position)
                .expect("batch position exists");
            if batch.request != request {
                self.batches.push_back(batch);
                return Err("request_id was already used for a different batch".into());
            }
            batch
        } else {
            let expected_document = request["document_id"].as_u64()
                .ok_or_else(|| "batch requires document_id from selected session".to_string())?;
            let expected_revision = request["revision"].as_u64()
                .ok_or_else(|| "batch requires revision from selected session".to_string())?;
            let current = self.request(json!({"op":"state"}), 0.0)?;
            if current["document_id"].as_u64() != Some(expected_document)
                || current["revision"].as_u64() != Some(expected_revision) {
                return Err("Selected document or revision changed; read state before editing".into());
            }
            let steps = request["steps"]
                .as_array()
                .cloned()
                .ok_or_else(|| "batch requires a steps array".to_string())?;
            let batch = BatchExecution {
                id,
                request,
                steps,
                next: 0,
                active: None,
                results: Vec::new(),
                changes: Vec::new(),
                state: None,
                terminal: None,
            };
            persist_batch(&self.descriptor.session_id, &batch)?;
            batch
        };

        if let Some(result) = batch.terminal.clone() {
            self.batches.push_back(batch);
            return Ok(result);
        }

        let deadline = Instant::now() + Duration::from_secs_f64(wait_seconds.clamp(0.0, 60.0));
        let mut attempted = false;
        loop {
            if batch.next == batch.steps.len() {
                let waiting = batch
                    .state
                    .as_ref()
                    .is_some_and(|state| !state["command"].is_null());
                let result = batch_result(
                    &batch,
                    if waiting {
                        "waiting_input"
                    } else {
                        "completed"
                    },
                    true,
                );
                batch.terminal = Some(result.clone());
                persist_batch(&self.descriptor.session_id, &batch)?;
                self.batches.push_back(batch);
                trim_batches(&mut self.batches);
                return Ok(result);
            }
            if attempted && Instant::now() >= deadline {
                let result = batch_result(&batch, "running", true);
                self.batches.push_back(batch);
                trim_batches(&mut self.batches);
                return Ok(result);
            }
            attempted = true;

            let resuming = batch.active.is_some();
            let step_id = batch.active.clone()
                .unwrap_or_else(|| batch_step_id(&batch.id, batch.next));
            if !resuming {
                batch.active = Some(step_id.clone());
                persist_batch(&self.descriptor.session_id, &batch)?;
            }
            let response = if resuming {
                self.request(
                    json!({"op":"operation","request_id":step_id}),
                    deadline
                        .saturating_duration_since(Instant::now())
                        .as_secs_f64(),
                )
            } else {
                let mut step = batch.steps[batch.next]
                    .as_object()
                    .cloned()
                    .ok_or_else(|| format!("batch step {} must be an object", batch.next))?;
                for key in [
                    "geometry_revision",
                    "camera_revision",
                    "selection",
                    "client_id",
                ] {
                    step.remove(key);
                }
                let expected = batch.state.as_ref().unwrap_or(&batch.request);
                step.insert("document_id".into(), expected["document_id"].clone());
                step.insert("revision".into(), expected["revision"].clone());
                step.insert("request_id".into(), Value::String(step_id.clone()));
                self.request(
                    Value::Object(step),
                    deadline
                        .saturating_duration_since(Instant::now())
                        .as_secs_f64(),
                )
            };
            let mut response = match response {
                Ok(response) => response,
                Err(error) => {
                    batch.active = Some(step_id);
                    persist_batch(&self.descriptor.session_id, &batch)?;
                    self.batches.push_back(batch);
                    trim_batches(&mut self.batches);
                    return Err(error);
                }
            };

            let strict = batch.request["strict"]
                .as_bool()
                .unwrap_or(batch.request["op"] == "run_script");
            if let Some(error) = strict.then(|| strict_command_error(&response)).flatten() {
                if let Some(object) = response.as_object_mut() {
                    object.insert("ok".into(), Value::Bool(false));
                    object.insert("status".into(), Value::String("failed".into()));
                    object.insert("code".into(), Value::String("strict_command_rejected".into()));
                    object.insert("error".into(), Value::String(error));
                }
            }

            if matches!(response["status"].as_str(), Some("accepted" | "running")) {
                batch.active = Some(step_id);
                let result = batch_result(&batch, "running", true);
                persist_batch(&self.descriptor.session_id, &batch)?;
                self.batches.push_back(batch);
                trim_batches(&mut self.batches);
                return Ok(result);
            }

            batch.active = None;
            if let Some(state) = response.get("state") {
                batch.state = Some(state.clone());
            }
            if let Some(changes) = response["changes"].as_array() {
                batch
                    .changes
                    .extend(changes.iter().cloned().map(|mut change| {
                        if let Some(object) = change.as_object_mut() {
                            object.insert("step".into(), Value::from(batch.next));
                        }
                        change
                    }));
            }
            let mut compact = response.clone();
            if let Some(object) = compact.as_object_mut() {
                object.remove("state");
                object.remove("changes");
                object.insert("step".into(), Value::from(batch.next));
                object.insert("op".into(), batch.steps[batch.next]["op"].clone());
            }
            batch.results.push(compact);
            batch.next += 1;

            if response["ok"].as_bool() == Some(false)
                || matches!(response["status"].as_str(), Some("failed" | "cancelled"))
            {
                let result = batch_result(
                    &batch,
                    response["status"].as_str().unwrap_or("failed"),
                    false,
                );
                batch.terminal = Some(result.clone());
                persist_batch(&self.descriptor.session_id, &batch)?;
                self.batches.push_back(batch);
                trim_batches(&mut self.batches);
                return Ok(result);
            }
            if response["status"] == "waiting_input"
                && batch
                    .steps
                    .get(batch.next)
                    .and_then(|step| step["op"].as_str())
                    .is_none_or(|op| !matches!(op, "input" | "cancel"))
            {
                let result = batch_result(&batch, "waiting_input", true);
                batch.terminal = Some(result.clone());
                persist_batch(&self.descriptor.session_id, &batch)?;
                self.batches.push_back(batch);
                trim_batches(&mut self.batches);
                return Ok(result);
            }
            persist_batch(&self.descriptor.session_id, &batch)?;
        }
    }
}

fn batch_step_id(id: &str, step: usize) -> String {
    let hash = id
        .as_bytes()
        .iter()
        .fold(0xcbf29ce484222325u64, |hash, byte| {
            (hash ^ u64::from(*byte)).wrapping_mul(0x100000001b3)
        });
    format!("batch-{hash:016x}-{step}")
}

fn strict_command_error(response: &Value) -> Option<String> {
    if response["status"] == "waiting_input" {
        Some("command did not finish and is waiting for input".to_string())
    } else if response["result"]["unconsumed"]
        .as_array()
        .is_some_and(|tokens| !tokens.is_empty())
    {
        Some(format!(
            "command left unconsumed tokens: {}",
            response["result"]["unconsumed"]
        ))
    } else {
        None
    }
}

fn batch_result(batch: &BatchExecution, status: &str, ok: bool) -> Value {
    if batch.request["op"] == "run_script" {
        let added_entities = batch
            .changes
            .iter()
            .filter(|change| change["kind"] == "Added")
            .filter_map(|change| change["handle"].as_str())
            .collect::<HashSet<_>>()
            .len();
        let failed_result = (!ok).then(|| batch.results.last().cloned()).flatten();
        return json!({
            "ok":ok,
            "status":status,
            "request_id":batch.id,
            "code":failed_result.as_ref().and_then(|result| result.get("code")).cloned(),
            "error":failed_result.as_ref().and_then(|result| result.get("error")).cloned(),
            "completed_commands":batch.next,
            "successful_commands":if ok { batch.next } else { batch.next.saturating_sub(1) },
            "failed_command":(!ok).then(|| batch.next.saturating_sub(1)),
            "total_commands":batch.steps.len(),
            "next_command":(batch.next < batch.steps.len()).then_some(batch.next),
            "added_entities":added_entities,
            "failed_result":failed_result,
            "changes":batch.changes,
            "state":batch.state
        });
    }
    json!({
        "ok":ok,
        "status":status,
        "request_id":batch.id,
        "completed_steps":batch.next,
        "total_steps":batch.steps.len(),
        "next_step":(batch.next < batch.steps.len()).then_some(batch.next),
        "results":batch.results,
        "changes":batch.changes,
        "state":batch.state
    })
}

fn trim_batches(batches: &mut VecDeque<BatchExecution>) {
    while batches.len() > 64 {
        batches.pop_front();
    }
}

fn client<'a>(
    clients: &'a mut HashMap<String, GuiClient>,
    session_id: &str,
) -> Result<&'a mut GuiClient, String> {
    if !clients.contains_key(session_id) {
        clients.insert(session_id.into(), GuiClient::connect(session_id)?);
    }
    Ok(clients.get_mut(session_id).expect("client inserted"))
}

fn shutdown_owned_session(
    clients: &mut HashMap<String, GuiClient>,
    session_id: &str,
    request: &Value,
) -> Result<Value, String> {
    let root = Path::new(required_string(request, "owned_root")?);
    if !root.is_absolute() {
        return Err("owned_root must be an existing absolute directory".into());
    }
    let root = root.canonicalize().map_err(|_| "owned_root does not exist".to_string())?;
    if !root.is_dir() {
        return Err("owned_root must be a directory".into());
    }
    let expected_pid = request["process_id"].as_u64()
        .and_then(|value| u32::try_from(value).ok())
        .ok_or_else(|| "process_id is required".to_string())?;
    let expected_start = request["process_started_at_unix_ms"].as_u64()
        .ok_or_else(|| "process_started_at_unix_ms is required".to_string())?;
    let expected_executable = Path::new(required_string(request, "executable_path")?)
        .canonicalize().map_err(|_| "executable_path is absent".to_string())?;
    let own_executable = std::env::current_exe().map_err(|error| error.to_string())?
        .canonicalize().map_err(|error| error.to_string())?;
    if expected_executable != own_executable {
        return Err("Requested executable is not this MCP server build".into());
    }
    let request_id = required_string(request, "request_id")?;
    {
        let launch = LAUNCH.get_or_init(|| Mutex::new(LaunchState::default()))
            .lock().map_err(|_| "Launch state lock poisoned".to_string())?;
        if launch.closed.as_ref().is_some_and(|closed|
            closed.session_id == session_id && closed.process_id == expected_pid
                && closed.started_at_unix_ms == expected_start
                && closed.request_id == request_id && closed.owned_root == root) {
            return Ok(json!({"ok":true,"status":"completed","request_id":request_id,
                "result":{"closed":true,"process_id":expected_pid}}));
        }
        if launch.child.as_ref().map(Child::id) != Some(expected_pid) {
            return Err("Session is not owned by this MCP process".into());
        }
    }
    let gui = client(clients, session_id)?;
    if gui.descriptor.pid != Some(expected_pid) {
        return Err("Selected session PID changed".into());
    }
    if gui.descriptor.started_at_unix_ms != Some(expected_start) {
        return Err("Selected session creation time changed".into());
    }
    let descriptor_executable = gui.descriptor.executable.as_deref()
        .ok_or_else(|| "Selected session has no executable identity".to_string())?;
    if Path::new(descriptor_executable).canonicalize()
        .map_err(|_| "Selected session executable is absent".to_string())? != own_executable {
        return Err("Selected session executable changed".into());
    }
    let state = gui.request(json!({"op":"state"}), 0.0)?;
    if state["modal"].as_str().is_some()
        || state["command"].as_object().is_some()
    {
        return Ok(json!({"ok":false,"status":"waiting_user","code":"editor_busy",
            "error":"Close the modal or active command before shutdown"}));
    }
    let documents = state["documents"].as_array()
        .ok_or_else(|| "GUI state has no documents array".to_string())?;
    for document in documents {
        if document["dirty"].as_bool() != Some(false) {
            return Ok(json!({"ok":false,"status":"waiting_user","code":"dirty_document",
                "error":"Save or explicitly close every dirty document before shutdown"}));
        }
        if let Some(path) = document["path"].as_str() {
            let path = Path::new(path).canonicalize()
                .map_err(|_| "Open document path cannot be verified".to_string())?;
            if !path.starts_with(&root) {
                return Ok(json!({"ok":false,"status":"waiting_user","code":"foreign_document",
                    "error":"Open document lies outside owned_root"}));
            }
        }
    }
    // The GUI can exit before its reply reaches MCP; inspect only the owned
    // child afterward. Never send another shutdown with a new ID here.
    if let Ok(response) = gui.request(json!({"op":"shutdown","request_id":request_id,
        "owned_root":root.to_string_lossy()}), 0.0) {
        if response["ok"].as_bool() == Some(false) {
            return Ok(response);
        }
    }
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        let mut launch = LAUNCH.get_or_init(|| Mutex::new(LaunchState::default()))
            .lock().map_err(|_| "Launch state lock poisoned".to_string())?;
        if let Some(child) = launch.child.as_mut() {
            if child.try_wait().map_err(|error| error.to_string())?.is_some() {
                launch.child = None;
                launch.started = None;
                launch.failure = None;
                launch.closed = Some(ClosedSession { session_id: session_id.into(),
                    process_id: expected_pid, started_at_unix_ms: expected_start,
                    request_id: request_id.into(), owned_root: root.clone() });
                return Ok(json!({"ok":true,"status":"completed","request_id":request_id,
                    "result":{"closed":true,"process_id":expected_pid}}));
            }
        }
        drop(launch);
        if Instant::now() >= deadline {
            return Ok(json!({"ok":false,"status":"waiting_user","code":"shutdown_unconfirmed",
                "error":"Owned GUI did not exit; inspect its state without retrying shutdown",
                "request_id":request_id}));
        }
        thread::sleep(Duration::from_millis(100));
    }
}

fn required_string<'a>(arguments: &'a Value, key: &str) -> Result<&'a str, String> {
    arguments[key]
        .as_str()
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("Missing {key}"))
}

fn validate_execute_request(request: &Value, op: &str) -> Result<(), String> {
    let missing = |field: &str, example: &str| {
        Err(format!(
            "Missing {field} for {op}. Example request: {example}"
        ))
    };
    match op {
        "run_script" => validate_run_script(request),
        "batch" => {
            let steps = request["steps"].as_array().ok_or_else(|| {
                r#"Missing steps for batch. Example request: {"op":"batch","request_id":"draw-1","steps":[{"op":"run","cmd":"LINE 0,0 10,0"}]}"#.to_string()
            })?;
            if steps.is_empty() || steps.len() > MAX_BATCH_STEPS {
                return Err(format!(
                    "batch steps must contain 1 to {MAX_BATCH_STEPS} operations"
                ));
            }
            for (index, step) in steps.iter().enumerate() {
                let step = step
                    .as_object()
                    .ok_or_else(|| format!("batch step {index} must be an object"))?;
                if step.contains_key("request_id") {
                    return Err(format!(
                        "batch step {index} must omit request_id; the batch assigns idempotency keys"
                    ));
                }
                let step = Value::Object(step.clone());
                let step_op = step["op"]
                    .as_str()
                    .ok_or_else(|| format!("batch step {index} is missing op"))?;
                if !BATCH_STEP_OPS.contains(&step_op) {
                    return Err(format!("Unknown operation {step_op} in batch step {index}"));
                }
                validate_execute_request(&step, step_op)
                    .map_err(|error| format!("batch step {index}: {error}"))?;
            }
            Ok(())
        }
        "open" if request["path"].as_str().is_none_or(str::is_empty) => {
            missing("path", r#"{"op":"open","path":"/path/drawing.dxf"}"#)
        }
        "activate" if request["document_id"].as_u64().is_none() => {
            missing("document_id", r#"{"op":"activate","document_id":2}"#)
        }
        "run" | "start" if request["cmd"].as_str().is_none_or(str::is_empty) => {
            missing("cmd", r#"{"op":"run","cmd":"LINE 0,0 10,10"}"#)
        }
        "input" => match request["kind"].as_str() {
            Some("text") => Ok(()),
            Some("token")
                if request["text"]
                    .as_str()
                    .is_some_and(|value| !value.is_empty()) =>
            {
                Ok(())
            }
            Some("token") => missing("text", r#"{"op":"input","kind":"token","text":"C"}"#),
            Some("point")
                if request["point"].as_array().is_some_and(|values| {
                    values.len() == 3 && values.iter().all(Value::is_number)
                }) =>
            {
                Ok(())
            }
            Some("point") => missing(
                "point",
                r#"{"op":"input","kind":"point","point":[0,0,0],"space":"wcs"}"#,
            ),
            Some("entity" | "structure")
                if request["handle"]
                    .as_str()
                    .is_some_and(|value| !value.is_empty())
                    && request["point"].as_array().is_some_and(|values| {
                        values.len() == 3 && values.iter().all(Value::is_number)
                    }) =>
            {
                Ok(())
            }
            Some("entity" | "structure") => missing(
                "handle and point",
                r#"{"op":"input","kind":"entity","handle":"2A","point":[0,0,0]}"#,
            ),
            Some("selection" | "enter") => Ok(()),
            Some(kind) => Err(format!(
                "Unknown input kind {kind}. Use text, token, point, entity, structure, selection or enter"
            )),
            None => missing("kind", r#"{"op":"input","kind":"point","point":[0,0,0]}"#),
        },
        "property"
            if request["field"].as_str().is_none_or(str::is_empty)
                || request.get("value").is_none() =>
        {
            missing(
                "field or value",
                r#"{"op":"property","field":"color","value":1}"#,
            )
        }
        "set_properties"
            if request["collection"].as_str().is_none_or(str::is_empty)
                || request["updates"].as_array().is_none_or(Vec::is_empty) =>
        {
            missing(
                "collection or updates",
                r#"{"op":"set_properties","collection":"entities","handle":"2A","updates":[{"path":"/common/layer","value":"Walls"}]}"#,
            )
        }
        "action" => match request["name"].as_str() {
            Some(name) if crate::app::automation_action_names().contains(&name) => Ok(()),
            Some(name) => Err(format!(
                "Unknown action {name}. Call ocs_read commands to list actions"
            )),
            None => missing("name", r#"{"op":"action","name":"zoom_extents"}"#),
        },
        "shutdown_owned_session" if request["owned_root"].as_str().is_none()
            || request["process_id"].as_u64().is_none()
            || request["process_started_at_unix_ms"].as_u64().is_none()
            || request["executable_path"].as_str().is_none() => {
            missing("owned_root/process_id/process_started_at_unix_ms/executable_path",
                r#"{"op":"shutdown_owned_session","owned_root":"/run","process_id":123,"process_started_at_unix_ms":123,"executable_path":"/path/OpenCADStudio"}"#)
        }
        "embed_image" if request["path"].as_str().is_none_or(str::is_empty) => {
            missing(
                "path",
                r#"{"op":"embed_image","path":"/path/logo.png","at":[0,0,0],"width":100}"#,
            )
        }
        "save_verified" if request["path"].as_str().is_none_or(str::is_empty) => {
            missing(
                "path",
                r#"{"op":"save_verified","request_id":"deliver-1","path":"/absolute/output.dwg","target_version":"2018"}"#,
            )
        }
        _ => Ok(()),
    }
}

fn validate_run_script(request: &Value) -> Result<(), String> {
    let commands = request["commands"].as_array().ok_or_else(|| {
        r#"Missing commands for run_script. Example request: {"op":"run_script","request_id":"walls-1","commands":["LINE 0,0 10,0","LINE 10,0 10,10"]}"#.to_string()
    })?;
    if commands.is_empty() || commands.len() > MAX_SCRIPT_COMMANDS {
        return Err(format!(
            "run_script commands must contain 1 to {MAX_SCRIPT_COMMANDS} command lines"
        ));
    }
    let mut total = 0usize;
    for (index, value) in commands.iter().enumerate() {
        let command = value
            .as_str()
            .ok_or_else(|| format!("run_script command {index} must be a string"))?;
        if command.trim().is_empty() {
            return Err(format!("run_script command {index} must not be empty"));
        }
        if command.contains(['\r', '\n', '\0']) {
            return Err(format!(
                "run_script command {index} must be exactly one command line"
            ));
        }
        if command.len() > MAX_SCRIPT_COMMAND_BYTES {
            return Err(format!(
                "run_script command {index} exceeds {MAX_SCRIPT_COMMAND_BYTES} bytes"
            ));
        }
        total = total.saturating_add(command.len());
    }
    if total > MAX_SCRIPT_BYTES {
        return Err(format!(
            "run_script commands exceed the {MAX_SCRIPT_BYTES}-byte payload budget"
        ));
    }
    Ok(())
}

fn expand_run_script(mut request: Value) -> Value {
    let commands = request["commands"].as_array().cloned().unwrap_or_default();
    let steps = commands
        .into_iter()
        .map(|cmd| json!({"op":"run","cmd":cmd}))
        .collect::<Vec<_>>();
    request
        .as_object_mut()
        .expect("validated run_script request is an object")
        .insert("steps".into(), Value::Array(steps));
    request
}

fn compact_state(state: &Value) -> Value {
    let mut compact = Map::new();
    for key in [
        "session_id",
        "document_id",
        "revision",
        "geometry_revision",
        "camera_revision",
        "selection",
        "command",
        "modal",
        "event_cursor",
        "operation",
    ] {
        if let Some(value) = state.get(key) {
            compact.insert(key.into(), value.clone());
        }
    }
    Value::Object(compact)
}

fn response_handles(response: &Value) -> Vec<String> {
    let mut handles = Vec::new();
    if let Some(changes) = response["changes"].as_array() {
        for handle in changes
            .iter()
            .filter_map(|change| change["handle"].as_str())
        {
            if !handles.iter().any(|value| value == handle) {
                handles.push(handle.to_owned());
            }
        }
    }
    handles
}

fn shape_execute_response(
    mut response: Value,
    detail: &str,
    gui: &mut GuiClient,
) -> Result<Value, String> {
    if detail == "changed_entities" {
        let handles = response_handles(&response);
        if !handles.is_empty() {
            let entities = gui.request(
                json!({"op":"query","handles":handles,"detail":"geometry","limit":MAX_SCRIPT_COMMANDS * 100}),
                30.0,
            )?;
            if let Some(object) = response.as_object_mut() {
                object.insert("changed_entities".into(), entities["entities"].clone());
            }
        }
    }
    if detail != "full" {
        if let Some(state) = response.get("state").cloned() {
            if let Some(object) = response.as_object_mut() {
                object.insert("state".into(), compact_state(&state));
            }
        }
    }
    Ok(response)
}

fn call_tool(
    name: &str,
    arguments: &Value,
    clients: &mut HashMap<String, GuiClient>,
) -> Result<Value, String> {
    match name {
        "ocs_sessions" => {
            let launch = arguments["launch_if_none"].as_bool().unwrap_or(true);
            sessions(launch)
        }
        "ocs_read" => {
            let session_id = required_string(arguments, "ocs_session_id")?;
            let op = arguments["op"].as_str().unwrap_or("state");
            if !READ_OPS.contains(&op) {
                return Err("Use ocs_execute for mutations".into());
            }
            let mut request = arguments["parameters"]
                .as_object()
                .cloned()
                .unwrap_or_default();
            request.insert("op".into(), Value::String(op.into()));
            let gui = client(clients, session_id)?;
            if op == "operation" {
                if let Some(id) = request.get("request_id").and_then(Value::as_str) {
                    if let Some(batch) = gui.resume_batch_operation(id)? {
                        return Ok(batch);
                    }
                }
            }
            gui.request(Value::Object(request), 30.0)
        }
        "ocs_execute" => {
            let session_id = required_string(arguments, "ocs_session_id")?;
            let mut request = arguments["request"]
                .as_object()
                .cloned()
                .map(Value::Object)
                .ok_or_else(|| "Missing request object".to_string())?;
            let op = required_string(&request, "op")?.to_owned();
            if !EXECUTE_OPS.contains(&op.as_str()) {
                return Err(format!("Unknown mutation operation: {op}"));
            }
            let request_id = required_string(&request, "request_id")?;
            if request_id.len() > 128 {
                return Err("request_id must not exceed 128 bytes".into());
            }
            validate_execute_request(&request, &op)?;
            if op == "shutdown_owned_session" {
                return shutdown_owned_session(clients, session_id, &request);
            }
            if op == "run_script" {
                request = expand_run_script(request);
            }
            let wait = arguments["wait_seconds"].as_f64().unwrap_or(30.0);
            let detail = arguments["response_detail"].as_str().unwrap_or("compact");
            let gui = client(clients, session_id)?;
            let response = if matches!(op.as_str(), "batch" | "run_script") {
                gui.execute_batch(request, wait)?
            } else {
                gui.request(request, wait)?
            };
            shape_execute_response(response, detail, gui)
        }
        "ocs_capture" => {
            let session_id = required_string(arguments, "ocs_session_id")?;
            let path = std::env::temp_dir().join(format!("ocs-capture-{}.png", random_id()?));
            let scope = arguments["scope"].as_str().unwrap_or("viewport");
            let max_dimension = arguments["max_dimension"].as_u64().unwrap_or(1600);
            let result = client(clients, session_id)?
                .request(json!({"op":"capture","path":path.to_string_lossy(),"scope":scope,"max_dimension":max_dimension}), 30.0)?;
            if result["ok"].as_bool() != Some(true)
                || result["status"].as_str() != Some("completed")
            {
                return Err(result.to_string());
            }
            let bytes = std::fs::read(&path).map_err(|error| error.to_string())?;
            let _ = std::fs::remove_file(path);
            Ok(json!({"$image":BASE64.encode(bytes)}))
        }
        _ => Err(format!("Unknown tool: {name}")),
    }
}

fn batch_step_schema() -> Value {
    json!({
        "type":"object",
        "properties":{
            "op":{"type":"string","enum":BATCH_STEP_OPS},
            "document_id":{"type":"integer","minimum":0},
            "cmd":{"type":"string","minLength":1},
            "path":{"type":"string","minLength":1},
            "target_format":{"type":"string","enum":["dwg","dxf"]},
            "target_version":{"type":"string","enum":["R14","2000","2004","2007","2010","2013","2018","AC1014","AC1015","AC1018","AC1021","AC1024","AC1027","AC1032"]},
            "allow_lossy":{"type":"boolean","default":false},
            "kind":{"type":"string","enum":["text","token","point","entity","structure","selection","enter"]},
            "text":{"type":"string"},
            "point":{"type":"array","items":{"type":"number"},"minItems":3,"maxItems":3},
            "space":{"type":"string","enum":["wcs","ucs","relative"]},
            "handle":{"type":"string"},
            "handles":{"type":"array","items":{"type":"string"}},
            "type":{"type":"string"},
            "layer":{"type":"string"},
            "clear":{"type":"boolean"},
            "field":{"type":"string"},
            "value":{"description":"New property value; its JSON type must match the property kind.","anyOf":[{"type":"string"},{"type":"number"},{"type":"boolean"},{"type":"object"},{"type":"array"},{"type":"null"}]},
            "collection":{"type":"string"},
            "updates":{"type":"array","minItems":1,"items":{"type":"object","properties":{"path":{"type":"string","pattern":"^/"},"value":{},"expected":{}},"required":["path","value"],"additionalProperties":false}},
            "name":{"type":"string","enum":crate::app::automation_action_names()}
        },
        "required":["op"],
        "additionalProperties":false
    })
}

fn execute_request_schema() -> Value {
    let handle = json!({
        "type":"string",
        "pattern":"^(0[xX])?[0-9A-Fa-f]+$",
        "description":"Entity handle returned by ocs_read entities or state selection."
    });
    let point = json!({
        "type":"array","items":{"type":"number"},"minItems":3,"maxItems":3,
        "description":"Finite [x,y,z] coordinates."
    });
    json!({
        "type":"object",
        "properties":{
            "op":{"type":"string","enum":EXECUTE_OPS,"description":"Semantic editor operation."},
            "request_id":{"type":"string","minLength":1,"maxLength":128,"description":"Caller-generated idempotency key. Reuse it only when retrying the identical request."},
            "document_id":{"type":"integer","minimum":0,"description":"Target document from current state."},
            "revision":{"type":"integer","minimum":0,"description":"Expected edit revision from current state."},
            "geometry_revision":{"type":"integer","minimum":0,"description":"Expected geometry revision when geometry state matters."},
            "camera_revision":{"type":"integer","minimum":0,"description":"Expected camera revision when view state matters."},
            "selection":{"type":"array","items":handle.clone(),"description":"Expected selected handles from current state."},
            "cmd":{"type":"string","minLength":1,"description":"Command name followed by its prompt answers separated by spaces. Points use x,y or x,y,z; option answers use their token. Read command details first when unsure.","examples":["LINE 0,0 10,10","CIRCLE 5,5 3","PLINE 0,0 10,0 10,10 C"]},
            "path":{"type":"string","minLength":1,"description":"Absolute path: drawing for open or save, image file for embed_image."},
            "target_format":{"type":"string","enum":["dwg","dxf"],"description":"Explicit output format; it must match the path extension."},
            "target_version":{"type":"string","enum":["R14","2000","2004","2007","2010","2013","2018","AC1014","AC1015","AC1018","AC1021","AC1024","AC1027","AC1032"],"description":"Explicit CAD output version. Omit only to preserve the document version."},
            "allow_lossy":{"type":"boolean","default":false,"description":"Acknowledge dropping unsupported passthrough records reported by audit."},
            "overwrite":{"type":"boolean","default":false,"description":"For save_verified only: replace an existing destination."},
            "at":{"type":"array","items":{"type":"number"},"minItems":2,"maxItems":3,"description":"World [x,y] or [x,y,z] placement corner for embed_image (picture grows up-right)."},
            "width":{"type":"number","exclusiveMinimum":0,"description":"World width for embed_image; height follows the image aspect ratio. Defaults to pixel_width/100."},
            "kind":{"type":"string","enum":["text","token","point","entity","structure","selection","enter"],"description":"Input kind listed in state.command.accepts."},
            "text":{"type":"string","description":"Free text or one option/value token."},
            "point":point,
            "space":{"type":"string","enum":["wcs","ucs","relative"],"default":"wcs","description":"Coordinate space for point input."},
            "handle":handle.clone(),
            "handles":{"type":"array","items":handle,"description":"Entity handles to select."},
            "type":{"type":"string","description":"Entity type filter for select."},
            "layer":{"type":"string","description":"Layer filter for select."},
            "clear":{"type":"boolean","description":"Clear the current selection before applying select filters."},
            "field":{"type":"string","minLength":1,"description":"Property id returned by ocs_read properties."},
            "value":{"description":"New property value; its JSON type must match the property kind.","anyOf":[{"type":"string"},{"type":"number"},{"type":"boolean"},{"type":"object"},{"type":"array"},{"type":"null"}]},
            "collection":{"type":"string","description":"Record collection returned by ocs_read records."},
            "updates":{"type":"array","minItems":1,"description":"Atomic, type-checked property replacements. Paths are RFC 6901 JSON Pointers relative to record.properties.","items":{"type":"object","properties":{"path":{"type":"string","pattern":"^/"},"value":{},"expected":{"description":"Optional compare-and-set value."}},"required":["path","value"],"additionalProperties":false}},
            "name":{"type":"string","enum":crate::app::automation_action_names(),"description":"UI action returned by ocs_read commands."},
            "steps":{"type":"array","minItems":1,"maxItems":MAX_BATCH_STEPS,"description":"Sequential editor operations executed with fresh state and idempotency keys. Execution stops at the first failure; completed_steps says what committed.","items":batch_step_schema()},
            "commands":{"type":"array","minItems":1,"maxItems":MAX_SCRIPT_COMMANDS,"description":"Complete one-line CAD commands for a resumable high-volume drawing script. Read command manifests first; points use x,y or x,y,z.","items":{"type":"string","minLength":1,"maxLength":MAX_SCRIPT_COMMAND_BYTES}},
            "strict":{"type":"boolean","default":true,"description":"For run_script, fail closed when a command waits for more input or leaves unconsumed tokens."},
            "owned_root":{"type":"string","minLength":1,"description":"Canonical root allowed for every open document during owned shutdown."},
            "process_id":{"type":"integer","minimum":1},
            "process_started_at_unix_ms":{"type":"integer","minimum":1},
            "executable_path":{"type":"string","minLength":1}
        },
        "required":["op","request_id"],
        "additionalProperties":false,
        "oneOf":[
            {"properties":{"op":{"const":"new"}}},
            {"properties":{"op":{"const":"open"}},"required":["path"]},
            {"properties":{"op":{"const":"activate"}},"required":["document_id"]},
            {"properties":{"op":{"const":"run"}},"required":["cmd"]},
            {"properties":{"op":{"const":"start"}},"required":["cmd"]},
            {"properties":{"op":{"const":"input"}},"required":["kind"],"oneOf":[
                {"properties":{"kind":{"const":"text"}}},
                {"properties":{"kind":{"const":"token"}},"required":["text"]},
                {"properties":{"kind":{"const":"point"}},"required":["point"]},
                {"properties":{"kind":{"const":"entity"}},"required":["handle","point"]},
                {"properties":{"kind":{"const":"structure"}},"required":["handle","point"]},
                {"properties":{"kind":{"const":"selection"}}},
                {"properties":{"kind":{"const":"enter"}}}
            ]},
            {"properties":{"op":{"const":"cancel"}}},
            {"properties":{"op":{"const":"undo"}}},
            {"properties":{"op":{"const":"redo"}}},
            {"properties":{"op":{"const":"select"}}},
            {"properties":{"op":{"const":"property"}},"required":["field","value"]},
            {"properties":{"op":{"const":"set_properties"}},"required":["collection","updates"]},
            {"properties":{"op":{"const":"action"}},"required":["name"]},
            {"properties":{"op":{"const":"embed_image"}},"required":["path"]},
            {"properties":{"op":{"const":"save"}}},
            {"properties":{"op":{"const":"save_verified"}},"required":["path"]},
            {"properties":{"op":{"const":"stop"}}},
            {"properties":{"op":{"const":"batch"}},"required":["steps","document_id","revision"]},
            {"properties":{"op":{"const":"run_script"}},"required":["commands","document_id","revision"]},
            {"properties":{"op":{"const":"shutdown_owned_session"}},"required":["owned_root","process_id","process_started_at_unix_ms","executable_path"]}
        ]
    })
}

fn read_output_schema() -> Value {
    json!({
        "type":"object",
        "properties":{
            "ok":{"type":"boolean"},"status":{"type":"string"},"code":{"type":"string"},
            "error":{"anyOf":[{"type":"string"},{"type":"null"}]},"document_id":{"type":"integer"},
            "revision":{"type":"integer"},"geometry_revision":{"type":"integer"},
            "camera_revision":{"type":"integer"}
        },
        "required":["ok"],"additionalProperties":true
    })
}

fn execute_output_schema() -> Value {
    json!({
        "type":"object",
        "properties":{
            "ok":{"type":"boolean"},
            "status":{"type":"string","enum":["accepted","running","waiting_input","waiting_user","completed","cancelled","failed"]},
            "request_id":{"type":"string"},"code":{"type":"string"},"error":{"anyOf":[{"type":"string"},{"type":"null"}]},
            "result":{"type":"object"},"changes":{"anyOf":[{"type":"array"},{"type":"null"}]},"state":{"type":"object"}
        },
        "required":["ok"],"additionalProperties":true
    })
}

fn tool_definitions() -> Value {
    json!([
        {
            "name":"ocs_sessions",
            "description":"List real OpenCADStudio GUI sessions and documents. Launch the installed editor if none is running.",
            "inputSchema":{"type":"object","properties":{"launch_if_none":{"type":"boolean","default":true,"description":"Launch OpenCADStudio when no live session exists."}},"additionalProperties":false},
            "outputSchema":{"type":"object","properties":{"ok":{"type":"boolean"},"status":{"type":"string","enum":["absent","starting","ready","failed"]},"reason":{"type":"string"},"retry_after_ms":{"type":"integer"},"deadline_remaining_ms":{"type":"integer"},"result":{"type":"array","items":{"type":"object","properties":{"ok":{"const":true},"session_id":{"type":"string"},"document_id":{"type":"integer"},"revision":{"type":"integer"},"selection":{"type":"array","items":{"type":"string"}},"documents":{"type":"array"}},"required":["ok","session_id","document_id","revision","selection","documents"],"additionalProperties":true}}},"required":["ok","status","result"],"additionalProperties":false},
            "annotations":{"title":"List OCS sessions","readOnlyHint":false,"destructiveHint":false,"idempotentHint":true,"openWorldHint":false}
        },
        {
            "name":"ocs_read",
            "description":"Discover capabilities and record schemas, or read state, complete database records, command manifests, entities, properties, kernel measurements and spatial relationships, history, events or operation status from a live OCS session.",
            "inputSchema":{"type":"object","properties":{"ocs_session_id":{"type":"string","minLength":1,"description":"Value of session_id returned by ocs_sessions."},"op":{"type":"string","enum":READ_OPS,"default":"state"},"parameters":{"type":"object","description":"Operation-specific filters.","properties":{"name":{"type":"string","description":"Command name or record name."},"search":{"type":"string","description":"Case-insensitive command or record-type search."},"document_id":{"type":"integer","minimum":0},"path":{"type":"string","description":"Optional intended output path for audit; extension determines target format."},"target_format":{"type":"string","enum":["dwg","dxf"],"description":"Intended output format for audit."},"target_version":{"type":"string","enum":["R14","2000","2004","2007","2010","2013","2018","AC1014","AC1015","AC1018","AC1021","AC1024","AC1027","AC1032"],"description":"Intended CAD output version for audit."},"collection":{"type":"string","description":"Record collection, all for records, or omit to discover collections and schema types."},"handle":{"type":"string"},"handles":{"type":"array","items":{"type":"string"},"description":"Exact entity or record handles."},"type":{"type":"string","description":"Entity or record type filter; for record_schema, returns its complete type graph and writable field paths."},"layer":{"type":"string","description":"Layer name filter for query."},"detail":{"type":"string","enum":["summary","geometry","full"],"default":"geometry","description":"Entity detail returned by query."},"fields":{"type":"array","items":{"type":"string"},"description":"Return only these entity fields plus handle."},"paths":{"type":"array","items":{"type":"string"},"description":"Project RFC 6901 JSON Pointer paths relative to record.properties."},"where":{"type":"array","description":"All property filters must match.","items":{"type":"object","properties":{"path":{"type":"string"},"op":{"type":"string","enum":["eq","ne","lt","lte","gt","gte","contains","starts_with","ends_with","in","exists","not_exists"],"default":"eq"},"value":{}},"required":["path"],"additionalProperties":false}},"near":{"type":"array","items":{"type":"number"},"minItems":2,"maxItems":3,"description":"Rank planar curves by exact kernel distance to this world XY point."},"contains_point":{"type":"array","items":{"type":"number"},"minItems":2,"maxItems":3,"description":"Return closed planar curves containing this world XY point."},"bounds":{"type":"array","items":{"type":"number"},"minItems":4,"maxItems":4,"description":"Filter entities whose world XY bounds overlap [min_x,min_y,max_x,max_y]."},"intersections":{"type":"array","items":{"type":"string"},"minItems":2,"maxItems":2,"description":"Return exact kernel intersections between two planar curve handles."},"after":{"type":"integer","minimum":0,"description":"Event cursor."},"request_id":{"type":"string","description":"Operation id to query."},"offset":{"type":"integer","minimum":0},"limit":{"type":"integer","minimum":1,"maximum":10000}},"additionalProperties":false}},"required":["ocs_session_id"],"additionalProperties":false},
            "outputSchema":read_output_schema(),
            "annotations":{"title":"Read OCS state","readOnlyHint":true,"destructiveHint":false,"idempotentHint":true,"openWorldHint":false}
        },
        {
            "name":"ocs_execute",
            "description":"Execute semantic OCS actions. Use current state fields and a unique request_id. Use run for one complete command, run_script for a long strict sequence, batch to mix operation types, or start plus input for guided steps. accepted, running and waiting_input are not completion.",
            "inputSchema":{"type":"object","properties":{"ocs_session_id":{"type":"string","minLength":1,"description":"Value of session_id returned by ocs_sessions."},"request":execute_request_schema(),"wait_seconds":{"type":"number","minimum":0,"maximum":60,"default":30,"description":"Total time to wait for completion before returning."},"response_detail":{"type":"string","enum":["compact","changed_entities","full"],"default":"compact","description":"compact returns only state needed for the next edit; changed_entities also returns current geometry for changed handles; full preserves the complete editor state."}},"required":["ocs_session_id","request"],"additionalProperties":false},
            "outputSchema":execute_output_schema(),
            "annotations":{"title":"Execute OCS action","readOnlyHint":false,"destructiveHint":true,"idempotentHint":true,"openWorldHint":false}
        },
        {
            "name":"ocs_capture",
            "description":"Capture the actual current OCS drawing viewport or window as a bounded PNG for visual verification.",
            "inputSchema":{"type":"object","properties":{"ocs_session_id":{"type":"string","minLength":1,"description":"Value of session_id returned by ocs_sessions."},"scope":{"type":"string","enum":["viewport","window"],"default":"viewport","description":"Capture only the drawing viewport by default, or the complete application window."},"max_dimension":{"type":"integer","minimum":256,"maximum":4096,"default":1600,"description":"Resize the longest image edge to at most this many pixels."}},"required":["ocs_session_id"],"additionalProperties":false},
            "annotations":{"title":"Capture OCS window","readOnlyHint":true,"destructiveHint":false,"idempotentHint":true,"openWorldHint":false}
        }
    ])
}

fn tool_result(value: Value) -> Value {
    if let Some(image) = value.get("$image").and_then(Value::as_str) {
        return json!({"content":[{"type":"image","data":image,"mimeType":"image/png"}]});
    }
    let structured = if value.is_object() {
        value.clone()
    } else {
        json!({"result":value.clone()})
    };
    json!({
        "content":[{"type":"text","text":value.to_string()}],
        "structuredContent":structured,
        "isError":value["ok"].as_bool() == Some(false)
    })
}

fn error_result(message: impl ToString) -> Value {
    let message = message.to_string();
    json!({
        "content":[{"type":"text","text":message.clone()}],
        "structuredContent":{"ok":false,"status":"failed","code":"invalid_arguments","error":message,"retryable":false},
        "isError":true
    })
}

fn response(id: Value, result: Value) -> Value {
    json!({"jsonrpc":"2.0","id":id,"result":result})
}

fn server_info() -> Value {
    json!({"name":"OpenCADStudio","title":"Open CAD Studio","version":env!("OCS_APP_VERSION")})
}

fn modern_request(params: &Value) -> bool {
    params["_meta"]["io.modelcontextprotocol/protocolVersion"].as_str()
        == Some(MODERN_PROTOCOL_VERSION)
}

fn supports_tasks(params: &Value) -> bool {
    params["_meta"]["io.modelcontextprotocol/clientCapabilities"]["extensions"]
        ["io.modelcontextprotocol/tasks"]
        .is_object()
}

fn task_value(task: &McpTask, status: &str) -> Value {
    let mut value = json!({
        "resultType":"complete",
        "taskId":task.id,
        "status":status,
        "createdAt":task.created_at,
        "lastUpdatedAt":task.last_updated_at,
        "ttlMs":3_600_000,
        "pollIntervalMs":250
    });
    if let Some(result) = &task.result {
        value["result"] = result.clone();
    }
    if let Some(error) = &task.error {
        value["error"] = error.clone();
    }
    value
}

fn poll_task(task: &mut McpTask, clients: &mut HashMap<String, GuiClient>) -> Value {
    if task.result.is_some() {
        return task_value(task, "completed");
    }
    if task.error.is_some() {
        return task_value(task, "failed");
    }
    task.last_updated_at = iso8601_now();
    let mut arguments = task.arguments.clone();
    arguments["wait_seconds"] = Value::from(0);
    match call_tool(&task.name, &arguments, clients) {
        Ok(value) if matches!(value["status"].as_str(), Some("accepted" | "running")) => {
            task_value(task, "working")
        }
        Ok(value) => {
            task.result = Some(tool_result(value));
            task_value(task, "completed")
        }
        Err(error) => {
            task.error = Some(json!({"code":-32000,"message":error}));
            task_value(task, "failed")
        }
    }
}

fn protocol_result(mut result: Value, modern: bool, cacheable: bool) -> Value {
    if modern {
        let object = result
            .as_object_mut()
            .expect("MCP results are JSON objects");
        object
            .entry("resultType")
            .or_insert_with(|| Value::String("complete".into()));
        object.insert(
            "_meta".into(),
            json!({"io.modelcontextprotocol/serverInfo":server_info()}),
        );
        if cacheable {
            object.insert("ttlMs".into(), Value::from(CACHE_TTL_MS));
            object.insert("cacheScope".into(), Value::String("public".into()));
        }
    }
    result
}

fn rpc_error(id: Value, code: i64, message: impl ToString) -> Value {
    json!({"jsonrpc":"2.0","id":id,"error":{"code":code,"message":message.to_string()}})
}

fn unsupported_protocol(id: Value, requested: &str) -> Value {
    json!({
        "jsonrpc":"2.0",
        "id":id,
        "error":{
            "code":-32022,
            "message":format!("Unsupported protocol version: {requested}"),
            "data":{"requested":requested,"supported":[MODERN_PROTOCOL_VERSION,PROTOCOL_VERSION]}
        }
    })
}

fn handle_message(
    message: Value,
    clients: &mut HashMap<String, GuiClient>,
    tasks: &mut TaskStore,
) -> Option<Value> {
    let id = message.get("id").cloned();
    let method = message.get("method").and_then(Value::as_str)?;
    if id.is_none() {
        return None;
    }
    let id = id.unwrap();
    let params = message.get("params").cloned().unwrap_or_else(|| json!({}));
    if let Some(requested) = params["_meta"]["io.modelcontextprotocol/protocolVersion"].as_str() {
        if requested != MODERN_PROTOCOL_VERSION {
            return Some(unsupported_protocol(id, requested));
        }
    }
    let modern = modern_request(&params);
    Some(match method {
        "initialize" if modern => rpc_error(id, -32601, "Method not found: initialize"),
        "initialize" => {
            let requested = params["protocolVersion"]
                .as_str()
                .unwrap_or(PROTOCOL_VERSION);
            let protocol =
                if ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"].contains(&requested) {
                    requested
                } else {
                    PROTOCOL_VERSION
                };
            response(
                id,
                json!({
                    "protocolVersion":protocol,
                    "capabilities":{"tools":{"listChanged":false}},
                    "serverInfo":server_info(),
                    "instructions":INSTRUCTIONS
                }),
            )
        }
        "server/discover" => response(
            id,
            protocol_result(
                json!({
                    "supportedVersions":[MODERN_PROTOCOL_VERSION,PROTOCOL_VERSION],
                    "capabilities":{"tools":{},"extensions":{"io.modelcontextprotocol/tasks":{}}},
                    "instructions":INSTRUCTIONS
                }),
                true,
                true,
            ),
        ),
        "ping" => response(id, protocol_result(json!({}), modern, false)),
        "tools/list" => response(
            id,
            protocol_result(json!({"tools":tool_definitions()}), modern, true),
        ),
        "tools/call" => {
            let Some(name) = params["name"].as_str() else {
                return Some(rpc_error(id, -32602, "Missing tool name"));
            };
            let arguments = params
                .get("arguments")
                .cloned()
                .unwrap_or_else(|| json!({}));
            let called = call_tool(name, &arguments, clients);
            if modern && supports_tasks(&params) {
                if let Ok(value) = &called {
                    if matches!(value["status"].as_str(), Some("accepted" | "running")) {
                        let task_id =
                            random_id().unwrap_or_else(|_| format!("task-{}", iso8601_now()));
                        let now = iso8601_now();
                        tasks.insert(McpTask {
                            id: task_id.clone(),
                            name: name.to_owned(),
                            arguments,
                            created_at: now.clone(),
                            last_updated_at: now,
                            result: None,
                            error: None,
                        });
                        return Some(response(
                            id,
                            protocol_result(
                                json!({
                                    "resultType":"task",
                                    "taskId":task_id,
                                    "status":"working",
                                    "statusMessage":"OCS operation is running.",
                                    "createdAt":tasks.tasks.back().unwrap().created_at,
                                    "lastUpdatedAt":tasks.tasks.back().unwrap().last_updated_at,
                                    "ttlMs":3_600_000,
                                    "pollIntervalMs":250
                                }),
                                true,
                                false,
                            ),
                        ));
                    }
                }
            }
            let result = called.map(tool_result).unwrap_or_else(error_result);
            response(id, protocol_result(result, modern, false))
        }
        "tasks/get" if modern && supports_tasks(&params) => {
            let Some(task_id) = params["taskId"].as_str() else {
                return Some(rpc_error(id, -32602, "Missing taskId"));
            };
            let Some(task) = tasks.get_mut(task_id) else {
                return Some(rpc_error(id, -32602, "Unknown or expired taskId"));
            };
            response(id, protocol_result(poll_task(task, clients), true, false))
        }
        "tasks/update" if modern && supports_tasks(&params) => {
            let Some(task_id) = params["taskId"].as_str() else {
                return Some(rpc_error(id, -32602, "Missing taskId"));
            };
            if tasks.get_mut(task_id).is_none() {
                return Some(rpc_error(id, -32602, "Unknown or expired taskId"));
            }
            response(id, protocol_result(json!({}), true, false))
        }
        "tasks/cancel" if modern && supports_tasks(&params) => {
            let Some(task_id) = params["taskId"].as_str() else {
                return Some(rpc_error(id, -32602, "Missing taskId"));
            };
            if tasks.get_mut(task_id).is_none() {
                return Some(rpc_error(id, -32602, "Unknown or expired taskId"));
            }
            response(id, protocol_result(json!({}), true, false))
        }
        _ => rpc_error(id, -32601, format!("Method not found: {method}")),
    })
}

/// Run the MCP stdio loop until the client closes stdin.
pub fn run() {
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut output = stdout.lock();
    let mut clients = HashMap::new();
    let mut tasks = TaskStore::default();
    for line in stdin.lock().lines() {
        let response = match line {
            Ok(line) if !line.trim().is_empty() => match serde_json::from_str::<Value>(&line) {
                Ok(message) => handle_message(message, &mut clients, &mut tasks),
                Err(error) => Some(rpc_error(Value::Null, -32700, error)),
            },
            Ok(_) => None,
            Err(error) => {
                eprintln!("MCP input error: {error}");
                break;
            }
        };
        if let Some(response) = response {
            if writeln!(output, "{response}")
                .and_then(|_| output.flush())
                .is_err()
            {
                break;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn batch_operation_exposes_progress_without_replaying() {
        let mut gui = GuiClient {
            descriptor: Descriptor { session_id: "fixture".into(), port: 0, token: String::new(), pid: None, executable: None, started_at_unix_ms: None },
            state: json!({}),
            client_id: "fixture-client".into(),
            batches: VecDeque::new(),
        };
        gui.batches.push_back(BatchExecution {
            id: "script-1".into(),
            request: json!({"op":"run_script","request_id":"script-1"}),
            steps: vec![json!({"op":"run"}), json!({"op":"run"})],
            next: 1,
            active: Some("step-2".into()),
            results: vec![json!({"ok":true,"status":"completed"})],
            changes: vec![],
            state: None,
            terminal: None,
        });
        let progress = gui.batch_operation("script-1").unwrap();
        assert_eq!(progress["status"], "running");
        assert_eq!(progress["completed_commands"], 1);
        assert_eq!(progress["next_command"], 1);
        assert_eq!(gui.batches[0].next, 1);
        gui.batches[0].terminal = Some(json!({"ok":false,"status":"failed", "request_id":"script-1", "completed_commands":1}));
        assert_eq!(gui.batch_operation("script-1").unwrap()["status"], "failed");
    }

    #[test]
    fn discovery_is_bounded_with_many_unresponsive_descriptors() {
        use std::net::TcpListener;
        use std::sync::atomic::AtomicBool;
        let directory = std::env::current_dir().unwrap().join("target/mcp-discovery-tests")
            .join(random_id().unwrap());
        std::fs::create_dir_all(&directory).unwrap();
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        listener.set_nonblocking(true).unwrap();
        let done = std::sync::Arc::new(AtomicBool::new(false));
        let worker_done = done.clone();
        let worker = thread::spawn(move || {
            let mut held = Vec::new();
            while !worker_done.load(Ordering::Relaxed) {
                match listener.accept() {
                    Ok((stream, _)) => held.push(stream),
                    Err(error) if error.kind() == io::ErrorKind::WouldBlock =>
                        thread::sleep(Duration::from_millis(2)),
                    Err(_) => break,
                }
            }
        });
        for count in [0, 1, 20, 100] {
            let existing = directory.read_dir().unwrap().count();
            for index in existing..count {
                std::fs::write(directory.join(format!("{index:03}.json")),
                    json!({"session_id":format!("dead-{index}"),"port":port,"token":"fixture"}).to_string()).unwrap();
            }
            let began = Instant::now();
            assert!(descriptors_in(&directory).unwrap().is_empty());
            let elapsed = began.elapsed();
            if count == 100 {
                eprintln!("dead_descriptor_count={count} discovery_ms={:.1}", elapsed.as_secs_f64() * 1000.0);
                assert!(elapsed < Duration::from_secs(8), "100 stale descriptors took {elapsed:?}");
            }
        }
        done.store(true, Ordering::Relaxed);
        worker.join().unwrap();
        for entry in directory.read_dir().unwrap() {
            std::fs::remove_file(entry.unwrap().path()).unwrap();
        }
        std::fs::remove_dir(directory).unwrap();
    }

    #[test]
    fn shutdown_rejects_unowned_process_before_connecting() {
        let request = json!({"op":"shutdown_owned_session","request_id":"close-1",
            "owned_root":std::env::current_dir().unwrap().to_string_lossy(),
            "process_id":u32::MAX,"process_started_at_unix_ms":1,
            "executable_path":std::env::current_exe().unwrap().to_string_lossy()});
        assert!(validate_execute_request(&request, "shutdown_owned_session").is_ok());
        let error = shutdown_owned_session(&mut HashMap::new(),
            "0123456789abcdef0123456789abcdef", &request).unwrap_err();
        assert!(error.contains("not owned"));
    }

    #[test]
    fn batch_journal_recovers_active_step_without_persisting_tokens() {
        let base = std::env::current_dir().unwrap().join("target/mcp-journal-tests");
        std::fs::create_dir_all(&base).unwrap();
        let run_root = base.join(random_id().unwrap());
        let dir = run_root
            .join("long-component-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
            .join("long-component-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
            .join("long-component-cccccccccccccccccccccccccccccccccccccccccccccccc");
        let mut batch = BatchExecution {
            id: "fixture-batch".into(),
            request: json!({"op":"run_script","request_id":"fixture-batch",
                "document_id":2,"revision":0,"steps":[{"op":"run","cmd":"LINE 0,0 1,0"}]}),
            steps: vec![json!({"op":"run","cmd":"LINE 0,0 1,0"})],
            next: 0,
            active: None,
            results: Vec::new(), changes: Vec::new(), state: None, terminal: None,
        };
        persist_batch_in(&dir, "session-1", &batch).unwrap();
        batch.active = Some(batch_step_id(&batch.id, 0));
        persist_batch_in(&dir, "session-1", &batch).unwrap();
        let loaded = load_batches_in(&dir, "session-1").unwrap();
        assert_eq!(loaded.len(), 1);
        assert_eq!(loaded[0].active, batch.active);
        assert_eq!(loaded[0].next, 0);
        assert!(load_batches_in(&dir, "another-session").unwrap().is_empty());
        assert_eq!(load_batch_in(&dir, "session-1", &batch.id).unwrap().unwrap().active,
            batch.active);
        let journal = std::fs::read_to_string(batch_journal_path(&dir, "session-1", &batch.id)).unwrap();
        assert!(!journal.contains("token"));
        std::fs::write(batch_journal_path(&dir, "session-1", &batch.id), b"corrupt").unwrap();
        assert!(load_batch_in(&dir, "session-1", &batch.id).unwrap_err().contains("corrupt"));
        assert!(run_root.canonicalize().unwrap().starts_with(base.canonicalize().unwrap()));
        std::fs::remove_dir_all(run_root).unwrap();
    }

    #[test]
    fn advertises_the_shared_tools() {
        let tools = tool_definitions();
        let names: Vec<_> = tools
            .as_array()
            .unwrap()
            .iter()
            .map(|tool| tool["name"].as_str().unwrap())
            .collect();
        assert_eq!(
            names,
            ["ocs_sessions", "ocs_read", "ocs_execute", "ocs_capture"]
        );
        assert_eq!(tools[0]["annotations"]["readOnlyHint"], false);
        for tool in [&tools[1], &tools[2], &tools[3]] {
            assert!(
                tool["inputSchema"]["properties"]
                    .get("session_id")
                    .is_none()
            );
            assert!(
                tool["inputSchema"]["required"]
                    .as_array()
                    .unwrap()
                    .contains(&json!("ocs_session_id"))
            );
        }
        assert_eq!(
            tools[2]["inputSchema"]["properties"]["request"]["required"],
            json!(["op", "request_id"])
        );
        assert_eq!(
            tools[2]["inputSchema"]["properties"]["request"]["oneOf"]
                .as_array()
                .unwrap()
                .len(),
            EXECUTE_OPS.len()
        );
        assert_eq!(
            tools[2]["inputSchema"]["properties"]["request"]["properties"]["steps"]["maxItems"],
            MAX_BATCH_STEPS
        );
        assert_eq!(
            tools[2]["inputSchema"]["properties"]["request"]["properties"]["commands"]["maxItems"],
            MAX_SCRIPT_COMMANDS
        );
        assert_eq!(
            tools[2]["inputSchema"]["properties"]["response_detail"]["default"],
            "compact"
        );
        assert_eq!(
            tools[3]["inputSchema"]["properties"]["scope"]["default"],
            "viewport"
        );
        assert_eq!(
            tools[2]["inputSchema"]["properties"]["request"]["properties"]["cmd"]["examples"][0],
            "LINE 0,0 10,10"
        );
        assert!(READ_OPS.contains(&"capabilities"));
        assert!(READ_OPS.contains(&"records"));
        assert!(READ_OPS.contains(&"record_schema"));
        assert!(READ_OPS.contains(&"audit"));
        assert!(EXECUTE_OPS.contains(&"set_properties"));
        assert!(EXECUTE_OPS.contains(&"save_verified"));
        assert!(EXECUTE_OPS.contains(&"run_script"));
        assert_eq!(
            tools[2]["inputSchema"]["properties"]["request"]["properties"]
                ["target_version"]["enum"][0],
            "R14"
        );
        assert_eq!(
            tools[1]["inputSchema"]["properties"]["parameters"]["properties"]["where"]["items"]["properties"]
                ["op"]["enum"],
            json!([
                "eq",
                "ne",
                "lt",
                "lte",
                "gt",
                "gte",
                "contains",
                "starts_with",
                "ends_with",
                "in",
                "exists",
                "not_exists"
            ])
        );
        assert_eq!(
            tools[2]["inputSchema"]["properties"]["request"]["properties"]["updates"]["items"]["required"],
            json!(["path", "value"])
        );
        assert!(tools[0].get("outputSchema").is_some());
        assert!(tools[1].get("outputSchema").is_some());
        assert!(tools[2].get("outputSchema").is_some());
    }

    #[test]
    fn negotiates_and_lists_tools() {
        let mut clients = HashMap::new();
        let initialized = handle_message(
            json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25"}}),
            &mut clients,
            &mut TaskStore::default(),
        )
        .unwrap();
        assert_eq!(initialized["result"]["protocolVersion"], "2025-11-25");
        assert!(
            initialized["result"]["instructions"]
                .as_str()
                .unwrap()
                .contains("geometry kernel")
        );

        let listed = handle_message(
            json!({"jsonrpc":"2.0","id":2,"method":"tools/list"}),
            &mut clients,
            &mut TaskStore::default(),
        )
        .unwrap();
        assert_eq!(listed["result"]["tools"].as_array().unwrap().len(), 4);
        assert!(listed["result"].get("ttlMs").is_none());
        assert!(listed["result"].get("resultType").is_none());
    }

    #[test]
    fn supports_modern_stateless_discovery() {
        let mut clients = HashMap::new();
        let discovered = handle_message(
            json!({"jsonrpc":"2.0","id":"discover","method":"server/discover","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}),
            &mut clients,
            &mut TaskStore::default(),
        )
        .unwrap();
        assert_eq!(discovered["result"]["resultType"], "complete");
        assert_eq!(discovered["result"]["ttlMs"], CACHE_TTL_MS);
        assert_eq!(discovered["result"]["cacheScope"], "public");
        assert_eq!(discovered["result"]["supportedVersions"][0], "2026-07-28");
        assert!(
            discovered["result"]["capabilities"]["extensions"]["io.modelcontextprotocol/tasks"]
                .is_object()
        );
        assert_eq!(
            discovered["result"]["_meta"]["io.modelcontextprotocol/serverInfo"]["name"],
            "OpenCADStudio"
        );

        let listed = handle_message(
            json!({"jsonrpc":"2.0","id":"tools","method":"tools/list","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}),
            &mut clients,
            &mut TaskStore::default(),
        )
        .unwrap();
        assert_eq!(listed["result"]["resultType"], "complete");
        assert_eq!(listed["result"]["ttlMs"], CACHE_TTL_MS);
        assert_eq!(listed["result"]["cacheScope"], "public");
    }

    #[test]
    fn read_tool_rejects_mutations_before_connecting() {
        let mut clients = HashMap::new();
        let called = handle_message(
            json!({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"ocs_read","arguments":{"ocs_session_id":"missing","op":"save"}}}),
            &mut clients,
            &mut TaskStore::default(),
        )
        .unwrap();
        assert_eq!(called["result"]["isError"], true);
    }

    #[test]
    fn rejects_unknown_modern_protocol_versions() {
        let mut clients = HashMap::new();
        let rejected = handle_message(
            json!({"jsonrpc":"2.0","id":4,"method":"tools/list","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2099-01-01"}}}),
            &mut clients,
            &mut TaskStore::default(),
        )
        .unwrap();
        assert_eq!(rejected["error"]["code"], -32022);
        assert_eq!(rejected["error"]["data"]["requested"], "2099-01-01");
        assert_eq!(
            rejected["error"]["data"]["supported"][0],
            MODERN_PROTOCOL_VERSION
        );
    }

    #[test]
    fn execute_requires_a_visible_request_id() {
        let mut clients = HashMap::new();
        let called = handle_message(
            json!({"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"ocs_execute","arguments":{"ocs_session_id":"missing","request":{"op":"undo"}}}}),
            &mut clients,
            &mut TaskStore::default(),
        )
        .unwrap();
        assert_eq!(called["result"]["isError"], true);
        assert!(
            called["result"]["structuredContent"]["error"]
                .as_str()
                .unwrap()
                .contains("request_id")
        );
    }

    #[test]
    fn execute_errors_explain_missing_operation_fields() {
        let mut clients = HashMap::new();
        let called = handle_message(
            json!({"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"ocs_execute","arguments":{"ocs_session_id":"missing","request":{"op":"run","request_id":"run-1"}}}}),
            &mut clients,
            &mut TaskStore::default(),
        )
        .unwrap();
        assert_eq!(called["result"]["isError"], true);
        assert_eq!(
            called["result"]["structuredContent"]["code"],
            "invalid_arguments"
        );
        let error = called["result"]["structuredContent"]["error"]
            .as_str()
            .unwrap();
        assert!(error.contains("Missing cmd"), "{error}");
        assert!(error.contains("LINE 0,0 10,10"), "{error}");
    }

    #[test]
    fn validates_batch_steps_and_compacts_state() {
        let batch = json!({
            "op":"batch",
            "request_id":"draw",
            "steps":[{"op":"run","cmd":"LINE 0,0 10,0"},{"op":"run","cmd":"CIRCLE 5,5 2"}]
        });
        assert!(validate_execute_request(&batch, "batch").is_ok());
        let invalid = json!({
            "op":"batch",
            "request_id":"draw",
            "steps":[{"op":"run","request_id":"nested","cmd":"LINE 0,0 10,0"}]
        });
        assert!(
            validate_execute_request(&invalid, "batch")
                .unwrap_err()
                .contains("omit request_id")
        );

        let compact = compact_state(&json!({
            "session_id":"s","document_id":3,"revision":4,"geometry_revision":5,
            "camera_revision":6,"selection":[],"command":null,"documents":[1,2,3],
            "camera":{"distance":100.0},"event_cursor":7
        }));
        assert_eq!(compact["revision"], 4);
        assert!(compact.get("camera").is_none());
        assert!(compact.get("documents").is_none());
    }

    #[test]
    fn validates_and_expands_strict_run_script() {
        let script = json!({
            "op":"run_script",
            "request_id":"walls",
            "commands":["LINE 0,0 10,0","CIRCLE 5,5 2"]
        });
        assert!(validate_execute_request(&script, "run_script").is_ok());
        let expanded = expand_run_script(script);
        assert_eq!(expanded["op"], "run_script");
        assert_eq!(expanded["steps"].as_array().unwrap().len(), 2);
        assert_eq!(expanded["steps"][1]["op"], "run");
        assert_eq!(expanded["steps"][1]["cmd"], "CIRCLE 5,5 2");

        let multiline = json!({
            "op":"run_script",
            "request_id":"bad",
            "commands":["LINE 0,0 1,1\nCIRCLE 0,0 1"]
        });
        assert!(validate_run_script(&multiline)
            .unwrap_err()
            .contains("exactly one command line"));
    }

    #[test]
    fn strict_script_rejects_incomplete_and_overtyped_commands() {
        assert!(strict_command_error(&json!({
            "status":"waiting_input",
            "result":{"unconsumed":[]}
        })).unwrap().contains("waiting for input"));
        assert!(strict_command_error(&json!({
            "status":"completed",
            "result":{"unconsumed":["9"]}
        })).unwrap().contains("unconsumed tokens"));
        assert!(strict_command_error(&json!({
            "status":"completed",
            "result":{"unconsumed":[]}
        })).is_none());
    }

    #[test]
    fn script_summary_counts_unique_added_handles() {
        let batch = BatchExecution {
            id: "script".into(),
            request: json!({"op":"run_script"}),
            steps: vec![json!({"op":"run"}), json!({"op":"run"})],
            next: 2,
            active: None,
            results: Vec::new(),
            changes: vec![
                json!({"handle":"A","kind":"Added","step":0}),
                json!({"handle":"A","kind":"Added","step":0}),
                json!({"handle":"B","kind":"Added","step":1}),
                json!({"handle":"C","kind":"Modified","step":1}),
            ],
            state: None,
            terminal: None,
        };
        let result = batch_result(&batch, "completed", true);
        assert_eq!(result["added_entities"], 2);
        assert_eq!(result["successful_commands"], 2);
        assert!(result["failed_command"].is_null());
    }

    #[test]
    fn task_metadata_uses_the_modern_shape() {
        let now = iso8601_now();
        assert_eq!(now.len(), 20);
        assert!(now.ends_with('Z'));
        let task = McpTask {
            id: "task".into(),
            name: "ocs_execute".into(),
            arguments: json!({}),
            created_at: now.clone(),
            last_updated_at: now,
            result: None,
            error: None,
        };
        let value = task_value(&task, "working");
        assert_eq!(value["resultType"], "complete");
        assert_eq!(value["status"], "working");
        assert_eq!(value["pollIntervalMs"], 250);
    }

    #[test]
    fn gui_failures_are_mcp_errors() {
        let result = tool_result(json!({
            "ok":false,
            "status":"failed",
            "code":"stale_state",
            "error":"Refresh state before editing"
        }));
        assert_eq!(result["isError"], true);
        assert_eq!(result["structuredContent"]["code"], "stale_state");
    }
}
