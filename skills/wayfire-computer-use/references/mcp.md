# MCP stdio adapter

Build the Rust executable with `./build.sh` in the installed skill directory. Configure the MCP host to launch the following stdio server, replacing the example path with the absolute installed path. The host process needs the same Wayfire, Portal, PipeWire and session-bus environment as the CLI.

```json
{
  "mcpServers": {
    "wayfire-computer-use": {
      "command": "uv",
      "args": ["run", "--script", "/absolute/path/to/wayfire-computer-use/mcp_server.py"]
    }
  }
}
```

The adapter declares its Python MCP SDK dependency in the script. The first uv run needs access to the package index or a populated cache. An interpreter with that SDK installed can also launch the script directly. Use `--binary PATH` to select another build of the matching Rust CLI.

| Tool | Use |
|---|---|
| `wayfire_start` | Start a session or attach to the active session. Supply `output` when several outputs exist. Pass `auto_select_output: true` only when the user authorized the Portal selector click. Returns an image. |
| `wayfire_observe` | Capture a fresh image in the attached session. Use after another client acts or focuses a window. |
| `wayfire_ui_find` | Read matching controls by role and exact name in the focused or specified window. Compare the returned output and center with the current screenshot. |
| `wayfire_ui_tree` | Read the accessible tree by window ID. Both discovery tools leave the last observation intact. |
| `wayfire_act` | Pass one bare action under `action`, using [the CLI action fields](actions.md). Inspect the last returned PNG first. The adapter pins its observation ID and generates a new request ID per call. |
| `wayfire_stop` | Stop the attached owner and inspect its cleanup result. Can interrupt an action. |

An image result contains JSON metadata followed by a base64 PNG image content block. Use an MCP host that displays image results. Call actions sequentially. After an error or a lost reply, observe before deciding on further input. Repeating a tool call creates a new request and can repeat a side effect. The explicit CLI envelope remains available for request replay with deduplication.

Stop explicitly when finished. On orderly server shutdown the adapter also requests cleanup for the owner it created. Sessions attached from another client stay under that client's control unless explicitly stopped. After abrupt termination the owner's idle timeout still applies.
