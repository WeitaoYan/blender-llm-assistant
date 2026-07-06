# blender-llm-mcp

MCP (Model Context Protocol) server for Blender 3D — expose Blender modeling tools to AI assistants via the Model Context Protocol.

GitHub: [WeitaoYan/blender-llm-assistant](https://github.com/WeitaoYan/blender-llm-assistant)

## Overview

`blender-llm-mcp` is the **MCP server** component of the Blender LLM Assistant project. It acts as a bridge between AI assistants (Claude Desktop, VS Code, etc.) and the Blender 3D software.

**This package alone is NOT enough** — it requires the [Blender LLM Assistant](https://github.com/WeitaoYan/blender-llm-assistant) addon to be installed and running inside Blender. The addon exposes an HTTP API on `127.0.0.1:15800`, and this MCP server translates MCP tool calls into HTTP requests to that API.

### Architecture

```
AI Assistant (Claude / VS Code)
    │  MCP stdio protocol
    ▼
blender-llm-mcp (this package)
    │  HTTP + SSE, Bearer Token auth
    ▼
Blender LLM Assistant addon ← must be running in Blender
    │  Blender Python API (bpy)
    ▼
Blender 3D scene
```

## Usage

Requires the [Blender LLM Assistant](https://github.com/WeitaoYan/blender-llm-assistant) addon running in Blender (HTTP API on `127.0.0.1:15800`).

The Blender addon uses **Bearer Token authentication**. After starting the server in Blender, copy the token from the panel and pass it to the MCP server.

```bash
# Install
pip install blender-llm-mcp

# Run with token
blender-llm-mcp --blender-token <token-from-blender-panel>

# Or with uvx (no install needed)
uvx blender-llm-mcp --blender-token <token-from-blender-panel>

# Custom Blender URL
blender-llm-mcp --blender-url http://127.0.0.1:15800 --blender-token <token>
```

## Configuration in Claude Desktop

First set the token as an environment variable, then reference it in the config:

```bash
export BLENDER_TOKEN="<token-from-blender-panel>"
```

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "blender": {
      "command": "uvx",
      "args": ["blender-llm-mcp", "--blender-token", "${BLENDER_TOKEN}"]
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
