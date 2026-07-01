"""Unit tests for blender-mcp-server.

These tests mock the Blender HTTP client so they don't require
a running Blender instance.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_blender_client():
    """Create a mock BlenderClient that returns canned responses."""
    client = MagicMock()
    client.health_check = AsyncMock(return_value=True)

    # Canned tool list
    client.list_tools = AsyncMock(return_value={
        "tools": [
            {
                "name": "create_object",
                "description": "Create a new mesh object",
                "parameters": {
                    "type": {
                        "type": "string",
                        "description": "Object type",
                        "required": True,
                    },
                },
            },
            {
                "name": "get_scene_info",
                "description": "Get scene information",
                "parameters": {},
            },
        ],
    })

    # Canned tool call result
    client.call_tool = AsyncMock(return_value={
        "result": {"name": "Cube", "type": "cube"},
    })

    client.get_scene_info = AsyncMock(return_value={
        "scene_name": "Scene",
        "objects": [{"name": "Cube", "type": "MESH"}],
    })

    return client


class TestToolManager:
    """Test MCP tool management."""

    def test_refresh_tools(self, mock_blender_client):
        from mcp_server.tools import ToolManager

        mgr = ToolManager(mock_blender_client)
        mgr._tools = []  # reset

        import asyncio
        asyncio.run(mgr._refresh())

        tools = mgr.list_tools()
        assert len(tools) == 2
        names = [t.name for t in tools]
        assert "create_object" in names
        assert "get_scene_info" in names

    def test_list_tools(self, mock_blender_client):
        from mcp_server.tools import ToolManager

        mgr = ToolManager(mock_blender_client)
        import asyncio
        asyncio.run(mgr._refresh())

        tools = mgr.list_tools()
        for t in tools:
            assert t.name
            assert t.inputSchema
            assert "type" in t.inputSchema
            assert t.inputSchema["type"] == "object"

    def test_call_tool(self, mock_blender_client):
        from mcp_server.tools import ToolManager

        mgr = ToolManager(mock_blender_client)
        import asyncio
        asyncio.run(mgr._refresh())

        result = asyncio.run(mgr.call_tool("create_object", {"type": "cube"}))
        assert len(result) == 1
        assert "Cube" in result[0].text


class TestJSONSchemaConversion:
    """Test flat parameter to JSON Schema conversion."""

    def test_empty_params(self):
        from mcp_server.tools import _to_json_schema
        schema = _to_json_schema({})
        assert schema == {"type": "object", "properties": {}}

    def test_required_params(self):
        from mcp_server.tools import _to_json_schema
        schema = _to_json_schema({
            "name": {
                "type": "string",
                "description": "Object name",
                "required": True,
            },
        })
        assert schema["required"] == ["name"]
        assert schema["properties"]["name"]["type"] == "string"

    def test_optional_params(self):
        from mcp_server.tools import _to_json_schema
        schema = _to_json_schema({
            "count": {
                "type": "integer",
                "description": "Count",
                "required": False,
            },
        })
        assert "required" not in schema or schema["required"] == []

    def test_required_is_removed_from_property(self):
        from mcp_server.tools import _to_json_schema
        schema = _to_json_schema({
            "name": {"type": "string", "required": True},
        })
        assert "required" not in schema["properties"]["name"]


class TestBlenderMCPServer:
    """Test MCP server registration."""

    def test_server_initialization(self, mock_blender_client):
        from mcp_server.main import BlenderMCPServer
        server = BlenderMCPServer(blender_url="http://127.0.0.1:15800")
        assert server.server is not None
        assert server.server.name == "blender-assistant"

    def test_server_creation(self):
        """Verify the server module can be instantiated without Blender."""
        from mcp_server.main import BlenderMCPServer
        server = BlenderMCPServer()
        assert server.blender is not None
        assert server.tool_manager is not None


class TestBlenderClient:
    """Test BlenderClient with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        from mcp_server.blender_client import BlenderClient

        client = BlenderClient()
        with patch.object(client._client, 'get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            result = await client.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        from mcp_server.blender_client import BlenderClient

        client = BlenderClient()
        with patch.object(client._client, 'get') as mock_get:
            import httpx
            mock_get.side_effect = httpx.ConnectError("Connection refused")

            result = await client.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_list_tools(self):
        from mcp_server.blender_client import BlenderClient

        client = BlenderClient()
        with patch.object(client._client, 'get') as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "tools": [{"name": "create_object"}],
            }
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await client.list_tools()
            assert result["tools"][0]["name"] == "create_object"

    @pytest.mark.asyncio
    async def test_call_tool_success(self):
        from mcp_server.blender_client import BlenderClient

        client = BlenderClient()
        sse_text = "event: success\ndata: {\"result\": {\"name\": \"Cube\"}}\n\n"

        with patch.object(client._client, 'post') as mock_post, \
             patch.object(client._client, 'stream') as mock_stream:
            mock_post_resp = MagicMock()
            mock_post_resp.json.return_value = {"task_id": "test-123"}
            mock_post_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_post_resp

            mock_sse_resp = MagicMock()
            mock_sse_resp.__aenter__ = AsyncMock(return_value=mock_sse_resp)
            mock_sse_resp.__aexit__ = AsyncMock()

            async def _aiter_lines():
                yield "event: success"
                yield 'data: {"result": {"name": "Cube"}}'
                yield ""
            mock_sse_resp.aiter_lines = _aiter_lines

            mock_sse_resp.raise_for_status = MagicMock()
            mock_stream.return_value = mock_sse_resp

            result = await client.call_tool("create_object", {"type": "cube"})
            assert result["name"] == "Cube"
