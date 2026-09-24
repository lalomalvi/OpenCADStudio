//! Private local discovery and a bounded GUI message queue.
use super::{session_id, Envelope, Reply};
use iced::futures::{channel::mpsc, Stream};
use serde_json::{json, Value};
use std::{
    io::{BufRead, BufReader, Read, Seek, SeekFrom, Write},
    net::TcpListener,
    path::PathBuf,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    },
    time::{Duration, SystemTime, UNIX_EPOCH},
};

fn heartbeat_writer(dir: PathBuf, id: String, pid: u32, started_at_unix_ms: Option<u64>) {
    let path = dir.join(format!("{id}.heartbeat"));
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)] {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let Ok(mut file) = options.open(path) else { return; };
    loop {
        let updated_at_unix_ms = u64::try_from(SystemTime::now().duration_since(UNIX_EPOCH)
            .unwrap_or_default().as_millis()).unwrap_or(u64::MAX);
        let wire = json!({"session_id":id,"pid":pid,"started_at_unix_ms":started_at_unix_ms,
            "updated_at_unix_ms":updated_at_unix_ms}).to_string();
        if file.set_len(0).is_err() || file.seek(SeekFrom::Start(0)).is_err()
            || file.write_all(wire.as_bytes()).is_err() || file.flush().is_err() {
            break;
        }
        std::thread::sleep(Duration::from_secs(2));
    }
}

#[cfg(windows)]
fn process_started_at_unix_ms() -> Option<u64> {
    use windows_sys::Win32::{Foundation::FILETIME, System::Threading::{GetCurrentProcess, GetProcessTimes}};
    let mut created: FILETIME = unsafe { std::mem::zeroed() };
    let mut exited: FILETIME = unsafe { std::mem::zeroed() };
    let mut kernel: FILETIME = unsafe { std::mem::zeroed() };
    let mut user: FILETIME = unsafe { std::mem::zeroed() };
    if unsafe { GetProcessTimes(GetCurrentProcess(), &mut created, &mut exited, &mut kernel, &mut user) } == 0 {
        return None;
    }
    let ticks = (u64::from(created.dwHighDateTime) << 32) | u64::from(created.dwLowDateTime);
    ticks.checked_sub(116_444_736_000_000_000).map(|value| value / 10_000)
}

#[cfg(not(windows))]
fn process_started_at_unix_ms() -> Option<u64> { None }

pub(in crate::app) fn subscribe() -> iced::Subscription<Envelope> {
    iced::Subscription::run(worker)
}

fn worker() -> impl Stream<Item = Envelope> {
    iced::stream::channel(32, |sender| async move {
        std::thread::spawn(move || {
            if let Err(error) = listen(sender) {
                eprintln!("Automation unavailable: {error}");
            }
        });
        iced::futures::future::pending::<()>().await;
    })
}

fn listen(sender: mpsc::Sender<Envelope>) -> std::io::Result<()> {
    let listener = TcpListener::bind(("127.0.0.1", 0))?;
    let dir = crate::config::config_dir()
        .ok_or_else(|| std::io::Error::other("No user directory"))?
        .join("automation");
    std::fs::create_dir_all(&dir)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&dir, std::fs::Permissions::from_mode(0o700))?;
    }
    let mut secret = [0u8; 32];
    getrandom::fill(&mut secret).map_err(std::io::Error::other)?;
    let token: String = secret.iter().map(|v| format!("{v:02x}")).collect();
    let started_at_unix_ms = process_started_at_unix_ms();
    let descriptor = json!({"protocol":1,"session_id":session_id(),"pid":std::process::id(),
        "started_at_unix_ms":started_at_unix_ms,"port":listener.local_addr()?.port(),
        "token":token,"executable":std::env::current_exe()?.to_string_lossy()});
    let path = dir.join(format!("{}.json", session_id()));
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(&path)?;
    write!(file, "{descriptor}")?;
    drop(file);
    let heartbeat_dir = dir.clone();
    let heartbeat_id = session_id().to_owned();
    std::thread::spawn(move || heartbeat_writer(heartbeat_dir, heartbeat_id,
        std::process::id(), started_at_unix_ms));
    let clients = Arc::new(AtomicUsize::new(0));
    for stream in listener.incoming().flatten() {
        if clients.fetch_add(1, Ordering::SeqCst) >= 8 {
            clients.fetch_sub(1, Ordering::SeqCst);
            continue;
        }
        let clients = clients.clone();
        let mut sender = sender.clone();
        let token = token.clone();
        std::thread::spawn(move || {
            let _ = stream.set_read_timeout(Some(Duration::from_secs(15)));
            let _ = stream.set_write_timeout(Some(Duration::from_secs(15)));
            if let Ok(write_half) = stream.try_clone() {
                let mut reader = BufReader::new(stream);
                let mut writer = write_half;
                // One bounded request per connection; operation polling reconnects.
                let mut line = String::new();
                if reader.by_ref().take(1_048_577).read_line(&mut line).is_ok()
                    && line.len() <= 1_048_576
                    && line.ends_with('\n')
                {
                    if let Ok(mut request) = serde_json::from_str::<Value>(&line) {
                        if request["token"].as_str() == Some(token.as_str()) {
                            if let Some(object) = request.as_object_mut() {
                                object.remove("token");
                            }
                            let (reply, response) = std::sync::mpsc::channel();
                            let result = if sender
                                .try_send(Envelope {
                                    request,
                                    reply: Reply::Native(reply),
                                })
                                .is_ok()
                            {
                                response.recv_timeout(Duration::from_secs(15)).unwrap_or_else(|_| json!({"ok":false,"code":"response_timeout","error":"Query operation status with the same request_id; execution may continue."}))
                            } else {
                                json!({"ok":false,"code":"busy","error":"GUI queue full"})
                            };
                            let _ = writeln!(writer, "{result}");
                        }
                    }
                }
            }
            clients.fetch_sub(1, Ordering::SeqCst);
        });
    }
    let _ = std::fs::remove_file(path);
    Ok(())
}
