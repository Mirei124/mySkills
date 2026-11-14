//! Optional Wayfire IPC window discovery and verified focus requests.
use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    os::unix::fs::{FileTypeExt, MetadataExt},
    path::Path,
    sync::atomic::{AtomicBool, Ordering},
    time::Duration,
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::UnixStream,
};

const LIMIT: usize = 4 * 1024 * 1024;
const TIMEOUT: Duration = Duration::from_secs(3);

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FocusTarget {
    pub id: u64,
    pub pid: Option<u32>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Geometry {
    x: f64,
    y: f64,
    width: f64,
    height: f64,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Toplevel {
    pub id: u64,
    pub pid: Option<u32>,
    pub title: String,
    pub app_id: String,
    pub output_name: Option<String>,
    pub output_id: Option<u64>,
    pub geometry: Option<Geometry>,
    pub activated: bool,
    pub minimized: bool,
    pub fullscreen: bool,
    pub focusable: bool,
}

fn parse_view(value: &Value) -> Result<Option<Toplevel>> {
    if value["role"] != "toplevel" || value["mapped"] != true {
        return Ok(None);
    }
    let id = value["id"]
        .as_u64()
        .filter(|id| *id > 0)
        .context("INVALID_TOPLEVEL_ID")?;
    let title = value["title"].as_str().context("INVALID_TOPLEVEL_TITLE")?;
    let app_id = value["app-id"]
        .as_str()
        .context("INVALID_TOPLEVEL_APP_ID")?;
    Ok(Some(Toplevel {
        id,
        pid: value["pid"]
            .as_u64()
            .and_then(|pid| u32::try_from(pid).ok())
            .filter(|pid| *pid > 0),
        title: title.into(),
        app_id: app_id.into(),
        output_name: value["output-name"]
            .as_str()
            .filter(|name| !name.is_empty() && *name != "null")
            .map(str::to_owned),
        output_id: value["output-id"].as_u64(),
        geometry: value
            .get("geometry")
            .filter(|v| !v.is_null())
            .map(|v| serde_json::from_value(v.clone()))
            .transpose()
            .context("INVALID_TOPLEVEL_GEOMETRY")?,
        activated: value["activated"]
            .as_bool()
            .context("INVALID_TOPLEVEL_STATE")?,
        minimized: value["minimized"].as_bool().unwrap_or(false),
        fullscreen: value["fullscreen"].as_bool().unwrap_or(false),
        focusable: value["focusable"].as_bool().unwrap_or(true),
    }))
}

fn parse_list(value: Value) -> Result<Vec<Toplevel>> {
    let mut seen = BTreeSet::new();
    let mut views = vec![];
    for raw in value.as_array().context("INVALID_TOPLEVEL_LIST")? {
        if let Some(view) = parse_view(raw)? {
            ensure!(seen.insert(view.id), "AMBIGUOUS_TOPLEVEL_ID");
            views.push(view);
        }
    }
    views.sort_by_key(|view| view.id);
    Ok(views)
}

struct Ipc(UnixStream);
impl Ipc {
    async fn connect(expected_pid: Option<libc::pid_t>) -> Result<Self> {
        let path = std::env::var_os("WAYFIRE_SOCKET")
            .context("WAYFIRE_IPC_UNAVAILABLE: WAYFIRE_SOCKET is not set")?;
        let path = Path::new(&path);
        ensure!(path.is_absolute(), "UNSAFE_WAYFIRE_IPC_SOCKET");
        let metadata = std::fs::symlink_metadata(path).context("WAYFIRE_IPC_UNAVAILABLE")?;
        // SAFETY: getuid has no pointer arguments or preconditions.
        let uid = unsafe { libc::getuid() };
        ensure!(
            metadata.file_type().is_socket() && metadata.uid() == uid,
            "UNSAFE_WAYFIRE_IPC_SOCKET"
        );
        let stream = UnixStream::connect(path)
            .await
            .context("WAYFIRE_IPC_UNAVAILABLE")?;
        let peer = stream.peer_cred()?;
        ensure!(peer.uid() == uid, "UNSAFE_WAYFIRE_IPC_PEER");
        ensure!(
            expected_pid.is_none_or(|pid| peer.pid() == Some(pid)),
            "COMPOSITOR_IDENTITY_MISMATCH"
        );
        Ok(Self(stream))
    }

    async fn call(&mut self, method: &str, data: Value) -> Result<Value> {
        let bytes = serde_json::to_vec(&json!({"method":method,"data":data}))?;
        ensure!(bytes.len() <= LIMIT, "WAYFIRE_IPC_MESSAGE_TOO_LARGE");
        self.0
            .write_all(&(bytes.len() as u32).to_le_bytes())
            .await?;
        self.0.write_all(&bytes).await?;
        let size = self.0.read_u32_le().await? as usize;
        ensure!(size > 0 && size <= LIMIT, "WAYFIRE_IPC_MESSAGE_TOO_LARGE");
        let mut body = vec![0; size];
        self.0.read_exact(&mut body).await?;
        let value: Value = serde_json::from_slice(&body).context("INVALID_WAYFIRE_IPC_RESPONSE")?;
        if let Some(error) = value.get("error") {
            bail!("WAYFIRE_IPC_ERROR: {error}");
        }
        if let Some(result) = value.get("result") {
            ensure!(result == "ok", "WAYFIRE_IPC_ERROR: {value}");
        }
        Ok(value)
    }

    async fn views(&mut self) -> Result<Vec<Toplevel>> {
        parse_list(self.call("window-rules/list-views", json!({})).await?)
    }
}

pub async fn list() -> Result<Value> {
    tokio::time::timeout(TIMEOUT, async {
        let views = Ipc::connect(None).await?.views().await?;
        Ok(json!({"status":"ok","backend":"wayfire-ipc","sends_input":false,"toplevels":views}))
    })
    .await
    .context("WAYFIRE_IPC_TIMEOUT")?
}

pub(crate) async fn verify_compositor(pid: libc::pid_t) -> Result<()> {
    tokio::time::timeout(TIMEOUT, Ipc::connect(Some(pid)))
        .await
        .context("WAYFIRE_IPC_TIMEOUT")??;
    Ok(())
}

fn validate_target(view: &Toplevel, target: &FocusTarget, output: Option<&str>) -> Result<()> {
    ensure!(view.focusable, "TOPLEVEL_NOT_FOCUSABLE");
    ensure!(
        target.pid.is_none_or(|pid| view.pid == Some(pid)),
        "TOPLEVEL_IDENTITY_CHANGED"
    );
    ensure!(
        output.is_none_or(|name| view.output_name.as_deref() == Some(name)),
        "TOPLEVEL_OUTPUT_MISMATCH"
    );
    Ok(())
}

async fn request_focus(
    ipc: &mut Ipc,
    target: &FocusTarget,
    output: Option<&str>,
    sent: &AtomicBool,
    cancel: Option<&AtomicBool>,
) -> Result<Toplevel> {
    ensure!(
        target.id > 0 && target.pid != Some(0),
        "INVALID_TOPLEVEL_TARGET"
    );
    let views = ipc.views().await?;
    let view = views
        .iter()
        .find(|view| view.id == target.id)
        .context("TOPLEVEL_NOT_FOUND")?;
    validate_target(view, target, output)?;
    ensure!(
        !cancel.is_some_and(|flag| flag.load(Ordering::Acquire)),
        "ACTION_CANCELLED"
    );
    // A write/timeout error cannot establish whether Wayfire received the request.
    sent.store(true, Ordering::Release);
    let reply = ipc
        .call("window-rules/focus-view", json!({"id":target.id}))
        .await?;
    ensure!(reply["result"] == "ok", "INVALID_WAYFIRE_IPC_RESPONSE");
    loop {
        ensure!(
            !cancel.is_some_and(|flag| flag.load(Ordering::Acquire)),
            "ACTION_CANCELLED"
        );
        let views = ipc.views().await?;
        let view = views
            .into_iter()
            .find(|view| view.id == target.id)
            .context("TOPLEVEL_CLOSED")?;
        validate_target(&view, target, output)?;
        let focused = ipc.call("window-rules/get-focused-view", json!({})).await?;
        ensure!(
            focused["result"] == "ok" && focused.get("info").is_some(),
            "INVALID_WAYFIRE_IPC_RESPONSE"
        );
        if view.activated && focused["info"]["id"].as_u64() == Some(target.id) {
            return Ok(view);
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
}

/// Called under the owner's action lock or the standalone per-display lock.
pub(crate) async fn focus(
    target: &FocusTarget,
    output: Option<&str>,
    cancel: Option<&AtomicBool>,
    compositor_pid: libc::pid_t,
) -> Value {
    let sent = AtomicBool::new(false);
    let result = tokio::time::timeout(TIMEOUT, async {
        request_focus(
            &mut Ipc::connect(Some(compositor_pid)).await?,
            target,
            output,
            &sent,
            cancel,
        )
        .await
    })
    .await
    .context("TOPLEVEL_FOCUS_TIMEOUT")
    .and_then(|value| value);
    let may_have_executed = sent.load(Ordering::Acquire);
    match result {
        Ok(view) => {
            json!({"status":"focused","backend":"wayfire-ipc","sends_input":false,"focus_confirmed":true,"focus_request_may_have_executed":may_have_executed,"toplevel":view})
        }
        Err(error) => {
            json!({"status":"error","code":format!("{error:#}"),"retryable":false,"sends_input":false,"focus_confirmed":false,"focus_request_may_have_executed":may_have_executed})
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn view(id: u64, activated: bool) -> Value {
        json!({"id":id,"pid":42,"title":"Same title 中文","app-id":"test.app","role":"toplevel","mapped":true,"activated":activated,"output-name":"HEADLESS-1","output-id":1,"geometry":{"x":10.0,"y":20.0,"width":700.0,"height":400.0}})
    }

    async fn receive(stream: &mut UnixStream) -> Value {
        let size = stream.read_u32_le().await.unwrap() as usize;
        let mut body = vec![0; size];
        stream.read_exact(&mut body).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    async fn respond(stream: &mut UnixStream, value: Value) {
        let bytes = serde_json::to_vec(&value).unwrap();
        stream
            .write_all(&(bytes.len() as u32).to_le_bytes())
            .await
            .unwrap();
        stream.write_all(&bytes).await.unwrap();
    }

    #[test]
    fn list_filters_non_windows_and_keeps_distinct_same_title_windows() {
        let mut layer = view(3, false);
        layer["role"] = json!("desktop-environment");
        let mut closed = view(4, false);
        closed["mapped"] = json!(false);
        let mut unknown_pid = view(2, false);
        unknown_pid["pid"] = json!(-1);
        let windows = parse_list(json!([unknown_pid, layer, closed, view(1, true)])).unwrap();
        assert_eq!(windows.iter().map(|v| v.id).collect::<Vec<_>>(), vec![1, 2]);
        assert_eq!(windows[1].pid, None);
        assert!(
            parse_list(json!([view(1, true), view(1, false)]))
                .unwrap_err()
                .to_string()
                .contains("AMBIGUOUS_TOPLEVEL_ID")
        );
    }

    #[tokio::test]
    async fn ipc_handles_fragmented_frames() {
        let (client, mut server) = UnixStream::pair().unwrap();
        let peer = tokio::spawn(async move {
            assert_eq!(
                receive(&mut server).await["method"],
                "window-rules/list-views"
            );
            let bytes = serde_json::to_vec(&json!([view(1, true)])).unwrap();
            for byte in (bytes.len() as u32).to_le_bytes().into_iter().chain(bytes) {
                server.write_all(&[byte]).await.unwrap();
                tokio::task::yield_now().await;
            }
        });
        assert_eq!(
            Ipc(client).views().await.unwrap()[0].title,
            "Same title 中文"
        );
        peer.await.unwrap();
    }

    #[tokio::test]
    async fn ipc_rejects_oversized_frames_and_reports_plugin_errors() {
        for oversized in [true, false] {
            let (client, mut server) = UnixStream::pair().unwrap();
            let peer = tokio::spawn(async move {
                receive(&mut server).await;
                if oversized {
                    server
                        .write_all(&((LIMIT + 1) as u32).to_le_bytes())
                        .await
                        .unwrap();
                } else {
                    respond(&mut server, json!({"error":"No such method found!"})).await;
                }
            });
            let error = Ipc(client).views().await.unwrap_err().to_string();
            assert!(error.contains(if oversized {
                "WAYFIRE_IPC_MESSAGE_TOO_LARGE"
            } else {
                "WAYFIRE_IPC_ERROR"
            }));
            peer.await.unwrap();
        }
    }

    #[tokio::test]
    async fn focus_requires_observed_activation_not_just_an_ack() {
        let (client, mut server) = UnixStream::pair().unwrap();
        let peer = tokio::spawn(async move {
            assert_eq!(
                receive(&mut server).await["method"],
                "window-rules/list-views"
            );
            respond(&mut server, json!([view(1, false), view(2, true)])).await;
            assert_eq!(
                receive(&mut server).await,
                json!({"method":"window-rules/focus-view","data":{"id":1}})
            );
            respond(&mut server, json!({"result":"ok"})).await;
            for focused_id in [2, 1] {
                assert_eq!(
                    receive(&mut server).await["method"],
                    "window-rules/list-views"
                );
                respond(&mut server, json!([view(1, true)])).await;
                assert_eq!(
                    receive(&mut server).await["method"],
                    "window-rules/get-focused-view"
                );
                respond(
                    &mut server,
                    json!({"result":"ok","info":view(focused_id, true)}),
                )
                .await;
            }
        });
        let sent = AtomicBool::new(false);
        let result = request_focus(
            &mut Ipc(client),
            &FocusTarget {
                id: 1,
                pid: Some(42),
            },
            Some("HEADLESS-1"),
            &sent,
            None,
        )
        .await
        .unwrap();
        assert_eq!(result.id, 1);
        assert!(sent.load(Ordering::Acquire));
        peer.await.unwrap();
    }

    #[tokio::test]
    async fn focus_detects_target_disappearing_after_request() {
        let (client, mut server) = UnixStream::pair().unwrap();
        let peer = tokio::spawn(async move {
            receive(&mut server).await;
            respond(&mut server, json!([view(1, false)])).await;
            receive(&mut server).await;
            respond(&mut server, json!({"result":"ok"})).await;
            receive(&mut server).await;
            respond(&mut server, json!([])).await;
        });
        let sent = AtomicBool::new(false);
        let error = request_focus(
            &mut Ipc(client),
            &FocusTarget { id: 1, pid: None },
            None,
            &sent,
            None,
        )
        .await
        .unwrap_err();
        assert_eq!(error.to_string(), "TOPLEVEL_CLOSED");
        assert!(sent.load(Ordering::Acquire));
        peer.await.unwrap();
    }

    #[tokio::test]
    async fn preflight_rejection_or_cancellation_sends_no_focus_request() {
        for (pid, output, cancelled, expected) in [
            (Some(99), None, false, "TOPLEVEL_IDENTITY_CHANGED"),
            (None, Some("HEADLESS-2"), false, "TOPLEVEL_OUTPUT_MISMATCH"),
            (None, None, true, "ACTION_CANCELLED"),
        ] {
            let (client, mut server) = UnixStream::pair().unwrap();
            let peer = tokio::spawn(async move {
                receive(&mut server).await;
                respond(&mut server, json!([view(1, false)])).await;
                let mut byte = [0];
                assert_eq!(server.read(&mut byte).await.unwrap(), 0);
            });
            let sent = AtomicBool::new(false);
            let cancel = AtomicBool::new(cancelled);
            let error = request_focus(
                &mut Ipc(client),
                &FocusTarget { id: 1, pid },
                output,
                &sent,
                Some(&cancel),
            )
            .await
            .unwrap_err();
            assert_eq!(error.to_string(), expected);
            assert!(!sent.load(Ordering::Acquire));
            peer.await.unwrap();
        }
    }

    #[tokio::test]
    async fn stalled_reply_after_focus_keeps_uncertainty_and_is_not_retried() {
        let (client, mut server) = UnixStream::pair().unwrap();
        let peer = tokio::spawn(async move {
            receive(&mut server).await;
            respond(&mut server, json!([view(1, false)])).await;
            assert_eq!(
                receive(&mut server).await["method"],
                "window-rules/focus-view"
            );
            respond(&mut server, json!({"result":"ok"})).await;
            assert_eq!(
                receive(&mut server).await["method"],
                "window-rules/list-views"
            );
            // Withhold the confirmation reply. Cancellation drops the socket;
            // there must be no second focus request on this connection.
            let mut byte = [0];
            assert_eq!(server.read(&mut byte).await.unwrap(), 0);
        });
        let sent = AtomicBool::new(false);
        let result = tokio::time::timeout(Duration::from_millis(100), async {
            request_focus(
                &mut Ipc(client),
                &FocusTarget { id: 1, pid: None },
                None,
                &sent,
                None,
            )
            .await
        })
        .await;
        assert!(result.is_err());
        assert!(sent.load(Ordering::Acquire));
        peer.await.unwrap();
    }
}
