use anyhow::Result;
use serde_json::{Value, json};
use std::{collections::BTreeMap, path::PathBuf, time::Duration};

/// Read-only discovery; does not create input devices or Portal sessions.
pub async fn doctor() -> Result<Value> {
    let mut report=tokio::task::spawn_blocking(||{
        let desktop=crate::desktop::Desktop::connect()?;
        Ok::<_,anyhow::Error>(json!({"status":"diagnostic","runtime":"Rust","sends_input":false,"outputs":desktop.state.outputs,"protocol_versions":desktop.state.globals,"supported_input_configuration":"one explicitly selected output, scale 1, normal orientation","verification":"See IMPLEMENTATION.md for tested configurations; doctor does not execute actions."}))
    }).await??;
    let services = tokio::time::timeout(Duration::from_secs(3), async {
        let connection = zbus::Connection::session().await?;
        let proxy = zbus::Proxy::new(
            &connection,
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
        )
        .await?;
        let mut owners = BTreeMap::new();
        for name in [
            "org.freedesktop.portal.Desktop",
            "org.freedesktop.impl.portal.desktop.wlr",
            "org.freedesktop.Notifications",
        ] {
            let owned: bool = proxy.call("NameHasOwner", &(name,)).await?;
            owners.insert(name.to_string(), owned);
        }
        Ok::<_, anyhow::Error>(owners)
    })
    .await;
    report["session_bus"] = match services {
        Ok(Ok(owners)) => json!({"reachable":true,"services":owners}),
        Ok(Err(error)) => json!({"reachable":false,"error":error.to_string()}),
        Err(_) => json!({"reachable":false,"error":"DBUS_TIMEOUT"}),
    };
    let root =
        std::env::var_os("PIPEWIRE_RUNTIME_DIR").or_else(|| std::env::var_os("XDG_RUNTIME_DIR"));
    report["pipewire_socket"] = if let Some(root) = root {
        let name = std::env::var("PIPEWIRE_REMOTE").unwrap_or_else(|_| "pipewire-0".into());
        match std::os::unix::net::UnixStream::connect(PathBuf::from(root).join(name)) {
            Ok(_) => json!({"reachable":true}),
            Err(error) => json!({"reachable":false,"error":error.to_string()}),
        }
    } else {
        json!({"reachable":false,"error":"RUNTIME_UNAVAILABLE"})
    };
    Ok(report)
}
