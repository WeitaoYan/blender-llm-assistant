import uuid

import bpy  # type: ignore

bl_info = {
    "name": "Blender LLM Assistant",
    "author": "Yan Weitao",
    "version": (1, 0, 0),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > LLM Assistant",
    "description": "Expose Blender modeling tools via HTTP API for AI assistants",
    "doc_url": "https://github.com/WeitaoYan/blender-llm-assistant",
    "tracker_url": "https://github.com/WeitaoYan/blender-llm-assistant",
    "support": "COMMUNITY",
    "category": "Development",
}

import threading
from pathlib import Path

from .server import start_server, stop_server


_CONFIG_DIR = Path.home() / ".blender-llm-assistant"
_TOKEN_FILE = _CONFIG_DIR / "token.txt"


def _load_persistent_token() -> str:
    """从磁盘加载持久化的 token，不存在则返回空字符串。"""
    try:
        if _TOKEN_FILE.exists():
            return _TOKEN_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


def _save_persistent_token(token: str):
    """将 token 持久化到磁盘。"""
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(token, encoding="utf-8")
    except Exception:
        pass



def _server_secret_get(self):
    """读取 token：优先返回场景中存储的值，否则从磁盘懒加载。"""
    stored = self.get("server_secret", "")
    if stored:
        return stored
    saved = _load_persistent_token()
    if saved:
        self["server_secret"] = saved
        return saved
    return ""


def _server_secret_set(self, value):
    """写入 token 并持久化到磁盘。"""
    self["server_secret"] = value
    if value:
        _save_persistent_token(value)


class LLMAssistantProperties(bpy.types.PropertyGroup):
    server_port: bpy.props.IntProperty(
        name="Server Port",
        description="Port for the HTTP server",
        default=15800,
        min=1024,
        max=65535,
    )
    server_secret: bpy.props.StringProperty(
        name="Secret Token",
        description="Bearer token for HTTP API authentication. Auto-generated if left empty.",
        default="",
        get=_server_secret_get,
        set=_server_secret_set,
    )
    server_running: bpy.props.BoolProperty(
        name="Server Running",
        default=False,
    )


class LLMASSISTANT_OT_copy_token(bpy.types.Operator):
    bl_idname = "llm_assistant.copy_token"
    bl_label = "Copy Token"
    bl_description = "Copy the server token to clipboard"

    def execute(self, context):
        props = context.scene.llm_assistant_props
        context.window_manager.clipboard = props.server_secret
        self.report({"INFO"}, "Token copied to clipboard")
        return {"FINISHED"}


class LLMASSISTANT_OT_regenerate_token(bpy.types.Operator):
    bl_idname = "llm_assistant.regenerate_token"
    bl_label = "Regenerate Token"
    bl_description = "Generate a new random token and save it persistently"

    def execute(self, context):
        props = context.scene.llm_assistant_props
        if props.server_running:
            self.report({"WARNING"}, "Stop the server before regenerating token")
            return {"CANCELLED"}
        new_token = uuid.uuid4().hex
        props.server_secret = new_token
        _save_persistent_token(new_token)
        self.report({"INFO"}, "New token generated and saved")
        return {"FINISHED"}


class LLMASSISTANT_OT_start_server(bpy.types.Operator):
    bl_idname = "llm_assistant.start_server"
    bl_label = "Start HTTP Server"
    bl_description = "Start the HTTP server for LLM assistant"

    def execute(self, context):
        props = context.scene.llm_assistant_props
        if props.server_running:
            self.report({"WARNING"}, "Server already running")
            return {"CANCELLED"}

        port = props.server_port
        if not props.server_secret:
            # 优先从磁盘加载持久化 token，没有则生成新的并保存
            saved_token = _load_persistent_token()
            if saved_token:
                props.server_secret = saved_token
            else:
                props.server_secret = uuid.uuid4().hex
                _save_persistent_token(props.server_secret)
        thread = threading.Thread(
            target=start_server,
            args=(port, props.server_secret),
            daemon=True,
        )
        thread.start()
        props.server_running = True
        self.report({"INFO"}, f"Server started on port {port}")
        return {"FINISHED"}


class LLMASSISTANT_OT_stop_server(bpy.types.Operator):
    bl_idname = "llm_assistant.stop_server"
    bl_label = "Stop HTTP Server"
    bl_description = "Stop the HTTP server for LLM assistant"

    def execute(self, context):
        props = context.scene.llm_assistant_props
        if not props.server_running:
            self.report({"WARNING"}, "Server not running")
            return {"CANCELLED"}

        stop_server()
        props.server_running = False
        self.report({"INFO"}, "Server stopped")
        return {"FINISHED"}


class LLMASSISTANT_PT_panel(bpy.types.Panel):
    bl_label = "LLM Assistant"
    bl_idname = "LLMASSISTANT_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "LLM Assistant"

    def draw(self, context):
        layout = self.layout
        props = context.scene.llm_assistant_props

        layout.prop(props, "server_port")

        if props.server_running:
            layout.label(text=f"Running on port {props.server_port}", icon="CHECKBOX_HLT")
            row = layout.row(align=True)
            row.label(text=f"Token: {props.server_secret}")
            row.operator("llm_assistant.copy_token", text="", icon="COPYDOWN")
            layout.operator("llm_assistant.stop_server", icon="CANCEL")
        else:
            layout.prop(props, "server_secret")
            row = layout.row(align=True)
            row.operator("llm_assistant.copy_token", text="Copy Token", icon="COPYDOWN")
            row.operator("llm_assistant.regenerate_token", text="New Token", icon="FILE_REFRESH")
            layout.label(text="Server not running", icon="CANCEL")
            layout.operator("llm_assistant.start_server", icon="PLAY")


classes = [
    LLMAssistantProperties,
    LLMASSISTANT_OT_copy_token,
    LLMASSISTANT_OT_regenerate_token,
    LLMASSISTANT_OT_start_server,
    LLMASSISTANT_OT_stop_server,
    LLMASSISTANT_PT_panel,
]


def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except RuntimeError:
            pass
    if not hasattr(bpy.types.Scene, "llm_assistant_props"):
        bpy.types.Scene.llm_assistant_props = bpy.props.PointerProperty(type=LLMAssistantProperties)

    # 预加载持久化 token：如果场景中 token 为空，尝试从磁盘加载
    saved_token = _load_persistent_token()
    if saved_token:
        for scene in bpy.data.scenes:
            props = scene.llm_assistant_props
            if not props.server_secret:
                props.server_secret = saved_token


def unregister():
    try:
        stop_server()
    except Exception:
        pass
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    try:
        del bpy.types.Scene.llm_assistant_props
    except AttributeError:
        pass
