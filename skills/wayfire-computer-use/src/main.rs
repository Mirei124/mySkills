use clap::{Parser, Subcommand};
use serde_json::json;
use std::io::Read;
mod action;
mod capture;
mod desktop;
mod execute;
mod portal;
mod probe;

#[derive(Parser)]
#[command(about = "Wayfire computer-use Rust migration (development)")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}
#[derive(Subcommand)]
enum Command {
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
        }
    );
    let result = match command {
        Command::ProbeCapture{output,path,auto_select}=>probe::capture(output,path,auto_select).await,
        Command::Doctor => desktop::Desktop::connect().map(|desktop|json!({"status":"diagnostic","outputs":desktop.state.outputs,"protocol_versions":desktop.state.globals,"runtime":"Rust","sends_input":false})),
        Command::Validate => {
            let mut input = String::new();
            std::io::stdin().read_to_string(&mut input).map_err(anyhow::Error::from)
                .and_then(|_| serde_json::from_str::<action::Action>(&input).map_err(Into::into))
                .and_then(|action| { action.validate()?; Ok(json!({"status":"valid","action":action})) })
        }
    };
    match result {
        Ok(value) => println!("{value}"),
        Err(error) => {
            println!(
                "{}",
                json!({"status":"error","code":error.to_string(),"action_executed":false,"selector_click_may_have_executed":selector_click_may_have_executed,"retryable":false})
            );
            std::process::exit(1);
        }
    }
}
