use crate::{
    capture::Capture,
    desktop::{Desktop, PointerOnly},
    portal::Portal,
};
use anyhow::{Context, Result, ensure};
use std::{
    collections::{BTreeSet, HashMap},
    os::unix::fs::MetadataExt,
    path::{Path, PathBuf},
    time::Duration,
};

pub async fn notify(summary: &str, body: &str) -> Result<()> {
    tokio::time::timeout(Duration::from_secs(5), async {
        let connection = zbus::Connection::session().await?;
        let proxy = zbus::Proxy::new(
            &connection,
            "org.freedesktop.Notifications",
            "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications",
        )
        .await?;
        let hints: HashMap<&str, zbus::zvariant::Value<'_>> = HashMap::new();
        let _: u32 = proxy
            .call(
                "Notify",
                &(
                    "wayfire-computer-use",
                    0u32,
                    "",
                    summary,
                    body,
                    Vec::<String>::new(),
                    hints,
                    -1i32,
                ),
            )
            .await?;
        Ok::<(), anyhow::Error>(())
    })
    .await
    .context("NOTIFICATION_TIMEOUT")??;
    Ok(())
}
pub(crate) fn selectors() -> BTreeSet<u32> {
    let mut found = BTreeSet::new();
    if let Ok(entries) = std::fs::read_dir("/proc") {
        for entry in entries.flatten() {
            let path = entry.path();
            let Some(pid) = entry
                .file_name()
                .to_str()
                .and_then(|v| v.parse::<u32>().ok())
            else {
                continue;
            };
            // SAFETY: getuid has no pointer arguments or preconditions.
            if !entry
                .metadata()
                .is_ok_and(|m| m.uid() == unsafe { libc::getuid() })
            {
                continue;
            }
            if let Ok(bytes) = std::fs::read(path.join("cmdline")) {
                let argv: Vec<_> = bytes.split(|v| *v == 0).collect();
                let executable = argv
                    .first()
                    .and_then(|v| std::str::from_utf8(v).ok())
                    .and_then(|v| Path::new(v).file_name())
                    .and_then(|v| v.to_str());
                if executable == Some("slurp")
                    && argv.contains(&b"-or".as_slice())
                    && (argv.contains(&b"Monitor: %o".as_slice())
                        || argv.contains(&b"%o".as_slice()))
                {
                    found.insert(pid);
                }
            }
        }
    }
    found
}
pub async fn choose_once(output: String, baseline: BTreeSet<u32>) -> Result<()> {
    let deadline = tokio::time::Instant::now() + Duration::from_secs(60);
    loop {
        let candidates: BTreeSet<_> = selectors().difference(&baseline).copied().collect();
        ensure!(candidates.len() <= 1, "AMBIGUOUS_PORTAL_SELECTOR");
        if !candidates.is_empty() {
            tokio::time::sleep(Duration::from_millis(200)).await;
            return tokio::task::spawn_blocking(move || {
                let desktop = Desktop::connect()?;
                let (id, geometry) = desktop.select(Some(&output))?;
                let mut input = PointerOnly::new(desktop, id)?;
                ensure!(
                    selectors()
                        .difference(&baseline)
                        .copied()
                        .collect::<BTreeSet<_>>()
                        == candidates,
                    "PORTAL_SELECTOR_DISAPPEARED"
                );
                input.motion(
                    geometry.size.0 as u32 / 2,
                    geometry.size.1 as u32 / 2,
                    geometry.size.0 as u32,
                    geometry.size.1 as u32,
                )?;
                std::thread::sleep(Duration::from_millis(100));
                ensure!(
                    selectors()
                        .difference(&baseline)
                        .copied()
                        .collect::<BTreeSet<_>>()
                        == candidates,
                    "PORTAL_SELECTOR_DISAPPEARED"
                );
                input.button(272, true)?;
                input.button(272, false)?;
                input.release()?;
                Ok(())
            })
            .await?;
        }
        ensure!(
            tokio::time::Instant::now() < deadline,
            "PORTAL_SELECTOR_TIMEOUT"
        );
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
}
pub async fn capture(
    output: Option<String>,
    path: PathBuf,
    auto_select: bool,
) -> Result<serde_json::Value> {
    let _lock = crate::session::Lock::acquire(&crate::session::runtime()?)?;
    let desktop = Desktop::connect()?;
    let (_, selected) = desktop.select(output.as_deref())?;
    notify("Computer Use Rust capture test","Preparing an explicitly authorized screenshot test. Desktop input may select the Portal source.").await?;
    let portal = Portal::open().await;
    let result = match &portal {
        Ok(portal) => {
            let baseline = selectors();
            let stream = if auto_select {
                tokio::try_join!(
                    portal.stream(&selected),
                    choose_once(selected.name.clone(), baseline)
                )
                .map(|(stream, ())| stream)
            } else {
                portal.stream(&selected).await
            };
            match stream {
                Ok((fd, node)) => {
                    let capture = Capture::new(fd, node);
                    let after = crate::capture::monotonic_ns();
                    tokio::task::spawn_blocking(move||{let (width,height)=capture.observe(&path,after)?;Ok(serde_json::json!({"status":"ok","output":selected,"width":width,"height":height,"screenshot_path":path,"runtime":"Rust","capture_backend":"PipeWire"}))}).await?
                }
                Err(error) => Err(error),
            }
        }
        Err(error) => Err(anyhow::anyhow!(error.to_string())),
    };
    let mut cleanup_errors = Vec::new();
    if let Ok(portal) = portal
        && let Err(error) = portal.close().await
    {
        cleanup_errors.push(format!("{error:#}"));
    }
    if let Err(error) = notify(
        "Computer Use Rust capture test ended",
        "The capture probe process is ending; no ordinary application input was requested.",
    )
    .await
    {
        cleanup_errors.push(format!("END_NOTIFICATION_FAILED: {error:#}"));
    }
    match result {
        Err(error) => {
            if cleanup_errors.is_empty() {
                Err(error)
            } else {
                Err(anyhow::anyhow!(
                    "{error:#}; cleanup_errors={cleanup_errors:?}"
                ))
            }
        }
        Ok(mut value) => {
            value["cleanup_errors"] = serde_json::json!(cleanup_errors);
            if !cleanup_errors.is_empty() {
                value["status"] = serde_json::json!("error");
            }
            Ok(value)
        }
    }
}
