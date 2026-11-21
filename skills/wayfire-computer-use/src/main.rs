use clap::{Parser, Subcommand};
use serde_json::json;
use std::io::Read;
mod action;
mod capture;
mod desktop;
mod diagnostics;
mod execute;
mod portal;
mod probe;
mod session;
mod toplevel;
mod ui;
mod worker;

#[derive(Parser)]
#[command(about = "Wayfire desktop computer use")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}
#[derive(Subcommand)]
enum Command {
    Start {
        #[arg(long)]
        output: Option<String>,
        #[arg(long = "auto-select-output", alias = "auto-select-single-output")]
        auto_select_single_output: bool,
        /// Seconds of inactivity before the owner stops.
        #[arg(long, visible_alias = "idle-timeout-secs", default_value_t = 300, value_parser = clap::value_parser!(u64).range(1..=3600))]
        idle_timeout: u64,
    },
    #[command(hide = true)]
    Serve {
        #[arg(long)]
        output: Option<String>,
        #[arg(long = "auto-select-output", alias = "auto-select-single-output")]
        auto_select_single_output: bool,
        /// Seconds of inactivity before the owner stops.
        #[arg(long, visible_alias = "idle-timeout-secs", default_value_t = 300, value_parser = clap::value_parser!(u64).range(1..=3600))]
        idle_timeout: u64,
    },
    Act {
        #[arg(long)]
        latest: bool,
    },
    Stop,
    Status,
    Capabilities,
    #[command(name = "release_all", alias = "release-all")]
    ReleaseAll,
    #[command(hide = true)]
    Worker {
        #[arg(long)]
        output: String,
    },
    Validate,
    Doctor,
    /// List application windows or request focus through Wayfire IPC.
    Toplevel {
        #[command(subcommand)]
        command: ToplevelCommand,
    },
    /// Inspect a mapped window through AT-SPI without sending input.
    Ui {
        #[command(subcommand)]
        command: UiCommand,
    },
    ProbeCapture {
        #[arg(long)]
        output: Option<String>,
        #[arg(long)]
        path: std::path::PathBuf,
        #[arg(long)]
        auto_select: bool,
    },
}
#[derive(Subcommand)]
enum ToplevelCommand {
    /// List mapped application toplevels without changing focus.
    List,
    /// Wait for a mapped application window, optionally requiring focus.
    Wait {
        #[arg(
            long,
            required_unless_present = "title_regex",
            conflicts_with = "title_regex"
        )]
        app_id: Option<String>,
        #[arg(long)]
        title_regex: Option<regex::Regex>,
        #[arg(long,value_parser=["focused","mapped"],conflicts_with="focused")]
        state: Option<String>,
        #[arg(long)]
        focused: bool,
        #[arg(long, visible_alias="timeout-secs", default_value_t=10,value_parser=clap::value_parser!(u64).range(1..=120))]
        timeout: u64,
    },
    /// Request focus for one listed window and verify the resulting focus.
    Focus {
        #[arg(long, value_parser = clap::value_parser!(u64).range(1..))]
        id: u64,
        /// Require the window to still belong to this PID.
        #[arg(long, value_parser = clap::value_parser!(u32).range(1..))]
        pid: Option<u32>,
    },
}
#[derive(Subcommand)]
enum UiCommand {
    Tree {
        #[arg(long)]
        window_id: u64,
    },
    /// Find exact accessible names in the specified or focused window.
    Find {
        #[arg(long)]
        role: String,
        #[arg(long)]
        name: String,
        #[arg(long)]
        window_id: Option<u64>,
    },
}
#[tokio::main]
async fn main() {
    let command = Cli::parse().command;
    let selector_click_may_have_executed = matches!(
        &command,
        Command::ProbeCapture {
            auto_select: true,
            ..
        } | Command::Start {
            auto_select_single_output: true,
            ..
        }
    );
    let result = match command {
        Command::Start {
            output,
            auto_select_single_output,
            idle_timeout,
        } => session::start(output, auto_select_single_output, idle_timeout).await,
        Command::Serve {
            output,
            auto_select_single_output,
            idle_timeout,
        } => {
            if let Err(error) =
                session::serve(output, auto_select_single_output, idle_timeout).await
            {
                eprintln!("{error:#}");
                std::process::exit(1);
            }
            return;
        }
        Command::Act { latest: true } => match stdin_json() {
            Ok(action) => session::act_latest(action).await,
            Err(error) => Err(error),
        },
        Command::Act { latest: false } => {
            let mut input = String::new();
            match std::io::stdin().read_to_string(&mut input) {
                Ok(_) => match serde_json::from_str(&input) {
                    Ok(value) => session::send(value).await,
                    Err(error) => Err(error.into()),
                },
                Err(error) => Err(error.into()),
            }
        }
        Command::Stop => session::send(json!({"command":"stop"})).await,
        Command::Status => session::send(json!({"command":"status"})).await,
        Command::Capabilities => session::send(json!({"command":"capabilities"})).await,
        Command::ReleaseAll => session::send(json!({"command":"release_all"})).await,
        Command::Worker { output } => {
            if let Err(error) = worker::run(&output) {
                eprintln!("{error:#}");
                std::process::exit(1);
            }
            return;
        }
        Command::ProbeCapture {
            output,
            path,
            auto_select,
        } => probe::capture(output, path, auto_select).await,
        Command::Ui { command } => match command {
            UiCommand::Tree { window_id } => ui::inspect(Some(window_id), None).await,
            UiCommand::Find {
                role,
                name,
                window_id,
            } => ui::inspect(window_id, Some((role, name))).await,
        },
        Command::Doctor => diagnostics::doctor().await,
        Command::Toplevel { command } => match command {
            ToplevelCommand::Wait {
                app_id,
                title_regex,
                state,
                focused,
                timeout,
            } => {
                toplevel::wait(
                    app_id.as_deref(),
                    title_regex.as_ref(),
                    focused || state.as_deref() == Some("focused"),
                    timeout,
                )
                .await
            }
            ToplevelCommand::List => toplevel::list().await,
            ToplevelCommand::Focus { id, pid } => {
                session::focus_toplevel(toplevel::FocusTarget { id, pid }).await
            }
        },
        Command::Validate => stdin_json()
            .and_then(|value| serde_json::from_value::<action::Action>(value).map_err(Into::into))
            .and_then(|action| {
                action.validate()?;
                Ok(json!({"status":"valid","action":action}))
            }),
    };
    match result {
        Ok(mut value) => {
            add_recovery(&mut value);
            println!("{value}");
            if value["status"] == "error" {
                std::process::exit(1);
            }
        }
        Err(error) => {
            let code = error.to_string();
            let mut response = json!({"status":"error","code":code,"action_executed":false,"selector_click_may_have_executed":selector_click_may_have_executed,"retryable":false});
            add_recovery(&mut response);
            println!("{response}");
            std::process::exit(1);
        }
    }
}

