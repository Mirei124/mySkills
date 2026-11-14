//! Private desktop owner, supervised same-binary input worker and JSON transport.
use crate::{
    action::Action,
    capture::{Capture, monotonic_ns},
    desktop::{Desktop, Output},
    portal::Portal,
    probe,
};
use anyhow::{Context, Result, bail, ensure};
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::HashMap,
    fs::{File, OpenOptions},
    io::{Read, Write},
    os::{
        fd::AsRawFd,
        unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt},
    },
    path::{Path, PathBuf},
    sync::{
        Arc, Mutex as StdMutex,
        atomic::{AtomicU32, Ordering},
    },
    time::{Duration, Instant},
};
use tokio::{
    io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader},
    net::{UnixListener, UnixStream},
    process::{Child, ChildStdin, ChildStdout, Command},
    sync::{Mutex, watch},
};

const LIMIT: u64 = 131_072;
fn token(prefix: &str) -> Result<String> {
    let mut bytes = [0u8; 16];
    File::open("/dev/urandom")?.read_exact(&mut bytes)?;
    Ok(format!(
        "{prefix}{}",
        bytes.iter().map(|v| format!("{v:02x}")).collect::<String>()
    ))
}
pub fn runtime() -> Result<PathBuf> {
    let base = PathBuf::from(std::env::var("XDG_RUNTIME_DIR").context("RUNTIME_UNAVAILABLE")?);
    ensure!(base.is_absolute(), "UNSAFE_RUNTIME_DIRECTORY");
    let display = std::env::var("WAYLAND_DISPLAY").context("WAYLAND_UNAVAILABLE")?;
    let hash = format!("{:x}", Sha256::digest(display.as_bytes()));
    let root = base.join(format!("wf-computer-{}", &hash[..16]));
    match std::fs::create_dir(&root) {
        Ok(()) => std::fs::set_permissions(&root, std::fs::Permissions::from_mode(0o700))?,
        Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {}
        Err(e) => return Err(e.into()),
    }
    let metadata = std::fs::symlink_metadata(&root)?;
    // SAFETY: getuid has no arguments or preconditions.
    ensure!(
        metadata.is_dir()
            && metadata.uid() == unsafe { libc::getuid() }
            && metadata.mode() & 0o077 == 0,
        "UNSAFE_RUNTIME_DIRECTORY"
    );
    Ok(root)
}
pub(crate) struct Lock(File);
impl Lock {
    pub(crate) fn acquire(root: &Path) -> Result<Self> {
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .mode(0o600)
            .open(root.join("lock"))?;
        // SAFETY: flock is called on a live owned file descriptor.
        ensure!(
            unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } == 0,
            "SESSION_BUSY"
        );
        Ok(Self(file))
    }
}
impl Drop for Lock {
    fn drop(&mut self) {
        let _ = unsafe { libc::flock(self.0.as_raw_fd(), libc::LOCK_UN) };
    }
}
fn publish(path: &Path, value: &Value) -> Result<()> {
    let temp = path.with_file_name(token("publish-")?);
    let result = (|| {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&temp)?;
        file.write_all(&serde_json::to_vec(value)?)?;
        file.sync_all()?;
        std::fs::rename(&temp, path)?;
        Ok(())
    })();
    if result.is_err() {
        let _ = std::fs::remove_file(&temp);
    }
    result
}
async fn read_line<R: tokio::io::AsyncBufRead + Unpin>(reader: &mut R) -> Result<Value> {
    let mut bytes = vec![];
    reader.take(LIMIT + 1).read_until(b'\n', &mut bytes).await?;
    ensure!(!bytes.is_empty(), "CONNECTION_CLOSED");
    ensure!(
        bytes.len() as u64 <= LIMIT && bytes.last() == Some(&b'\n'),
        "REQUEST_TOO_LARGE"
    );
    serde_json::from_slice(&bytes).context("INVALID_JSON")
}
async fn write_line<W: tokio::io::AsyncWrite + Unpin>(writer: &mut W, value: &Value) -> Result<()> {
    let mut bytes = serde_json::to_vec(value)?;
    bytes.push(b'\n');
    writer.write_all(&bytes).await?;
    writer.flush().await?;
    Ok(())
}
struct Worker {
    child: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
}
impl Worker {
    async fn open(output: &str) -> Result<(Self, Value)> {
        let mut command = Command::new(std::env::current_exe()?);
        configure_child_lifetime(&mut command, false);
        let mut child = command
            .args(["worker", "--output", output])
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::null())
            .kill_on_drop(true)
            .spawn()?;
        let input = child.stdin.take().context("INPUT_START_FAILED")?;
        let output = BufReader::new(child.stdout.take().context("INPUT_START_FAILED")?);
        let mut worker = Self {
            child,
            input,
            output,
        };
        let ready = tokio::time::timeout(Duration::from_secs(5), read_line(&mut worker.output))
            .await
            .context("INPUT_START_TIMEOUT")??;
        ensure!(ready["status"] == "ready", "INPUT_START_FAILED");
        Ok((worker, ready))
    }
    async fn call(&mut self, value: Value) -> Result<Value> {
        write_line(&mut self.input, &value).await?;
        let response = tokio::time::timeout(Duration::from_secs(32), read_line(&mut self.output))
            .await
            .context("INPUT_RESPONSE_TIMEOUT")??;
        ensure!(
            response["status"] != "error",
            "{}",
            response["code"].as_str().unwrap_or("INPUT_FAILED")
        );
        Ok(response)
    }
    async fn close(&mut self) -> Result<()> {
        if self.child.try_wait()?.is_some() {
            return Ok(());
        }
        write_line(&mut self.input, &json!({"command":"stop"})).await?;
        match tokio::time::timeout(Duration::from_secs(3), self.child.wait()).await {
            Ok(status) => {
                ensure!(status?.success(), "INPUT_EXIT_FAILED");
                Ok(())
            }
            Err(_) => {
                self.child.kill().await?;
                self.child.wait().await?;
                bail!("INPUT_FORCE_TERMINATED")
            }
        }
    }
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Envelope {
    #[serde(default)]
    command: Option<String>,
    request_id: String,
    session_id: String,
    #[serde(default)]
    observation_id: Option<String>,
    action: Action,
}
struct Engine {
    root: PathBuf,
    id: String,
    portal: Option<Portal>,
    capture: Option<Arc<Capture>>,
    worker: Option<Worker>,
    output: Option<Output>,
    layout: Value,
    observation: Option<String>,
    width: u32,
    height: u32,
    paths: Vec<PathBuf>,
    cache: HashMap<String, (Value, Value)>,
    started: bool,
    bootstrap: bool,
}
impl Engine {
    fn new(root: PathBuf) -> Result<Self> {
        Ok(Self {
            root,
            id: token("s-")?,
            portal: None,
            capture: None,
            worker: None,
            output: None,
            layout: Value::Null,
            observation: None,
            width: 0,
            height: 0,
            paths: vec![],
            cache: HashMap::new(),
            started: false,
            bootstrap: false,
        })
    }
    async fn observe(&mut self) -> Result<Value> {
        let id = token("o-")?;
        let path = self.root.join(format!("{id}.png"));
        let saved = path.clone();
        let capture = self
            .capture
            .as_ref()
            .context("CAPTURE_UNAVAILABLE")?
            .clone();
        let after = monotonic_ns();
        self.paths.push(path.clone());
        let (width, height) =
            tokio::task::spawn_blocking(move || capture.observe(&saved, after)).await??;
        if self.width != 0 && (width, height) != (self.width, self.height) {
            self.observation = None;
            bail!("LAYOUT_CHANGED");
        }
        self.width = width;
        self.height = height;
        self.observation = Some(id.clone());
        Ok(
            json!({"status":"ok","session_id":self.id,"observation_id":id,"screenshot_path":path,"width":width,"height":height,"output":self.output.as_ref().context("OUTPUT_UNAVAILABLE")?.name,"layout_version":format!("{:x}",Sha256::digest(serde_json::to_vec(&self.layout)?)),"timestamp":std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)?.as_secs_f64()}),
        )
    }
    async fn prepare(
        &mut self,
        shared: &Arc<Shared>,
        name: Option<String>,
        auto_select: bool,
    ) -> Result<Value> {
        let (selected, layout) = tokio::task::spawn_blocking(move || {
            let desktop = Desktop::connect()?;
            let (_, output) = desktop.select(name.as_deref())?;
            validate_mapping(
                &desktop.state.outputs,
                &output,
                desktop
                    .state
                    .globals
                    .get("zwlr_virtual_pointer_manager_v1")
                    .copied()
                    .unwrap_or(0),
            )?;
            Ok::<_, anyhow::Error>((output, serde_json::to_value(desktop.state.outputs)?))
        })
        .await??;
        ensure!(
            selected.scale == 1 && selected.transform == 0,
            "UNSUPPORTED_OUTPUT_TRANSFORM_OR_SCALE"
        );
        self.output = Some(selected.clone());
        self.layout = layout;
        self.portal = Some(Portal::open().await?);
        let stream = if auto_select {
            let baseline = probe::selectors();
            probe::notify(
                "Computer Use is preparing desktop control",
                "Selecting the explicitly chosen display with one authorized click. Please avoid desktop input.",
            )
            .await?;
            self.started = true;
            self.bootstrap = true;
            tokio::try_join!(
                self.portal.as_ref().unwrap().stream(&selected),
                probe::choose_once(
                    selected.name.clone(),
                    baseline,
                    Some(shared.cancel_requested.clone())
                )
            )?
            .0
        } else {
            self.portal.as_ref().unwrap().stream(&selected).await?
        };
        let (worker, ready) = Worker::open(&selected.name).await?;
        ensure!(ready["layout"] == self.layout, "LAYOUT_CHANGED");
        shared.worker_pid.store(
            worker.child.id().context("INPUT_START_FAILED")?,
            Ordering::Release,
        );
        self.worker = Some(worker);
        if !self.started {
            probe::notify("Computer Use is controlling the desktop","Mouse and keyboard control is active. Please avoid interacting until the end notification.").await?;
            self.started = true;
        }
        let capture = Arc::new(Capture::new(stream.0, stream.1));
        *shared.capture.lock().unwrap() = Some(Arc::downgrade(&capture));
        self.capture = Some(capture);
        let mut first = self.observe().await?;
        first["status"] = json!("ready");
        first["selector_click_may_have_executed"] = json!(self.bootstrap);
        Ok(first)
    }
    async fn cleanup(&mut self) -> Vec<String> {
        let mut errors = vec![];
        if let Some(mut worker) = self.worker.take()
            && let Err(error) = worker.close().await
        {
            errors.push(format!("{error:#}"));
        }
        if let Some(capture) = self.capture.take() {
            capture.cancel();
            capture.synchronize();
            drop(capture);
        }
        if let Some(portal) = self.portal.take()
            && let Err(error) = portal.close().await
        {
            errors.push(format!("{error:#}"));
        }
        for path in self.paths.drain(..) {
            if let Err(error) = std::fs::remove_file(path)
                && error.kind() != std::io::ErrorKind::NotFound
            {
                errors.push("SCREENSHOT_CLEANUP_FAILED".into());
            }
        }
        errors
    }
}
struct Shared {
    engine: Mutex<Engine>,
    serial: Mutex<()>,
    snapshot: StdMutex<Value>,
    last: StdMutex<Instant>,
    stop: watch::Sender<bool>,
    finished: watch::Sender<Option<Value>>,
    reason: StdMutex<&'static str>,
    worker_pid: AtomicU32,
    capture: StdMutex<Option<std::sync::Weak<Capture>>>,
    cancel_requested: Arc<std::sync::atomic::AtomicBool>,
}
impl Shared {
    fn cancel(&self) {
        self.cancel_with_reason("normal");
    }
    fn cancel_with_reason(&self, reason: &'static str) {
        if *self.stop.borrow() {
            return;
        }
        *self.reason.lock().unwrap() = reason;
        self.snapshot.lock().unwrap()["status"] = json!("stopping");
        self.cancel_requested.store(true, Ordering::Release);
        self.stop.send_replace(true);
        let pid = self.worker_pid.load(Ordering::Acquire);
        if pid != 0 {
            let _ = unsafe { libc::kill(pid as i32, libc::SIGUSR1) };
        }
        if let Some(capture) = self
            .capture
            .lock()
            .unwrap()
            .as_ref()
            .and_then(|capture| capture.upgrade())
        {
            capture.cancel();
        }
    }
    async fn request(self: &Arc<Self>, request: Value) -> Result<Value> {
        ensure!(request.is_object(), "INVALID_REQUEST");
        if matches!(
            request.get("command").and_then(Value::as_str),
            Some("stop" | "status" | "capabilities" | "release_all")
        ) {
            ensure!(request.as_object().unwrap().len() == 1, "INVALID_FIELDS");
        }
        match request.get("command").and_then(Value::as_str) {
            Some("stop") => {
                self.cancel();
                let mut done = self.finished.subscribe();
                loop {
                    if let Some(value) = done.borrow().clone() {
                        return Ok(value);
                    }
                    done.changed().await?;
                }
            }
            Some("status") | Some("capabilities") => {
                return Ok(self.snapshot.lock().unwrap().clone());
            }
            _ => {}
        }
        let _serial = self.serial.lock().await;
        ensure!(!*self.stop.borrow(), "SESSION_STOPPING");
        ensure!(
            self.snapshot.lock().unwrap()["status"] == "active",
            "SESSION_PREPARING"
        );
        *self.last.lock().unwrap() = Instant::now();
        let mut engine = self.engine.lock().await;
        if request.get("command").and_then(Value::as_str) == Some("release_all") {
            engine
                .worker
                .as_mut()
                .context("INPUT_UNAVAILABLE")?
                .call(json!({"command":"release_all"}))
                .await?;
            return Ok(json!({"status":"released"}));
        }
        let envelope: Envelope =
            serde_json::from_value(request.clone()).context("INVALID_ENVELOPE")?;
        ensure!(
            envelope.command.as_deref().is_none_or(|v| v == "act"),
            "UNSUPPORTED_COMMAND"
        );
        ensure!(
            (1..=128).contains(&envelope.request_id.chars().count()),
            "INVALID_REQUEST_ID"
        );
        if let Some((original, response)) = engine.cache.get(&envelope.request_id) {
            ensure!(*original == request, "REQUEST_ID_CONFLICT");
            return Ok(response.clone());
        }
        ensure!(engine.cache.len() < 1000, "SESSION_REQUEST_LIMIT");
        ensure!(envelope.session_id == engine.id, "UNKNOWN_SESSION");
        envelope.action.validate()?;
        let executed = std::sync::atomic::AtomicBool::new(false);
        let mut stop = self.stop.subscribe();
        let result = tokio::select! {
            biased;
            _=stop.changed()=>Err(anyhow::anyhow!("ACTION_CANCELLED")),
            value=async{
                ensure!(envelope.observation_id==engine.observation,"STALE_OBSERVATION");
                if engine.observation.is_none(){ensure!(matches!(&envelope.action,Action::Screenshot{}),"STALE_OBSERVATION");}
                engine.capture.as_ref().context("CAPTURE_UNAVAILABLE")?.check()?;
                let layout=engine.worker.as_mut().context("INPUT_UNAVAILABLE")?.call(json!({"command":"layout"})).await?;
                if layout["layout"]!=engine.layout{engine.observation=None;bail!("LAYOUT_CHANGED");}
                if !matches!(&envelope.action,Action::Screenshot{}){
                    executed.store(true,Ordering::Release);
                    let (width,height)=(engine.width,engine.height);
                    engine.worker.as_mut().unwrap().call(json!({"command":"execute","action":envelope.action,"width":width,"height":height})).await?;
                }
                engine.observe().await
            }=>value,
        };
        let executed = executed.load(Ordering::Acquire);
        let mut response = match result {
            Ok(value) => value,
            Err(error) => {
                if executed {
                    engine.observation = None;
                }
                json!({"status":"error","code":format!("{error:#}"),"retryable":false})
            }
        };
        response["request_id"] = json!(envelope.request_id);
        response["action_executed"] = json!(executed);
        engine
            .cache
            .insert(envelope.request_id, (request, response.clone()));
        self.snapshot.lock().unwrap()["observation_id"] = json!(engine.observation);
        Ok(response)
    }
}
fn status(engine: &Engine) -> Value {
    json!({"status":"active","owner_pid":std::process::id(),"session_id":engine.id,"observation_id":engine.observation,"capabilities":{"actions":["screenshot","wait","move","click","double_click","drag","scroll","keypress","type"],"multi_output_selection":true,"clipboard":false,"runtime":"Rust","unicode":"BMP text with experimental settling delays; non-BMP rejected before input"}})
}
async fn client(shared: Arc<Shared>, socket: UnixStream) {
    let (reader, mut writer) = socket.into_split();
    let mut reader = BufReader::new(reader);
    let result = match tokio::time::timeout(Duration::from_secs(5), read_line(&mut reader)).await {
        Ok(Ok(request)) => shared.request(request).await,
        Ok(Err(error)) => Err(error),
        Err(_) => Err(anyhow::anyhow!("REQUEST_TIMEOUT")),
    };
    let response=result.unwrap_or_else(|error|json!({"status":"error","code":format!("{error:#}"),"retryable":false,"action_executed":false}));
    let _ = tokio::time::timeout(Duration::from_secs(2), write_line(&mut writer, &response)).await;
    let _ = writer.shutdown().await;
}
pub async fn serve(output: Option<String>, auto_select: bool) -> Result<()> {
    let root = runtime()?;
    let lock = Lock::acquire(&root)?;
    for name in ["ready.json", "stopped.json", "socket"] {
        let _ = std::fs::remove_file(root.join(name));
    }
    for entry in std::fs::read_dir(&root)?.flatten() {
        let name = entry.file_name();
        if name.to_string_lossy().starts_with("o-")
            && entry.path().extension().is_some_and(|v| v == "png")
        {
            let _ = std::fs::remove_file(entry.path());
        }
    }
    let listener = UnixListener::bind(root.join("socket"))?;
    std::fs::set_permissions(root.join("socket"), std::fs::Permissions::from_mode(0o600))?;
    let (stop, _) = watch::channel(false);
    let (finished, _) = watch::channel(None);
    let engine = Engine::new(root.clone())?;
    let shared = Arc::new(Shared {
        snapshot: StdMutex::new(json!({"status":"preparing","session_id":engine.id})),
        engine: Mutex::new(engine),
        serial: Mutex::new(()),
        last: StdMutex::new(Instant::now()),
        stop,
        finished,
        reason: StdMutex::new("normal"),
        worker_pid: AtomicU32::new(0),
        capture: StdMutex::new(None),
        cancel_requested: Arc::new(std::sync::atomic::AtomicBool::new(false)),
    });
    let preparing_shared = shared.clone();
    let mut preparing = tokio::spawn(async move {
        let mut engine = preparing_shared.engine.lock().await;
        engine.prepare(&preparing_shared, output, auto_select).await
    });
    let mut prepared = false;
    let mut receiver = shared.stop.subscribe();
    let mut signals = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    let mut tick = tokio::time::interval(Duration::from_secs(1));
    let mut clients = tokio::task::JoinSet::new();
    let serving:Result<()>=async {
    loop{
        tokio::select!{
            _=receiver.changed()=>break,
            _=signals.recv()=>{shared.cancel_with_reason("interrupted");break;},
            _=tokio::signal::ctrl_c()=>{shared.cancel_with_reason("interrupted");break;},
            result=&mut preparing,if !prepared=>{
                prepared=true;
                match result{
                    Ok(Ok(mut first))=>{clear_parent_death_guard()?;first["owner_pid"]=json!(std::process::id());let engine=shared.engine.lock().await;*shared.snapshot.lock().unwrap()=status(&engine);publish(&root.join("ready.json"),&first)?;},
                    error=>{let engine=shared.engine.lock().await;let code=match error{Ok(Err(error))=>format!("{error:#}"),Err(error)=>format!("PREPARE_TASK_FAILED: {error}"),_=>unreachable!()};publish(&root.join("ready.json"),&json!({"status":"error","code":code,"action_executed":false,"selector_click_may_have_executed":engine.bootstrap}))?;drop(engine);shared.cancel();break;}
                }
            },
            socket=listener.accept()=>{let (socket,_)=socket?;let state=shared.clone();clients.spawn(async move{client(state,socket).await;});},
            _=tick.tick()=>{
                if shared.last.lock().unwrap().elapsed()>Duration::from_secs(300){shared.cancel_with_reason("idle timeout");break;}
                if let Ok(mut engine)=shared.engine.try_lock()&& let Some(worker)=engine.worker.as_mut()&& worker.child.try_wait()?.is_some(){shared.worker_pid.store(0,Ordering::Release);shared.cancel_with_reason("helper interrupted");break;}
            },
        }
    }
    Ok(())
    }.await;
    if serving.is_err() {
        shared.cancel_with_reason("owner error");
    } else {
        shared.cancel();
    }
    drop(listener);
    if !prepared {
        preparing.abort();
        let _ = preparing.await;
    }
    let _serial = shared.serial.lock().await;
    let mut engine = shared.engine.lock().await;
    let mut errors = engine.cleanup().await;
    shared.worker_pid.store(0, Ordering::Release);
    let _ = std::fs::remove_file(root.join("socket"));
    drop(lock);
    if engine.started
        && let Err(error) = probe::notify(
            if errors.is_empty() {
                "Computer Use has ended"
            } else {
                "Computer Use needs attention"
            },
            if errors.is_empty() {
                if *shared.reason.lock().unwrap() == "normal" {
                    "Desktop control has stopped."
                } else {
                    "Task interrupted; desktop control has stopped."
                }
            } else {
                "Cleanup could not be verified. Check the session state."
            },
        )
        .await
    {
        errors.push(format!("END_NOTIFICATION_FAILED: {error:#}"));
    }
    let result = json!({"status":"stopped","errors":errors});
    publish(&root.join("stopped.json"), &result)?;
    shared.finished.send_replace(Some(result));
    drop(engine);
    drop(_serial);
    let _ = tokio::time::timeout(Duration::from_secs(3), async {
        while clients.join_next().await.is_some() {}
    })
    .await;
    clients.abort_all();
    serving
}
pub async fn send(request: Value) -> Result<Value> {
    let root = runtime()?;
    let socket = match UnixStream::connect(root.join("socket")).await {
        Ok(socket) => socket,
        Err(error) => {
            if request["command"] == "stop"
                && let Ok(bytes) = std::fs::read(root.join("stopped.json"))
            {
                return Ok(serde_json::from_slice(&bytes)?);
            }
            return Err(error).context("SESSION_UNAVAILABLE");
        }
    };
    let (reader, mut writer) = socket.into_split();
    write_line(&mut writer, &request).await?;
    tokio::time::timeout(
        Duration::from_secs(40),
        read_line(&mut BufReader::new(reader)),
    )
    .await
    .context("SESSION_RESPONSE_TIMEOUT")?
}
struct Owner {
    child: Child,
    keep: bool,
}
impl std::ops::Deref for Owner {
    type Target = Child;
    fn deref(&self) -> &Child {
        &self.child
    }
}
impl std::ops::DerefMut for Owner {
    fn deref_mut(&mut self) -> &mut Child {
        &mut self.child
    }
}
impl Drop for Owner {
    fn drop(&mut self) {
        if !self.keep
            && let Some(pid) = self.child.id()
        {
            let _ = unsafe { libc::kill(pid as i32, libc::SIGTERM) };
        }
    }
}
pub async fn start(output: Option<String>, auto_select: bool) -> Result<Value> {
    let root = runtime()?;
    if root.join("socket").exists()
        && let Ok(status) = send(json!({"command":"status"})).await
    {
        return Ok(status);
    }
    let _ = std::fs::remove_file(root.join("ready.json"));
    let mut command = Command::new(std::env::current_exe()?);
    command.arg("serve");
    if let Some(output) = output {
        command.args(["--output", &output]);
    }
    if auto_select {
        command.arg("--auto-select-output");
    }
    configure_child_lifetime(&mut command, true);
    let child = command
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .kill_on_drop(false)
        .spawn()?;
    let mut owner = Owner { child, keep: false };
    let deadline = Instant::now() + Duration::from_secs(75);
    loop {
        if let Ok(bytes) = std::fs::read(root.join("ready.json")) {
            let value: Value = serde_json::from_slice(&bytes)?;
            if value["status"] == "ready" {
                owner.keep = true;
                return Ok(value);
            }
            let _ = tokio::time::timeout(Duration::from_secs(8), owner.wait()).await;
            return Ok(value);
        }
        ensure!(owner.try_wait()?.is_none(), "SESSION_START_FAILED");
        if Instant::now() >= deadline {
            if let Some(pid) = owner.id() {
                let _ = unsafe { libc::kill(pid as i32, libc::SIGTERM) };
            }
            if tokio::time::timeout(Duration::from_secs(8), owner.wait())
                .await
                .is_err()
            {
                owner.kill().await?;
                owner.wait().await?;
            }
            bail!("SESSION_START_TIMEOUT");
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn directory() -> PathBuf {
        let path = std::env::temp_dir().join(token("wf-rust-unit-").unwrap());
        std::fs::create_dir(&path).unwrap();
        path
    }
    #[test]
    fn exclusive_lock_releases_on_drop() {
        let root = directory();
        let first = Lock::acquire(&root).unwrap();
        assert!(Lock::acquire(&root).is_err());
        drop(first);
        assert!(Lock::acquire(&root).is_ok());
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn published_metadata_is_private_and_complete() {
        let root = directory();
        let path = root.join("ready.json");
        publish(&path, &json!({"status":"ready"})).unwrap();
        assert_eq!(std::fs::metadata(&path).unwrap().mode() & 0o777, 0o600);
        assert_eq!(
            serde_json::from_slice::<Value>(&std::fs::read(path).unwrap()).unwrap()["status"],
            "ready"
        );
        assert_eq!(std::fs::read_dir(&root).unwrap().count(), 1);
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn envelope_rejects_unknown_fields() {
        let request = json!({"request_id":"r","session_id":"s","action":{"type":"screenshot"},"shell":"not permitted"});
        assert!(serde_json::from_value::<Envelope>(request).is_err());
    }
    #[tokio::test]
    async fn socket_stop_bypasses_action_lock_and_waits_for_cleanup() {
        let root = directory();
        let engine = Engine::new(root.clone()).unwrap();
        let (stop, _) = watch::channel(false);
        let (finished, _) = watch::channel(None);
        let shared = Arc::new(Shared {
            engine: Mutex::new(engine),
            serial: Mutex::new(()),
            snapshot: StdMutex::new(json!({"status":"active"})),
            last: StdMutex::new(Instant::now()),
            stop,
            finished,
            reason: StdMutex::new("normal"),
            worker_pid: AtomicU32::new(0),
            capture: StdMutex::new(None),
            cancel_requested: Arc::new(std::sync::atomic::AtomicBool::new(false)),
        });
        assert!(
            shared
                .request(json!({"command":"stop","extra":true}))
                .await
                .is_err()
        );
        assert!(!*shared.stop.borrow());
        let _gate = shared.serial.lock().await;
        let listener = UnixListener::bind(root.join("test.socket")).unwrap();
        let server_state = shared.clone();
        let server = tokio::spawn(async move {
            let (socket, _) = listener.accept().await.unwrap();
            client(server_state, socket).await;
        });
        let mut socket = UnixStream::connect(root.join("test.socket")).await.unwrap();
        write_line(&mut socket, &json!({"command":"stop"}))
            .await
            .unwrap();
        tokio::time::timeout(Duration::from_secs(1), async {
            while !*shared.stop.borrow() {
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap();
        assert!(!server.is_finished());
        let expected = json!({"status":"stopped","errors":[]});
        shared.finished.send_replace(Some(expected.clone()));
        let result = tokio::time::timeout(
            Duration::from_secs(1),
            read_line(&mut BufReader::new(socket)),
        )
        .await
        .unwrap()
        .unwrap();
        assert_eq!(result, expected);
        server.await.unwrap();
        std::fs::remove_dir_all(root).unwrap();
    }
}

fn validate_mapping(
    outputs: &std::collections::BTreeMap<u32, Output>,
    selected: &Output,
    pointer_version: u32,
) -> Result<()> {
    ensure!(
        outputs
            .values()
            .filter(|other| other.position == selected.position && other.size == selected.size)
            .count()
            == 1,
        "AMBIGUOUS_OUTPUT_GEOMETRY"
    );
    if outputs.len() > 1 {
        ensure!(pointer_version >= 2, "OUTPUT_BINDING_UNAVAILABLE");
    }
    ensure!(
        selected.scale == 1 && selected.transform == 0,
        "UNSUPPORTED_OUTPUT_TRANSFORM_OR_SCALE"
    );
    Ok(())
}
#[cfg(test)]
mod mapping_tests {
    use super::*;
    #[test]
    fn selected_output_requires_unambiguous_geometry_and_binding() {
        let first = Output {
            name: "A".into(),
            position: (0, 0),
            size: (1920, 1080),
            scale: 1,
            transform: 0,
        };
        let second = Output {
            name: "B".into(),
            position: (1920, 0),
            ..first.clone()
        };
        let mut outputs =
            std::collections::BTreeMap::from([(1, first.clone()), (2, second.clone())]);
        assert!(validate_mapping(&outputs, &second, 2).is_ok());
        assert_eq!(
            validate_mapping(&outputs, &second, 1)
                .unwrap_err()
                .to_string(),
            "OUTPUT_BINDING_UNAVAILABLE"
        );
        outputs.get_mut(&1).unwrap().position = (1920, 0);
        assert_eq!(
            validate_mapping(&outputs, &second, 2)
                .unwrap_err()
                .to_string(),
            "AMBIGUOUS_OUTPUT_GEOMETRY"
        );
        let mut only = std::collections::BTreeMap::from([(1, first)]);
        let rotated = only.get_mut(&1).unwrap();
        rotated.transform = 1;
        assert!(validate_mapping(&only, &only[&1], 2).is_err());
    }
}

/// Isolate the owner from launcher process-group cleanup. Both owner (until
/// ready) and worker are terminated by the kernel if their creating parent dies.
fn configure_child_lifetime(command: &mut Command, detach: bool) {
    let parent = std::process::id() as libc::pid_t;
    // SAFETY: this post-fork closure performs only async-signal-safe system
    // calls and constructs OS errors without allocating. No locks are used.
    unsafe {
        command.pre_exec(move || {
            if detach && libc::setsid() < 0 {
                return Err(std::io::Error::last_os_error());
            }
            if libc::prctl(
                libc::PR_SET_PDEATHSIG,
                libc::SIGTERM as libc::c_ulong,
                0 as libc::c_ulong,
                0 as libc::c_ulong,
                0 as libc::c_ulong,
            ) < 0
            {
                return Err(std::io::Error::last_os_error());
            }
            if libc::getppid() != parent {
                return Err(std::io::Error::from_raw_os_error(libc::ECANCELED));
            }
            Ok(())
        });
    }
}
fn clear_parent_death_guard() -> Result<()> {
    // serve runs on the main block_on thread which inherited the guard at exec.
    ensure!(
        unsafe {
            libc::prctl(
                libc::PR_SET_PDEATHSIG,
                0 as libc::c_ulong,
                0 as libc::c_ulong,
                0 as libc::c_ulong,
                0 as libc::c_ulong,
            )
        } == 0,
        "START_HANDOFF_FAILED"
    );
    Ok(())
}
