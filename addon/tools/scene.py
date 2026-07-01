import builtins
import math

import bmesh  # type: ignore
import bpy  # type: ignore
import mathutils  # type: ignore

# --- Whitelist of safe modules for execute_python ---
_SAFE_MODULES = {
    "bpy": bpy,
    "bmesh": bmesh,
    "mathutils": mathutils,
    "math": math,
}

# Block dangerous builtins in the sandbox
_FORBIDDEN_BUILTINS = {
    "compile",
    "eval",
    "exec",
    "open",
    "input",
    "breakpoint",
}


def _safe_import(name, *args, **kwargs):
    """Whitelist-based import: only allows modules in _SAFE_MODULES."""
    if name in _SAFE_MODULES:
        import builtins as _b
        return _b.__import__(name, *args, **kwargs)
    raise ImportError(f"Import of '{name}' is not allowed in sandbox")


def _safe_builtins() -> dict:
    """Return a copy of builtins with dangerous functions removed."""
    safe = {}
    for name in dir(builtins):
        if name.startswith("_") or name in _FORBIDDEN_BUILTINS:
            continue
        obj = getattr(builtins, name)
        safe[name] = obj
    safe["__import__"] = _safe_import
    return safe


def _make_sandbox_globals() -> dict:
    """Build a restricted globals dict for exec()."""
    g = {**{k: v for k, v in _SAFE_MODULES.items()}}
    g["__builtins__"] = _safe_builtins()
    # Convenience aliases (read-only snapshot to avoid stale context issues)
    g["C"] = bpy.context
    g["D"] = bpy.data
    return g


def register_tools(registry):

    @registry.register(
        name="get_scene_info",
        description="Get information about the current scene, including all objects and their properties",
        parameters={},
    )
    def get_scene_info():
        objects = []
        for obj in bpy.data.objects:
            obj_info = {
                "name": obj.name,
                "type": obj.type,
                "location": list(obj.location),
                "rotation": list(obj.rotation_euler),
                "scale": list(obj.scale),
                "visible": obj.visible_get(),
                "selectable": obj.hide_select is False,
            }

            if obj.type == "MESH":
                verts = len(obj.data.vertices)
                faces = len(obj.data.polygons)
                obj_info["vertices"] = verts
                obj_info["faces"] = faces

                materials = []
                for mat in obj.data.materials:
                    if mat:
                        materials.append(mat.name)
                obj_info["materials"] = materials

                modifiers = []
                for mod in obj.modifiers:
                    modifiers.append({
                        "name": mod.name,
                        "type": mod.type,
                    })
                obj_info["modifiers"] = modifiers

            objects.append(obj_info)

        return {
            "scene_name": bpy.context.scene.name,
            "frame_current": bpy.context.scene.frame_current,
            "frame_start": bpy.context.scene.frame_start,
            "frame_end": bpy.context.scene.frame_end,
            "render_engine": bpy.context.scene.render.engine,
            "objects": objects,
        }

    @registry.register(
        name="execute_python",
        description=(
            "Execute Python code in Blender's sandboxed namespace. "
            "Only bpy, bmesh, mathutils, and math are available. "
            "Dangerous builtins (__import__, open, eval, exec, compile) are blocked. "
            "Use 'result = ...' to return a value."
        ),
        parameters={
            "code": {
                "type": "string",
                "description": "Python code to execute in Blender's sandboxed namespace",
                "required": True,
            },
        },
    )
    def execute_python(code: str):
        local_scope: dict = {}
        sandbox_globals = _make_sandbox_globals()
        exec(code, sandbox_globals, local_scope)
        return {"executed": True, "result": local_scope.get("result", None)}
