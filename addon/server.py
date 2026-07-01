import asyncio
import json
import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager

import bpy # type: ignore
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .tools import tool_registry

logger = logging.getLogger(__name__)

_server = None
_loop = None
_thread = None
_app = None

# --- SSE Event Store ---
_event_store: dict[str, list[dict]] = {}
_event_conditions: dict[str, threading.Condition] = {}
_store_lock = threading.Lock()
_cleanup_timers: dict[str, threading.Timer] = {}


def _new_task_id() -> str:
    return str(uuid.uuid4())


def _init_task(task_id: str):
    logger.debug(f"Init SSE task: {task_id}")
    with _store_lock:
        _event_store[task_id] = []
        _event_conditions[task_id] = threading.Condition()


def _push_event(task_id: str, event_type: str, data: dict | None = None):
    with _store_lock:
        events = _event_store.get(task_id)
        if events is None:
            return
        events.append({"event": event_type, "data": data or {}})
        cond = _event_conditions.get(task_id)
        if cond:
            with cond:
                cond.notify_all()


def _get_events_since(task_id: str, index: int) -> list[dict]:
    with _store_lock:
        return _event_store.get(task_id, [])[index:]


def _cleanup_task(task_id: str):
    with _store_lock:
        _event_store.pop(task_id, None)
        _event_conditions.pop(task_id, None)
        _cleanup_timers.pop(task_id, None)


def _schedule_cleanup(task_id: str, delay: float = 30.0):
    def _do_cleanup():
        _cleanup_task(task_id)
    timer = threading.Timer(delay, _do_cleanup)
    with _store_lock:
        _cleanup_timers[task_id] = timer
    timer.start()


def _cancel_cleanup(task_id: str):
    with _store_lock:
        timer = _cleanup_timers.pop(task_id, None)
        if timer:
            timer.cancel()


def _run_on_main_thread_sync(func, *args, timeout: float = 60.0, **kwargs):
    """Execute a function on Blender's main thread and return its result.

    Uses bpy.app.timers.register to schedule the call and a threading.Event
    to wait for completion. Returns (result, None) on success or (None, error)
    on failure/timeout.
    """
    result_container = {}
    done_event = threading.Event()

    def _wrapper():
        try:
            result_container["result"] = func(*args, **kwargs)
        except Exception as e:
            result_container["error"] = e
        finally:
            done_event.set()
        return None  # one-shot timer: return None to unregister

    bpy.app.timers.register(_wrapper, first_interval=0.0)
    if not done_event.wait(timeout=timeout):
        return None, TimeoutError(f"Main-thread call timed out after {timeout}s")

    if "error" in result_container:
        return None, result_container["error"]
    return result_container.get("result"), None


def _run_tool(task_id: str, tool_name: str, params: dict):
    logger.info(f"Tool call (dispatching to main thread): {tool_name}({json.dumps(params, default=str)})")
    start = time.time()
    _push_event(task_id, "running", {"tool": tool_name})
    try:
        tool_func = tool_registry.get(tool_name)
        if tool_func is None:
            raise ValueError(f"Tool '{tool_name}' not found")

        # Execute the tool on Blender's main thread
        result, error = _run_on_main_thread_sync(tool_func, **params)
        if error is not None:
            raise error

        elapsed = time.time() - start
        logger.info(f"Tool {tool_name} completed in {elapsed:.2f}s")
        _push_event(task_id, "success", {"result": result})
    except Exception as e:
        elapsed = time.time() - start
        logger.exception(f"Tool {tool_name} failed after {elapsed:.2f}s: {e}")
        _push_event(task_id, "error", {"error": str(e)})
    finally:
        _schedule_cleanup(task_id)


def _wait_on_cond(cond: threading.Condition, timeout: float):
    with cond:
        cond.wait(timeout=timeout)


async def _event_generator(task_id: str, request: Request):
    index = 0
    try:
        while True:
            if await request.is_disconnected():
                break
            events = _get_events_since(task_id, index)
            for ev in events:
                index += 1
                yield f"event: {ev['event']}\ndata: {json.dumps(ev['data'])}\n\n"
                if ev['event'] in ("success", "error"):
                    return
            cond = _event_conditions.get(task_id)
            if cond is None:
                break
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _wait_on_cond, cond, 3.0)
    finally:
        _cancel_cleanup(task_id)
        _cleanup_task(task_id)


