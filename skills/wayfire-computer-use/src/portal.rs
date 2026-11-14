use crate::desktop::Output;
use anyhow::{Context, Result, ensure};
use ashpd::desktop::{
    PersistMode, Session,
    screencast::{CursorMode, Screencast, SourceType},
};
use futures_util::StreamExt;
use std::{os::fd::OwnedFd, time::Duration};
use tokio::sync::{oneshot, watch};
pub struct Portal {
    _service_guard: Option<ServiceGuard>,
    service_loss: Option<watch::Receiver<bool>>,
    proxy: Screencast<'static>,
    session: Session<'static, Screencast<'static>>,
}
impl Portal {
    pub async fn open() -> Result<Self> {
        Self::open_inner(None).await
    }
    pub async fn open_with_loss(loss: watch::Sender<bool>) -> Result<Self> {
        Self::open_inner(Some(loss)).await
    }
    async fn open_inner(loss: Option<watch::Sender<bool>>) -> Result<Self> {
        let proxy = tokio::time::timeout(Duration::from_secs(10), Screencast::new())
            .await
            .context("PORTAL_CONNECT_TIMEOUT")??;
        // Subscribe before CreateSession so an owner change cannot be missed
        // between acquiring the session and installing its loss monitor.
        let service_loss = loss.as_ref().map(watch::Sender::subscribe);
        let guard = if let Some(loss) = loss {
            Some(ServiceGuard::new(proxy.connection().clone(), loss).await?)
        } else {
            None
        };
        let session = tokio::time::timeout(Duration::from_secs(10), proxy.create_session())
            .await
            .context("PORTAL_CREATE_TIMEOUT")??;
        Ok(Self {
            _service_guard: guard,
            service_loss,
            proxy,
            session,
        })
    }
    pub async fn stream(&self, output: &Output) -> Result<(OwnedFd, u32)> {
        tokio::time::timeout(
            Duration::from_secs(60),
            self.proxy.select_sources(
                &self.session,
                CursorMode::Hidden,
                SourceType::Monitor.into(),
                false,
                None,
                PersistMode::DoNot,
            ),
        )
        .await
        .context("PORTAL_SOURCE_SELECTION_TIMEOUT")??
        .response()?;
        let response = tokio::time::timeout(
            Duration::from_secs(60),
            self.proxy.start(&self.session, None),
        )
        .await
        .context("PORTAL_START_TIMEOUT")??
        .response()?;
        ensure!(response.streams().len() == 1, "OUTPUT_MAPPING_UNAVAILABLE");
        let stream = &response.streams()[0];
        ensure!(
            stream.position() == Some(output.position) && stream.size() == Some(output.size),
            "OUTPUT_MAPPING_MISMATCH"
        );
        let fd = tokio::time::timeout(
            Duration::from_secs(5),
            self.proxy.open_pipe_wire_remote(&self.session),
        )
        .await
        .context("PIPEWIRE_REMOTE_TIMEOUT")??;
        Ok((fd, stream.pipe_wire_node_id()))
    }
    pub async fn close(&self) -> Result<()> {
        // Avoid D-Bus auto-activation or addressing a replacement service while
        // cleaning up a session whose service identity has already been lost.
        ensure!(
            !self
                .service_loss
                .as_ref()
                .is_some_and(|loss| *loss.borrow()),
            "PORTAL_SERVICE_LOST: session close could not be confirmed"
        );
        tokio::time::timeout(Duration::from_secs(3), self.session.close())
            .await
            .context("PORTAL_CLOSE_TIMEOUT")??;
        Ok(())
    }
}

/// Lifetime-bound monitor. Any owner release/replacement or monitor/bus loss
/// cancels control, even while an already-open PipeWire stream remains usable.
struct ServiceGuard(tokio::task::JoinHandle<()>);
impl ServiceGuard {
    async fn new(connection: zbus::Connection, loss: watch::Sender<bool>) -> Result<Self> {
        let (ready_tx, ready_rx) = oneshot::channel::<std::result::Result<(), String>>();
        let task = tokio::spawn(async move {
            let mut ready = Some(ready_tx);
            let result: Result<()> = async {
                let bus = zbus::fdo::DBusProxy::new(&connection).await?;
                let mut changes = bus.receive_name_owner_changed().await?;
                bus.get_name_owner("org.freedesktop.portal.Desktop".try_into()?)
                    .await?;
                let _ = ready.take().unwrap().send(Ok(()));
                while let Some(change) = changes.next().await {
                    let args = change.args()?;
                    if matches!(
                        args.name().as_str(),
                        "org.freedesktop.portal.Desktop"
                            | "org.freedesktop.impl.portal.desktop.wlr"
                    ) && args.old_owner().as_ref().is_some()
                    {
                        anyhow::bail!("PORTAL_SERVICE_LOST");
                    }
                }
                anyhow::bail!("PORTAL_MONITOR_ENDED")
            }
            .await;
            if let Some(ready) = ready {
                let _ = ready.send(Err(format!("PORTAL_MONITOR_FAILED: {:?}", result.err())));
            }
            loss.send_replace(true);
        });
        let guard = Self(task);
        tokio::time::timeout(Duration::from_secs(5), ready_rx)
            .await
            .context("PORTAL_MONITOR_TIMEOUT")??
            .map_err(anyhow::Error::msg)?;
        Ok(guard)
    }
}
impl Drop for ServiceGuard {
    fn drop(&mut self) {
        self.0.abort();
    }
}
