# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp==1.30.0"]
# ///
"""Stdio MCP adapter for the local Wayfire owner."""
import argparse
import asyncio
import base64
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent
from pydantic import Field


def create_server(binary: Path) -> FastMCP:
    session_id = None
    observation_id = None
    created = False
    stopping = False
    busy = asyncio.Lock()

    async def cli(*args, body=None):
        process = await asyncio.create_subprocess_exec(
            str(binary), *args, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        try:
            data = json.dumps(body).encode() if body is not None else b""
            output, _ = await process.communicate(data)
        finally:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
        result = json.loads(output)
        if process.returncode or result.get("status") == "error":
            raise ValueError(json.dumps(result))
        return result

    async def stop_session():
        nonlocal session_id, observation_id, created, stopping
        if stopping:
            raise ValueError("STOP_IN_PROGRESS")
        if session_id is None:
            raise ValueError("NO_ATTACHED_SESSION")
        observation_id = None
        stopping = True
        try:
            result = await cli("act", body={"command": "stop", "session_id": session_id})
        finally:
            stopping = False
        session_id = observation_id = None
        created = False
        return result

    @asynccontextmanager
    async def lifespan(_server):
        try:
            yield {}
        finally:
            if created and session_id:
                await stop_session()

    server = FastMCP(
        "wayfire-computer-use",
        instructions="Inspect each returned screenshot before choosing input. Choose the output "
                     "with the user on multi-output desktops. Stop the session at completion.",
        lifespan=lifespan,
    )

    def image_result(result):
        nonlocal observation_id
        if result["session_id"] != session_id:
            raise ValueError("SESSION_CHANGED")
        data = Path(result["screenshot_path"]).read_bytes()
        image = ImageContent(type="image", mimeType="image/png",
                             data=base64.b64encode(data).decode("ascii"))
        metadata = TextContent(type="text", text=json.dumps(result))
        observation_id = result["observation_id"]
        return CallToolResult(content=[metadata, image])

    async def capture():
        nonlocal observation_id
        observation_id = None
        status = await cli("status")
        if status["session_id"] != session_id:
            raise ValueError("SESSION_CHANGED")
        result = await cli("act", body={
            "session_id": session_id, "observation_id": status["observation_id"],
            "request_id": uuid.uuid4().hex, "action": {"type": "screenshot"},
        })
        return image_result(result)

    @server.tool()
    async def wayfire_start(output: str | None = None, auto_select_output: bool = False,
                            idle_timeout: int = Field(default=300, ge=1, le=3600)) -> CallToolResult:
        """Start or attach and return the first PNG. Auto-selection authorizes one selector click."""
        nonlocal session_id, observation_id, created
        if stopping or busy.locked():
            raise ValueError("ADAPTER_BUSY")
        async with busy:
            args = ["start", "--idle-timeout", str(idle_timeout)]
            if output is not None:
                args.extend(["--output", output])
            if auto_select_output:
                args.append("--auto-select-output")
            result = await cli(*args)
            if result["status"] not in ("active", "ready"):
                raise ValueError(json.dumps(result))
            if output is not None and result.get("output") != output:
                raise ValueError("ACTIVE_OUTPUT_MISMATCH")
            created = result["status"] == "ready" or (created and session_id == result["session_id"])
            session_id = result["session_id"]
            observation_id = None
            return image_result(result) if result["status"] == "ready" else await capture()

    @server.tool()
    async def wayfire_observe() -> CallToolResult:
        """Get a fresh PNG of the attached session, including after external focus changes."""
        if stopping or busy.locked() or not session_id:
            raise ValueError("ADAPTER_BUSY_OR_NO_SESSION")
        async with busy:
            return await capture()

    @server.tool()
    async def wayfire_act(action: dict) -> CallToolResult:
        """Execute one Wayfire action against the last returned image and return a new PNG.
        Inspect the image before input. Examples include {"type":"click","x":30,"y":20,"button":"left"}
        and {"type":"type","text":"hello"}. Other types include move, double_click, drag (path of
        x/y points), scroll (x, y, scroll_x, scroll_y), keypress (keys), wait (duration_ms),
        and wait_stable (frames). After an error, observe before further input.
        """
        nonlocal observation_id
        if stopping or busy.locked() or not observation_id:
            raise ValueError("ADAPTER_BUSY_OR_OBSERVATION_REQUIRED")
        async with busy:
            envelope = {"session_id": session_id, "observation_id": observation_id,
                        "request_id": uuid.uuid4().hex, "action": action}
            observation_id = None
            return image_result(await cli("act", body=envelope))

    @server.tool()
    async def wayfire_stop() -> dict:
        """Stop the attached desktop session, including an in-progress action, and report cleanup."""
        return await stop_session()

    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path,
                        default=Path(__file__).resolve().parent / "target/release/wayfire-computer-use")
    create_server(parser.parse_args().binary.resolve()).run(transport="stdio")
