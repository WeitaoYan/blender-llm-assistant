# 测试

## 前提

### HTTP API 集成测试

需要一个运行中的 Blender 实例，已加载 LLM Assistant 插件并启动 HTTP Server：

```powershell
# 1. 启动 Blender（后台模式）
blender --background

# 2. 在 Blender 的 3D Viewport 侧边栏
#    → LLM Assistant 标签
#    → 点击 Start HTTP Server（端口 15800）

# 3. 运行测试
cd extensions
pytest tests/test_http_api.py -v --timeout=120
```

### MCP Server 单元测试

无需 Blender，使用 mock：

```bash
cd extensions/mcp-server
pip install -e .
pip install pytest pytest-asyncio
pytest ../tests/test_mcp_server.py -v
```
