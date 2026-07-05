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
            "Execute Python code in Blender's restricted namespace. "
            "WARNING: The sandbox limits direct dangerous calls but is not a security boundary. "
            "Only expose this API to trusted clients. "
            "Available: bpy, bmesh, mathutils, math. "
            "Builtins filtered (open/eval/exec/compile blocked). "
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

    # ================================================================
    #  Viewport Control
    # ================================================================

    @registry.register(
        name="set_viewport",
        description="Configure viewport display settings (shading, x-ray, wireframe overlay)",
        parameters={
            "shading": {
                "type": "string",
                "description": "Viewport shading: WIREFRAME, SOLID, MATERIAL, RENDERED",
                "required": False,
            },
            "show_xray": {
                "type": "boolean",
                "description": "Enable x-ray (transparent) view",
                "required": False,
            },
            "show_wireframe": {
                "type": "boolean",
                "description": "Show wireframe overlay on shaded view",
                "required": False,
            },
            "view_axis": {
                "type": "string",
                "description": "Align view to axis: FRONT, BACK, LEFT, RIGHT, TOP, BOTTOM, or USER (default: no change)",
                "required": False,
            },
        },
    )
    def set_viewport(
        shading: str = "",
        show_xray: bool | None = None,
        show_wireframe: bool | None = None,
        view_axis: str = "",
    ):
        updated = {"shading": None, "xray": None, "wireframe": None, "view_axis": None}

        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    space = area.spaces.active

                    if shading:
                        shading_upper = shading.upper()
                        if shading_upper not in ("WIREFRAME", "SOLID", "MATERIAL", "RENDERED"):
                            raise ValueError(f"Unknown shading: {shading}")
                        space.shading.type = shading_upper
                        updated["shading"] = shading_upper

                    if show_xray is not None:
                        space.shading.show_xray = show_xray
                        updated["xray"] = show_xray

                    if show_wireframe is not None:
                        space.overlay.show_wireframes = show_wireframe
                        updated["wireframe"] = show_wireframe

                    if view_axis:
                        axis_upper = view_axis.upper()
                        if axis_upper == "USER":
                            pass
                        else:
                            ctx_override = {
                                "window": window,
                                "area": area,
                                "region": area.regions[0] if area.regions else None,
                            }
                            with bpy.context.temp_override(**ctx_override):
                                bpy.ops.view3d.view_axis(type=axis_upper)
                            updated["view_axis"] = axis_upper

                    break

        return {"viewport": updated}

    # ================================================================
    #  Render
    # ================================================================

    @registry.register(
        name="render_scene",
        description="Render the current scene to an image file",
        parameters={
            "output_path": {
                "type": "string",
                "description": "Output file path (e.g. //render.png or C:/output/render.png)",
                "required": False,
            },
            "resolution_x": {
                "type": "integer",
                "description": "Render width in pixels (default 1920)",
                "required": False,
            },
            "resolution_y": {
                "type": "integer",
                "description": "Render height in pixels (default 1080)",
                "required": False,
            },
            "samples": {
                "type": "integer",
                "description": "Render samples (Cycles) or TAA samples (EEVEE). Default 128.",
                "required": False,
            },
        },
    )
    def render_scene(
        output_path: str = "",
        resolution_x: int = 1920,
        resolution_y: int = 1080,
        samples: int = 128,
    ):
        scene = bpy.context.scene

        if scene.camera is None:
            cam_data = bpy.data.cameras.new(name="RenderCamera")
            cam_obj = bpy.data.objects.new(name="RenderCamera", object_data=cam_data)
            cam_obj.location = (0, -10, 5)
            cam_obj.rotation_euler = (1.1, 0, 0)
            bpy.context.collection.objects.link(cam_obj)
            scene.camera = cam_obj

        if output_path:
            scene.render.filepath = output_path

        scene.render.resolution_x = max(1, resolution_x)
        scene.render.resolution_y = max(1, resolution_y)

        engine = scene.render.engine
        if "CYCLES" in engine:
            scene.cycles.samples = max(1, samples)
        elif "EEVEE" in engine:
            try:
                scene.eevee.taa_render_samples = max(1, samples)
            except Exception:
                pass

        original_format = scene.render.image_settings.file_format
        if not output_path.lower().endswith((".png", ".jpg", ".jpeg", ".exr", ".tga", ".bmp", ".tiff", ".webp")):
            scene.render.image_settings.file_format = "PNG"

        try:
            bpy.ops.render.render(write_still=True)
        except Exception as e:
            scene.render.image_settings.file_format = original_format
            raise RuntimeError(f"Render failed: {e}")

        scene.render.image_settings.file_format = original_format

        return {
            "output_path": scene.render.filepath,
            "resolution": [scene.render.resolution_x, scene.render.resolution_y],
            "samples": samples,
            "engine": engine,
        }

    # ================================================================
    #  Import / Export
    # ================================================================

    @registry.register(
        name="import_file",
        description="Import a 3D file into the scene",
        parameters={
            "filepath": {
                "type": "string",
                "description": "Full path to the file to import",
                "required": True,
            },
            "format": {
                "type": "string",
                "description": "File format: OBJ, FBX, STL, GLTF, GLB, PLY, X3D, ABC, USD, SVG (auto-detected from extension if not provided)",
                "required": False,
            },
        },
    )
    def import_file(filepath: str, format: str = ""):
        import pathlib

        ext = format.upper() if format else pathlib.Path(filepath).suffix[1:].upper()

        if ext == "GLTF":
            ext = "GLTF"

        func_map = {
            "OBJ": lambda filepath: bpy.ops.wm.obj_import(filepath=filepath),
            "FBX": bpy.ops.import_scene.fbx,
            "STL": bpy.ops.import_mesh.stl,
            "GLTF": bpy.ops.import_scene.gltf,
            "GLB": bpy.ops.import_scene.gltf,
            "PLY": bpy.ops.import_mesh.ply,
            "X3D": bpy.ops.import_scene.x3d,
            "ABC": bpy.ops.import_alembic,
            "USD": bpy.ops.import_scene.usd,
            "SVG": bpy.ops.import_curve.svg,
            "DAE": bpy.ops.wm.collada_import,
        }

        fn = func_map.get(ext)
        if fn is None:
            raise ValueError(f"Unsupported or unrecognized format: '{format or ext}'. Supported: {', '.join(func_map.keys())}")

        fn(filepath=filepath)

        return {"imported": filepath, "format": ext}

    @registry.register(
        name="export_file",
        description="Export scene or selected objects to a file",
        parameters={
            "filepath": {
                "type": "string",
                "description": "Full output file path",
                "required": True,
            },
            "format": {
                "type": "string",
                "description": "File format: OBJ, FBX, STL, GLTF, GLB, PLY, X3D, ABC, USD (auto-detected from extension if not provided)",
                "required": False,
            },
            "use_selection": {
                "type": "boolean",
                "description": "Export only selected objects (default false = export entire scene)",
                "required": False,
            },
        },
    )
    def export_file(filepath: str, format: str = "", use_selection: bool = False):
        import pathlib

        ext = format.upper() if format else pathlib.Path(filepath).suffix[1:].upper()

        if ext == "GLTF":
            ext = "GLTF"

        func_map = {
            "OBJ": lambda filepath, use_selection: bpy.ops.wm.obj_export(
                filepath=filepath, export_selected_objects=use_selection),
            "FBX": bpy.ops.export_scene.fbx,
            "STL": bpy.ops.export_mesh.stl,
            "GLTF": bpy.ops.export_scene.gltf,
            "GLB": bpy.ops.export_scene.gltf,
            "PLY": bpy.ops.export_mesh.ply,
            "X3D": bpy.ops.export_scene.x3d,
            "ABC": bpy.ops.export_alembic,
            "USD": bpy.ops.export_scene.usd,
            "DAE": bpy.ops.wm.collada_export,
        }

        fn = func_map.get(ext)
        if fn is None:
            raise ValueError(f"Unsupported or unrecognized format: '{format or ext}'. Supported: {', '.join(func_map.keys())}")

        fn(filepath=filepath, use_selection=use_selection)

        return {"exported": filepath, "format": ext, "use_selection": use_selection}
