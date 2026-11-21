//! Read-only AT-SPI discovery, scoped to one mapped Wayfire window.
use crate::{desktop::Desktop, toplevel};
use anyhow::{Context, Result, ensure};
use atspi::{
    CoordType, Interface,
    proxy::{
        accessible::{AccessibleProxy, ObjectRefExt},
        bus::BusProxy,
        component::ComponentProxy,
    },
};
use serde_json::{Value, json};
use std::{collections::HashSet, time::Duration};

pub async fn inspect(id: Option<u64>, filter: Option<(String, String)>) -> Result<Value> {
    tokio::time::timeout(Duration::from_secs(15), query(id, filter))
        .await
        .context("UI_QUERY_TIMEOUT")?
}

async fn query(id: Option<u64>, filter: Option<(String, String)>) -> Result<Value> {
    let views = toplevel::mapped_views().await?;
    let candidates: Vec<_> = views
        .iter()
        .filter(|v| id.map_or(v.activated, |id| v.id == id))
        .collect();
    ensure!(candidates.len() == 1, "UI_WINDOW_SELECTION_REQUIRED");
    let view = candidates[0];
    let pid = view.pid.context("UI_WINDOW_PID_MISSING")?;
    ensure!(
        !view.title.is_empty()
            && views
                .iter()
                .filter(|v| v.pid == Some(pid) && v.title == view.title)
                .count()
                == 1,
        "UI_WINDOW_AMBIGUOUS"
    );

    let output_name = view.output_name.as_deref().context("UI_OUTPUT_MISSING")?;
    let (_, output) = Desktop::connect()?.select(Some(output_name))?;
    ensure!(
        output.scale == 1 && output.transform == 0,
        "UNSUPPORTED_OUTPUT_TRANSFORM_OR_SCALE"
    );
    let session = zbus::Connection::session()
        .await
        .context("ATSPI_BUS_UNAVAILABLE")?;
    let address = BusProxy::new(&session)
        .await?
        .get_address()
        .await
        .context("ATSPI_BUS_UNAVAILABLE")?;
    let bus = zbus::connection::Builder::address(address.as_str())?
        .build()
        .await
        .context("ATSPI_BUS_UNAVAILABLE")?;
    let registry = AccessibleProxy::builder(&bus)
        .destination("org.a11y.atspi.Registry")?
        .build()
        .await?;
    let dbus = zbus::fdo::DBusProxy::new(&bus).await?;
    let mut windows = Vec::new();
    for app in registry.get_children().await? {
        let owner = app.name().context("ATSPI_APPLICATION_OWNER_MISSING")?;
        if dbus
            .get_connection_unix_process_id(owner.clone().into())
            .await?
            != pid
        {
            continue;
        }
        for window in app.as_accessible_proxy(&bus).await?.get_children().await? {
            if window.as_accessible_proxy(&bus).await?.name().await? == view.title {
                windows.push(window);
            }
        }
    }
    ensure!(!windows.is_empty(), "ATSPI_WINDOW_NOT_FOUND");
    ensure!(windows.len() == 1, "UI_WINDOW_AMBIGUOUS");
    let window = windows.remove(0);
    let component = ComponentProxy::builder(&bus)
        .destination(window.name().context("ATSPI_OWNER_MISSING")?.clone())?
        .path(window.path().clone())?
        .build()
        .await?;
    let (rx, ry, rw, rh) = component.get_extents(CoordType::Window).await?;
    let mut origins = std::collections::BTreeSet::new();
    for geometry in [&view.geometry, &view.base_geometry].into_iter().flatten() {
        if geometry.width == f64::from(rw)
            && geometry.height == f64::from(rh)
            && geometry.x.fract() == 0.
            && geometry.y.fract() == 0.
        {
            origins.insert((
                geometry.x as i64 - i64::from(rx),
                geometry.y as i64 - i64::from(ry),
            ));
        }
    }
    ensure!(origins.len() == 1, "UI_COORDINATE_MAPPING_UNVERIFIED");
    let origin = origins.pop_first().unwrap();
    let mut pending = vec![(window, 0)];
    let mut seen = HashSet::new();
    let mut nodes = Vec::new();
    while let Some((node, depth)) = pending.pop() {
        ensure!(seen.len() < 8192, "ATSPI_TREE_LIMIT");
        if !seen.insert((
            node.name_as_str().map(str::to_owned),
            node.path().to_string(),
        )) {
            continue;
        }
        let accessible = node.as_accessible_proxy(&bus).await?;
        let role = accessible.get_role_name().await?;
        let name = accessible.name().await?;
        if filter.as_ref().is_none_or(|(r, n)| {
            n == &name
                && (r.eq_ignore_ascii_case(&role) || (r == "button" && role == "push button"))
        }) {
            let states: Vec<_> = accessible
                .get_state()
                .await?
                .iter()
                .map(|s| format!("{s:?}"))
                .collect();
            let mut row = json!({"role":role,"name":name,"states":states,"depth":depth,"bounds":null,"center":null,"desktop_center":null});
            if accessible
                .get_interfaces()
                .await?
                .contains(Interface::Component)
            {
                let component = ComponentProxy::builder(&bus)
                    .destination(node.name().context("ATSPI_OWNER_MISSING")?.clone())?
                    .path(node.path().clone())?
                    .build()
                    .await?;
                let (x, y, w, h) = component.get_extents(CoordType::Window).await?;
                if w > 0 && h > 0 && x != i32::MIN && y != i32::MIN {
                    let left = origin.0 + i64::from(x);
                    let top = origin.1 + i64::from(y);
                    let cx = left + i64::from(w) / 2;
                    let cy = top + i64::from(h) / 2;
                    row["bounds"] = json!({"x":left,"y":top,"width":w,"height":h});
                    if (0..i64::from(output.size.0)).contains(&cx)
                        && (0..i64::from(output.size.1)).contains(&cy)
                    {
                        row["center"] = json!({"x":cx,"y":cy});
                        row["desktop_center"] = json!({"x":cx+i64::from(output.position.0),"y":cy+i64::from(output.position.1)});
                    }
                }
            }
            nodes.push(row);
        }
        pending.extend(
            accessible
                .get_children()
                .await?
                .into_iter()
                .rev()
                .filter(|child| !child.is_null())
                .map(|child| (child, depth + 1)),
        );
    }
    Ok(
        json!({"status":"ok","window_id":view.id,"output":output_name,"nodes":nodes,"sends_input":false}),
    )
}
