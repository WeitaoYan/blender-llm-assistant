import asyncio
import logging
import logging.handlers
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server

from .blender_client import BlenderClient
from .tools import ToolManager

_LOG_DIR = Path.home() / ".blender-assistant" / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

log_file = _LOG_DIR / "mcp_server.log"
file_handler = logging.handlers.RotatingFileHandler(
    str(log_file), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))
file_handler.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))
console_handler.setLevel(logging.INFO)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[file_handler, console_handler],
    force=True,
)
logger = logging.getLogger("mcp-server")
logger.info(f"Logging to {log_file}")


class BlenderMCPServer:
    def __init__(self, blender_url: str = "http://127.0.0.1:15800"):
        self.blender = BlenderClient(blender_url)
        self.tool_manager = ToolManager(self.blender)
        self.server = Server("blender-assistant")

        self._register_handlers()

    def _register_handlers(self):
        @self.server.list_tools()
        async def handle_list_tools():
            try:
                await self.tool_manager._refresh()
            except Exception as e:
                logger.warning(f"Failed to refresh tools from Blender: {e}")
            return self.tool_manager.list_tools()

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict | None):
            logger.info(f"Tool call: {name}({arguments})")
            result = await self.tool_manager.call_tool(name, arguments)
            logger.info(f"Tool result: {result}")
            return result

    async def run_stdio(self):
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Blender MCP Server")
    parser.add_argument("--blender-url", default="http://127.0.0.1:15800")
    args = parser.parse_args()

    server = BlenderMCPServer(blender_url=args.blender_url)

    if not await server.blender.health_check():
        logger.warning("Blender HTTP server is not reachable. Tools will be empty until connection.")

    await server.run_stdio()


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