fn add_recovery(result: &mut serde_json::Value) {
    let Some(code) = result["code"].as_str() else {
        return;
    };
    if matches!(
        code,
        "STALE_OBSERVATION"
            | "LAYOUT_CHANGED"
            | "SESSION_UNAVAILABLE"
            | "SESSION_RESPONSE_TIMEOUT"
            | "ACTION_TIMEOUT"
            | "INPUT_RESPONSE_TIMEOUT"
            | "CAPTURE_TIMEOUT"
            | "CAPTURE_ENDED"
            | "CAPTURE_UNAVAILABLE"
            | "PORTAL_SERVICE_LOST"
    ) || code.starts_with("PIPEWIRE_STREAM_ERROR")
        || result["capture_error"].is_string()
        || matches!(
            result["stop_reason"].as_str(),
            Some("capture ended" | "portal session or service lost" | "idle timeout")
        )
    {
        result["recovery"] = json!([
            ["stop"],
            ["start", "--output", "<output>"],
            ["toplevel", "list"],
            ["toplevel", "focus", "--id", "<window-id>"],
            ["act", "--latest"]
        ]);
        result["recovery_screenshot_action"] = json!({"type":"screenshot"});
    }
}

fn stdin_json() -> anyhow::Result<serde_json::Value> {
    let mut text = String::new();
    std::io::stdin().take(131_073).read_to_string(&mut text)?;
    anyhow::ensure!(text.len() <= 131_072, "REQUEST_TOO_LARGE");
    Ok(serde_json::from_str(&text)?)
}

#[cfg(test)]
mod recovery_tests {
    use super::*;
    #[test]
    fn permanent_capture_errors_preserve_the_cause_and_order_the_recovery_steps() {
        for mut result in [
            json!({"code":"CAPTURE_ENDED"}),
            json!({"code":"PIPEWIRE_STREAM_ERROR: disconnected"}),
            json!({"code":"INVALID_FRAME_RANGE","capture_error":"INVALID_FRAME_RANGE"}),
            json!({"code":"ACTION_CANCELLED","capture_error":"UNSUPPORTED_FRAME_FORMAT"}),
        ] {
            let original = result.clone();
            add_recovery(&mut result);
            assert_eq!(result["code"], original["code"]);
            assert_eq!(result["capture_error"], original["capture_error"]);
            assert_eq!(
                result["recovery"],
                json!([
                    ["stop"],
                    ["start", "--output", "<output>"],
                    ["toplevel", "list"],
                    ["toplevel", "focus", "--id", "<window-id>"],
                    ["act", "--latest"]
                ])
            );
            assert_eq!(
                result["recovery_screenshot_action"],
                json!({"type":"screenshot"})
            );
        }
        let mut user_cancel = json!({"code":"ACTION_CANCELLED"});
        add_recovery(&mut user_cancel);
        assert!(user_cancel.get("recovery").is_none());
    }
}
