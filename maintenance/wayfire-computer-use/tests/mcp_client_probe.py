"""Run the official stdio client inside the private desktop harness."""
import asyncio
import base64
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    binary, output = sys.argv[1:]
    adapter = Path(binary).parents[2] / "mcp_server.py"
    params = StdioServerParameters(command=sys.executable, args=[str(adapter), "--binary", binary],
                                   env=dict(os.environ))
    async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as client:
        await client.initialize()
        listing = await client.list_tools()
        assert {tool.name for tool in listing.tools} == {
            "wayfire_start", "wayfire_act", "wayfire_stop", "wayfire_observe", "wayfire_ui_find", "wayfire_ui_tree",
        }

        async def image_call(name, arguments):
            result = await client.call_tool(name, arguments)
            assert not result.isError, result.content[0]
            metadata, image = result.content
            frame = json.loads(metadata.text)
            assert image.mimeType == "image/png"
            data = base64.b64decode(image.data, validate=True)
            assert data.startswith(b"\x89PNG\r\n\x1a\n")
            assert data == Path(frame["screenshot_path"]).read_bytes()
            return frame

        first = await image_call("wayfire_start", {"output": output, "auto_select_output": True})
        if os.environ.get("WF_UI_TEST"):
            found = await client.call_tool("wayfire_ui_find", {"role":"button", "name":"Verify location"})
            assert not found.isError, found.content
            match = found.structuredContent
            tree = await client.call_tool("wayfire_ui_tree", {"window_id":match["window_id"]})
            assert match["nodes"][0] in tree.structuredContent["nodes"]
            center = match["nodes"][0]["center"]
            await image_call("wayfire_act", {"action":{"type":"click","button":"left",**center}})
            events=json.loads((Path(os.environ["XDG_RUNTIME_DIR"])/"fixture-state.json").read_text())["events"]
            assert any(event["type"]=="located-button-clicked" for event in events)
        second = await image_call("wayfire_act", {"action": {"type": "wait", "duration_ms": 5}})
        assert second["session_id"] == first["session_id"]
        assert second["observation_id"] != first["observation_id"]

        wrong_owner = await asyncio.create_subprocess_exec(
            binary, "act", stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        rejected, _ = await wrong_owner.communicate(b'{"command":"stop","session_id":"obsolete"}')
        assert json.loads(rejected)["code"] == "UNKNOWN_SESSION"

        async with stdio_client(params) as (r2, w2), ClientSession(r2, w2) as other:
            await other.initialize()
            attached = await other.call_tool("wayfire_start", {"output": output})
            assert not attached.isError, attached.content[0]
            assert json.loads(attached.content[0].text)["session_id"] == first["session_id"]
        stale = await client.call_tool("wayfire_act", {"action": {"type": "click", "x": 1, "y": 1, "button": "left"}})
        assert stale.isError and "STALE_OBSERVATION" in stale.content[0].text
        await image_call("wayfire_observe", {})
        await image_call("wayfire_act", {"action": {"type":"click","x":300,"y":213,"button":"left"}})
        await image_call("wayfire_act", {"action": {"type":"type","text":"MCP input"}})
        fixture = Path(os.environ["XDG_RUNTIME_DIR"]) / "fixture-state.json"
        assert json.loads(fixture.read_text())["text"].endswith("MCP input")
        stopped = await client.call_tool("wayfire_stop", {})
        assert not stopped.isError and not Path(first["screenshot_path"]).exists()


if __name__ == "__main__":
    asyncio.run(main())
