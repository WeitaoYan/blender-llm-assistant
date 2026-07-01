# blender-llm-mcp

MCP (Model Context Protocol) server for Blender 3D.

Connect AI assistants to Blender via [Model Context Protocol](https://modelcontextprotocol.io).

## Usage

Requires the [Blender LLM Assistant](https://github.com/WeitaoYan/blender-llm-assistant) addon running in Blender (HTTP API on `127.0.0.1:15800`).

```bash
# Install
pip install blender-llm-mcp

# Run
blender-llm-mcp

# Or with uvx (no install needed)
uvx blender-llm-mcp

# Custom Blender URL
blender-llm-mcp --blender-url http://127.0.0.1:15800
```

## Configuration in Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "blender": {
      "command": "uvx",
      "args": ["blender-llm-mcp"]
    }
  }
}
```

## How it works

```
Claude Desktop / VS Code / any MCP client
    │  MCP stdio protocol
    ▼
blender-llm-mcp
    │  HTTP (SSE)
    ▼
Blender LLM Assistant addon (inside Blender)
    │  Blender Python API (bpy)
    ▼
Blender 3D scene
```

The MCP server translates MCP tool calls into HTTP requests to the Blender addon.
