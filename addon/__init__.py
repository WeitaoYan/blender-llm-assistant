import sys
import subprocess
import bpy  # type: ignore

bl_info = {
    "name": "Blender LLM Assistant",
    "author": "Yan Weitao",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > LLM Assistant",
    "description": "Expose Blender modeling tools via HTTP API for AI assistants",
    "doc_url": "https://github.com/your-org/blender-assistant",
    "tracker_url": "https://github.com/your-org/blender-assistant/issues",
    "support": "COMMUNITY",
    "category": "Development",
}

# --- 自动安装缺失的第三方依赖 ---
REQUIRED_PACKAGES = ["fastapi", "uvicorn", "websockets"]


def _ensure_dependencies():
    """检查并安装缺失的 pip 包到 Blender 的 Python 环境中"""
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if not missing:
        return True

    # 使用 Blender 自带的 Python 安装缺失的包
    python_exe = sys.executable
    try:
        subprocess.check_call(
            [python_exe, "-m", "pip", "install", *missing],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        print(f"[LLM Assistant] 自动安装失败: {missing}")
        print(f"[LLM Assistant] 请手动运行: {python_exe} -m pip install {' '.join(missing)}")
        return False


if not _ensure_dependencies():
    raise ImportError(
        "无法自动安装依赖，请在 Blender 的 Python 中手动安装:\n"
        f"{sys.executable} -m pip install {' '.join(REQUIRED_PACKAGES)}"
    )

import threading
import logging
import logging.handlers
from pathlib import Path

from .server import start_server, stop_server

logger = logging.getLogger(__name__)

_LOG_DIR = Path.home() / ".blender-assistant" / "logs"


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
    server_running: bpy.props.BoolProperty(
        name="Server Running",
        default=False,
    )


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
        thread = threading.Thread(
            target=start_server,
            args=(port,),
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
            layout.operator("llm_assistant.stop_server")
        else:
            layout.label(text="Server not running", icon="CANCEL")
            layout.operator("llm_assistant.start_server")


classes = [
    LLMAssistantProperties,
    LLMASSISTANT_OT_start_server,
    LLMASSISTANT_OT_stop_server,
    LLMASSISTANT_PT_panel,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.llm_assistant_props = bpy.props.PointerProperty(type=LLMAssistantProperties)


def unregister():
    stop_server()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.llm_assistant_props
