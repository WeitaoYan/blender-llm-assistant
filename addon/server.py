import json
import logging
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

import bpy

from .tools import tool_registry

logger = logging.getLogger(__name__)

_server_instance = None

# --- SSE Event Store ---
_event_store: dict[str, list[dict]] = {}
_event_conditions: dict[str, threading.Condition] = {}
_store_lock = threading.Lock()
_cleanup_timers: dict[str, threading.Timer] = {}


def _new_task_id() -> str:
    return str(uuid.uuid4())


def _init_task(task_id: str):
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


def _view3d_override():
    """Build a temp_override dict for the first VIEW_3D area found."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                region = None
                for r in area.regions:
                    if r.type == "WINDOW":
                        region = r
                        break
                if region is None and area.regions:
                    region = area.regions[-1]
                return {
                    "window": window,
                    "screen": window.screen,
                    "area": area,
                    "region": region,
                }
    return None


def _run_on_main_thread_sync(func, *args, timeout: float = 60.0, **kwargs):
    """Execute a function on Blender's main thread and return its result."""
    result_container = {}
    done_event = threading.Event()

    def _wrapper():
        try:
            ctx = _view3d_override()
            if ctx:
                with bpy.context.temp_override(**ctx):
                    result_container["result"] = func(*args, **kwargs)
            else:
                result_container["result"] = func(*args, **kwargs)
        except Exception as e:
            result_container["error"] = e
        finally:
            done_event.set()
        return None

    bpy.app.timers.register(_wrapper, first_interval=0.0)
    if not done_event.wait(timeout=timeout):
        return None, TimeoutError(f"Main-thread call timed out after {timeout}s")

    if "error" in result_container:
        return None, result_container["error"]
    return result_container.get("result"), None


def _run_tool(task_id: str, tool_name: str, params: dict):
    logger.info(f"Tool call: {tool_name}({json.dumps(params, default=str)})")
    start = time.time()
    _push_event(task_id, "running", {"tool": tool_name})
    try:
        tool_func = tool_registry.get(tool_name)
        if tool_func is None:
            raise ValueError(f"Tool '{tool_name}' not found")

        result, error = _run_on_main_thread_sync(tool_func, **params)
        if error is not None:
            raise error

        logger.info(f"Tool {tool_name} completed in {time.time() - start:.2f}s")
        _push_event(task_id, "success", {"result": result})
    except Exception as e:
        logger.exception(f"Tool {tool_name} failed after {time.time() - start:.2f}s: {e}")
        _push_event(task_id, "error", {"error": str(e)})
    finally:
        _schedule_cleanup(task_id)


def _json_response(handler, data: dict, status: int = 200):
    body = json.dumps(data, default=str).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _read_json_body(handler) -> dict:
    length = int(handler.headers.get("Content-Length", 0))
    if length > 0:
        return json.loads(handler.rfile.read(length).decode())
    return {}


class _BlenderHTTPRequestHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        logger.debug(f"HTTP {args[0]} {args[1]} {args[2]}")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        try:
            self._route_get()
        except Exception as e:
            logger.exception(f"GET {self.path} failed")
            _json_response(self, {"detail": str(e)}, 500)

    def _route_get(self):
        if self.path == "/health":
            return _json_response(self, {"status": "ok"})

        if self.path == "/api/tools/list":
            tools = [
                {"name": n, "description": i.get("description", ""), "parameters": i.get("parameters", {})}
                for n, i in tool_registry.get_all().items()
            ]
            return _json_response(self, {"tools": tools})

        if self.path.startswith("/api/sse/"):
            task_id = self.path[len("/api/sse/"):]
            return self._handle_sse(task_id)

        if self.path == "/api/scene/info":
            def _get_info():
                info = {
                    "scene_name": bpy.context.scene.name,
                    "objects": [],
                    "frame": bpy.context.scene.frame_current,
                    "render_engine": bpy.context.scene.render.engine,
                }
                for obj in bpy.data.objects:
                    info["objects"].append({
                        "name": obj.name, "type": obj.type,
                        "location": list(obj.location), "rotation": list(obj.rotation_euler),
                        "scale": list(obj.scale), "visible": obj.visible_get(),
                    })
                return info
            result, error = _run_on_main_thread_sync(_get_info)
            if error:
                return _json_response(self, {"detail": str(error)}, 500)
            return _json_response(self, result)

        _json_response(self, {"detail": "Not Found"}, 404)

    def do_POST(self):
        try:
            self._route_post()
        except Exception as e:
            logger.exception(f"POST {self.path} failed")
            _json_response(self, {"detail": str(e)}, 500)

    def _route_post(self):
        if self.path == "/api/tools/call":
            data = _read_json_body(self)
            task_id = _new_task_id()
            _init_task(task_id)
            _push_event(task_id, "queued", {"task_id": task_id, "tool": data.get("tool", "")})
            thread = threading.Thread(
                target=_run_tool,
                args=(task_id, data.get("tool"), data.get("params", {})),
                daemon=True,
            )
            thread.start()
            return _json_response(self, {"task_id": task_id, "status": "queued"}, 202)

        if self.path == "/api/scene/screenshot":
            import base64
            import os
            import tempfile

            def _take():
                scene = bpy.context.scene
                old_format = scene.render.image_settings.file_format
                scene.render.image_settings.file_format = "PNG"
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    scene.render.filepath = tmp_path
                    bpy.ops.render.opengl(write_still=True)
                    with open(tmp_path, "rb") as f:
                        data = base64.b64encode(f.read()).decode()
                    return {"image": data, "format": "png"}
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    scene.render.image_settings.file_format = old_format

            result, error = _run_on_main_thread_sync(_take)
            if error:
                return _json_response(self, {"detail": str(error)}, 500)
            return _json_response(self, result)

        _json_response(self, {"detail": "Not Found"}, 404)

    def _handle_sse(self, task_id: str):
        """Block until tool completes, then write all SSE events at once."""
        if task_id not in _event_store:
            return _json_response(self, {"detail": "Task not found"}, 404)

        index = 0
        lines = []
        try:
            while True:
                events = _get_events_since(task_id, index)
                for ev in events:
                    index += 1
                    lines.append(
                        f"event: {ev['event']}\n"
                        f"data: {json.dumps(ev['data'], default=str)}\n\n"
                    )
                    if ev['event'] in ("success", "error"):
                        _cancel_cleanup(task_id)
                        _cleanup_task(task_id)
                        self._write_sse_response(lines)
                        return

                cond = _event_conditions.get(task_id)
                if cond is None:
                    break
                with cond:
                    cond.wait(timeout=3.0)
        finally:
            _cancel_cleanup(task_id)
            _cleanup_task(task_id)

        if lines:
            self._write_sse_response(lines)
        else:
            _json_response(self, {"detail": "No events"}, 204)

    def _write_sse_response(self, lines: list[str]):
        body = "".join(lines).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_server(port: int = 15800):
    global _server_instance

    logger.info(f"Starting Blender HTTP server on port {port}")

    _server_instance = _ThreadingHTTPServer(("127.0.0.1", port), _BlenderHTTPRequestHandler)

    try:
        _server_instance.serve_forever()
    except Exception as e:
        logger.warning(f"Blender HTTP server stopped: {e}")
    finally:
        _server_instance = None


def stop_server():
    global _server_instance
    logger.info("Stopping Blender HTTP server...")
    if _server_instance:
        _server_instance.shutdown()
        _server_instance = None
