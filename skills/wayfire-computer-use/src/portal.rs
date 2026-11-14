use crate::desktop::Output;
use anyhow::{Context, Result, ensure};
use ashpd::desktop::{
    PersistMode, Session,
    screencast::{CursorMode, Screencast, SourceType},
};
use std::{os::fd::OwnedFd, time::Duration};
pub struct Portal {
    proxy: Screencast<'static>,
    session: Session<'static, Screencast<'static>>,
}
impl Portal {
    pub async fn open() -> Result<Self> {
        let proxy = tokio::time::timeout(Duration::from_secs(10), Screencast::new())
            .await
            .context("PORTAL_CONNECT_TIMEOUT")??;
        let session = tokio::time::timeout(Duration::from_secs(10), proxy.create_session())
            .await
            .context("PORTAL_CREATE_TIMEOUT")??;
        Ok(Self { proxy, session })
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
        tokio::time::timeout(Duration::from_secs(3), self.session.close())
            .await
            .context("PORTAL_CLOSE_TIMEOUT")??;
        Ok(())
    }
}
