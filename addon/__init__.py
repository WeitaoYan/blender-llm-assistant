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
import logging
import logging.handlers
from pathlib import Path

from .server import start_server, stop_server

logger = logging.getLogger(__name__)

_LOG_DIR = Path.home() / ".blender-llm-assistant" / "logs"


def _setup_addon_logging():
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_file = _LOG_DIR / "blender_addon.log"
    handler = logging.handlers.RotatingFileHandler(
        str(log_file), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    handler.setLevel(logging.DEBUG)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # Avoid duplicate handlers on reload
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)
        logger.info(f"Logging to {log_file}")


_setup_addon_logging()


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
            props.server_secret = uuid.uuid4().hex
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
            layout.label(text="Server not running", icon="CANCEL")
            layout.operator("llm_assistant.start_server", icon="PLAY")


classes = [
    LLMAssistantProperties,
    LLMASSISTANT_OT_copy_token,
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
