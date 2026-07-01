import logging

from mcp.types import Tool as MCPTool, TextContent
from .blender_client import BlenderClient

logger = logging.getLogger(__name__)


def _to_json_schema(flat_params: dict) -> dict:
    """Convert flat {name: {type, description, required, ...}} into
    standard JSON Schema with top-level type/object/properties/required."""
    properties = {}
    required = []
    for name, schema in flat_params.items():
        prop = dict(schema)
        is_required = prop.pop("required", False)
        properties[name] = prop
        if is_required:
            required.append(name)
    result = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    return result


class ToolManager:
    def __init__(self, blender: BlenderClient):
        self.blender = blender
        self._tools: list[MCPTool] = []

    async def _refresh(self):
        resp = await self.blender.list_tools()
        self._tools = []
        for t in resp.get("tools", []):
            raw_params = t.get("parameters", {})
            input_schema = _to_json_schema(raw_params)
            self._tools.append(
                MCPTool(
                    name=t["name"],
                    description=t.get("description", ""),
                    inputSchema=input_schema,
                )
            )
        logger.info(f"Refreshed {len(self._tools)} tools from Blender")

    def list_tools(self) -> list[MCPTool]:
        return self._tools

    async def call_tool(self, name: str, arguments: dict | None) -> list[TextContent]:
        logger.info(f"MCP tool call: {name}({arguments})")
        result = await self.blender.call_tool(name, arguments or {})
        logger.debug(f"MCP tool result for {name}: {result}")
        return [TextContent(type="text", text=str(result))]
