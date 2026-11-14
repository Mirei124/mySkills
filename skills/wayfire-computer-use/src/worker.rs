//! Supervised input worker in the same Rust executable; no C helper required.
use crate::{
    action::Action,
    desktop::{Desktop, Input},
    execute,
};
use anyhow::{Context, Result, ensure};
use serde::Deserialize;
use serde_json::json;
use std::{
    io::{BufRead, Read, Write},
    sync::atomic::{AtomicBool, Ordering},
};
static CANCEL: AtomicBool = AtomicBool::new(false);
extern "C" fn cancel_signal(_: libc::c_int) {
    CANCEL.store(true, Ordering::Release);
}
#[derive(Deserialize)]
#[serde(tag = "command", rename_all = "snake_case", deny_unknown_fields)]
enum Request {
    Execute {
        action: Action,
        width: u32,
        height: u32,
    },
    Layout {},
    ReleaseAll {},
    Stop {},
}
fn reply(value: serde_json::Value) -> Result<()> {
    let mut out = std::io::stdout().lock();
    serde_json::to_writer(&mut out, &value)?;
    out.write_all(b"\n")?;
    out.flush()?;
    Ok(())
}
pub fn run(output: &str) -> Result<()> {
    // SAFETY: the signal handler only writes a lock-free AtomicBool and has
    // the required C ABI. It performs no allocation, I/O or unwinding.
    ensure!(
        unsafe {
            libc::signal(
                libc::SIGUSR1,
                cancel_signal as *const () as libc::sighandler_t,
            )
        } != libc::SIG_ERR,
        "SIGNAL_SETUP_FAILED"
    );
    let desktop = Desktop::connect()?;
    let (id, selected) = desktop.select(Some(output))?;
    let mut input = Input::new(desktop, id)?;
    reply(json!({"status":"ready","output":selected,"layout":input.desktop.state.outputs}))?;
    let stdin = std::io::stdin();
    let mut reader = stdin.lock();
    loop {
        let mut bytes = vec![];
        let count = reader
            .by_ref()
            .take(131_073)
            .read_until(b'\n', &mut bytes)?;
        if count == 0 {
            break;
        }
        ensure!(
            count <= 131_072 && bytes.last() == Some(&b'\n'),
            "REQUEST_TOO_LARGE"
        );
        let result = (|| -> Result<serde_json::Value> {
            let request: Request =
                serde_json::from_slice(&bytes).context("INVALID_WORKER_REQUEST")?;
            match request {
                Request::Stop {} => Ok(json!({"status":"stopped"})),
                Request::ReleaseAll {} => {
                    input.release()?;
                    Ok(json!({"status":"released"}))
                }
                Request::Layout {} => {
                    let current = Desktop::connect()?;
                    Ok(json!({"status":"ok","layout":current.state.outputs}))
                }
                Request::Execute {
                    action,
                    width,
                    height,
                } => {
                    CANCEL.store(false, Ordering::Release);
                    execute::execute(&mut input, &action, width, height, &CANCEL)?;
                    Ok(json!({"status":"ok"}))
                }
            }
        })();
        let stop = result.as_ref().is_ok_and(|v| v["status"] == "stopped");
        match result {
            Ok(value) => reply(value)?,
            Err(error) => reply(json!({"status":"error","code":format!("{error:#}")}))?,
        }
        if stop {
            break;
        }
    }
    input.release()?;
    Ok(())
}