class ToolCallRequest(BaseModel):
    tool: str
    params: dict = {}


class ToolCallResponse(BaseModel):
    success: bool
    result: dict | None = None
    error: str | None = None


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Blender HTTP Server started")
        yield
        logger.info("Blender HTTP Server stopped")

    app = FastAPI(title="Blender LLM Assistant", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/tools/list")
    def list_tools():
        tools = list(tool_registry.get_all().keys())
        logger.debug(f"Listing {len(tools)} tools")
        return {
            "tools": [
                {
                    "name": name,
                    "description": info.get("description", ""),
                    "parameters": info.get("parameters", {}),
                }
                for name, info in tool_registry.get_all().items()
            ]
        }

    @app.post("/api/tools/call", status_code=202)
    async def call_tool(req: ToolCallRequest):
        task_id = _new_task_id()
        _init_task(task_id)
        logger.info(f"Queue tool call: {req.tool} (task={task_id})")
        _push_event(task_id, "queued", {"task_id": task_id, "tool": req.tool})
        thread = threading.Thread(
            target=_run_tool,
            args=(task_id, req.tool, req.params),
            daemon=True,
        )
        thread.start()
        return {"task_id": task_id, "status": "queued"}

    @app.get("/api/sse/{task_id}")
    async def sse_events(task_id: str, request: Request):
        if task_id not in _event_store:
            raise HTTPException(status_code=404, detail="Task not found")
        return StreamingResponse(
            _event_generator(task_id, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/scene/info")
    def scene_info():
        def _get_scene_info():
            info = {
                "objects": [],
                "frame": bpy.context.scene.frame_current,
                "render_engine": bpy.context.scene.render.engine,
            }
            for obj in bpy.data.objects:
                info["objects"].append({
                    "name": obj.name,
                    "type": obj.type,
                    "location": list(obj.location),
                    "rotation": list(obj.rotation_euler),
                    "scale": list(obj.scale),
                    "visible": obj.visible_get(),
                })
            return info

        result, error = _run_on_main_thread_sync(_get_scene_info)
        if error:
            raise HTTPException(status_code=500, detail=str(error))
        return result

    @app.post("/api/scene/screenshot")
    def take_screenshot():
        import base64
        import tempfile
        import os

        def _take_screenshot():
            scene = bpy.context.scene
            old_format = scene.render.image_settings.file_format
            scene.render.image_settings.file_format = "PNG"

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name

            try:
                bpy.ops.render.opengl(write_still=True, view_context=True)
                import bpy.path
                actual_path = bpy.context.render.frame_path()
                if os.path.exists(actual_path):
                    import shutil
                    shutil.copy(actual_path, tmp_path)
                else:
                    scene.render.filepath = tmp_path
                    bpy.ops.render.opengl(write_still=True, view_context=True)

                with open(tmp_path, "rb") as f:
                    data = base64.b64encode(f.read()).decode()
                return {"image": data, "format": "png"}
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                scene.render.image_settings.file_format = old_format

        result, error = _run_on_main_thread_sync(_take_screenshot)
        if error:
            raise HTTPException(status_code=500, detail=str(error))
        return result

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


def start_server(port: int = 15800):
    global _app, _server, _loop, _thread

    logger.info(f"Starting Blender HTTP server on port {port}")
    _app = create_app()

    config = uvicorn.Config(
        app=_app,
        host="127.0.0.1",
        port=port,
        log_level="info",
        loop="asyncio",
    )
    _server = uvicorn.Server(config)

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    try:
        _loop.run_until_complete(_server.serve())
    except Exception as e:
        logger.exception(f"Blender HTTP server crashed: {e}")
    finally:
        logger.info("Blender HTTP server stopped")


def stop_server():
    global _server, _loop
    logger.info("Stopping Blender HTTP server...")
    if _server:
        _server.should_exit = True
        _server = None
    if _loop:
        _loop.call_soon_threadsafe(_loop.stop)
        _loop = None
