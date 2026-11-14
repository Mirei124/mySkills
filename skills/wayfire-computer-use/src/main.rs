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
    },
    #[command(hide = true)]
    Serve {
        #[arg(long)]
        output: Option<String>,
        #[arg(long = "auto-select-output", alias = "auto-select-single-output")]
        auto_select_single_output: bool,
    },
    Act,
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
    ProbeCapture {
        #[arg(long)]
        output: Option<String>,
        #[arg(long)]
        path: std::path::PathBuf,
        #[arg(long)]
        auto_select: bool,
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
        } => session::start(output, auto_select_single_output).await,
        Command::Serve {
            output,
            auto_select_single_output,
        } => {
            if let Err(error) = session::serve(output, auto_select_single_output).await {
                eprintln!("{error:#}");
                std::process::exit(1);
            }
            return;
        }
        Command::Act => {
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
        Command::Doctor => diagnostics::doctor().await,
        Command::Validate => stdin_json()
            .and_then(|value| serde_json::from_value::<action::Action>(value).map_err(Into::into))
            .and_then(|action| {
                action.validate()?;
                Ok(json!({"status":"valid","action":action}))
            }),
    };
    match result {
        Ok(value) => {
            println!("{value}");
            if value["status"] == "error" {
                std::process::exit(1);
            }
        }
        Err(error) => {
            println!(
                "{}",
                json!({"status":"error","code":error.to_string(),"action_executed":false,"selector_click_may_have_executed":selector_click_may_have_executed,"retryable":false})
            );
            std::process::exit(1);
        }
    }
}

fn stdin_json() -> anyhow::Result<serde_json::Value> {
    let mut text = String::new();
    std::io::stdin().take(131_073).read_to_string(&mut text)?;
    anyhow::ensure!(text.len() <= 131_072, "REQUEST_TOO_LARGE");
    Ok(serde_json::from_str(&text)?)
}
