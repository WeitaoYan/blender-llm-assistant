# Blender LLM Assistant — Extensions

Blender 3D 建模工具的 AI 助手基础设施。

## 组件

```
extensions/
├── addon/           Blender 插件（HTTP API 服务）
└── mcp-server/      MCP 协议网关（uvx / PyPI）
```

### addon

在 Blender 内部运行 HTTP 服务器，暴露 55+ 建模工具 API。标准 Blender 插件格式，支持手动安装和 [Blender Extensions 平台](https://extensions.blender.org) 发布。

- **兼容性**：已在 Blender **4.5** 上测试通过
- 依赖：无（使用 Python 标准库 `http.server`）
- 端口：`127.0.0.1:15800`
- 鉴权：Bearer Token（面板自动生成）
- 协议：REST + SSE 流式结果

> **版本注意事项：** 如使用非 4.5 版本，请注意以下潜在兼容点：
>
> - `bpy.context.mode` 返回格式（4.5 中为 `"EDIT_MESH"` 而非旧版的 `"EDIT"`）
> - `shade_smooth`、`proportional_edit`、`normals` 相关 API 在 4.5 中的调整

### mcp-server

将 Blender 插件的 HTTP API 转换为 [Model Context Protocol](https://modelcontextprotocol.io) 标准接口，让任何 MCP 客户端（Claude Desktop、VS Code、自定义 Agent 等）都能调用 Blender 工具。

```bash
# uvx 运行（无需安装）
uvx blender-llm-mcp --blender-token <粘贴上面复制的 Token>

# 从源码安装
pip install -e ./mcp-server
blender-llm-mcp
```

- 依赖：`mcp`、`httpx`

## 架构

```
MCP 客户端（Claude Desktop / VS Code / Agent Core）
    │  MCP stdio 协议
    ▼
blender-llm-mcp          ← 已发布到 PyPI
    │  HTTP + SSE
    ▼
Blender 插件 (HTTP + SSE)
    │  bpy API
    ▼
Blender 3D 场景
```

## 快速开始

```bash
# 1. 启动 Blender 并开启插件
blender
# 在 3D Viewport 侧边栏 → LLM Assistant → Start HTTP Server
# 复制面板中显示的 Token

# 2. 运行 MCP Server（传入 Token）
uvx blender-llm-mcp --blender-token <粘贴上面复制的 Token>
```

## 发布

```bash
# 打包插件
python package_addon.py

# 发布 MCP Server 到 PyPI
cd mcp-server
pip install build twine
python -m build
twine upload dist/*
```
