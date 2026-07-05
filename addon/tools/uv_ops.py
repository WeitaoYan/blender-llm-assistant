"""UV mapping and packing tools for high-precision texturing."""

import bpy
import bmesh


def _deselect_all():
    for o in bpy.data.objects:
        o.select_set(False)


def _view3d_ctx():
    try:
        area = bpy.context.area
        if area and area.type == "VIEW_3D":
            return {
                "window": bpy.context.window,
                "screen": bpy.context.screen,
                "area": area,
                "region": bpy.context.region,
            }
    except Exception:
        pass
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
                return {"window": window, "screen": window.screen, "area": area, "region": region}
    return None


def _run_uv_op(op_func, **kwargs):
    return op_func(**kwargs)


def register_tools(registry):

    @registry.register(
        name="uv_unwrap",
        description="Unwrap the UVs of a mesh object using various projection methods",
        parameters={
            "target": {
                "type": "string",
                "description": "Name of the mesh object. Uses active object if not provided.",
                "required": False,
            },
            "method": {
                "type": "string",
                "description": "Unwrap method: SMART, ANGLE_BASED, CONFORMAL, CUBE, CYLINDER, SPHERE, PROJECT_FROM_VIEW (default SMART)",
                "required": False,
            },
            "margin": {
                "type": "number",
                "description": "Margin between UV islands (default 0.03)",
                "required": False,
            },
            "cube_size": {
                "type": "number",
                "description": "Cube projection size (default 1.0). Used with CUBE method.",
                "required": False,
            },
        },
    )
    def uv_unwrap(
        target: str | None = None,
        method: str = "SMART",
        margin: float = 0.03,
        cube_size: float = 1.0,
    ):
        if target:
            obj = bpy.data.objects.get(target)
            if obj is None:
                raise ValueError(f"Object '{target}' not found")
            if obj.type != "MESH":
                raise ValueError(f"Object '{target}' is not a mesh")
            _deselect_all()
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
        else:
            obj = bpy.context.active_object
            if obj is None or obj.type != "MESH":
                raise ValueError("No active mesh object. Specify target or select a mesh.")

        was_edit = obj.mode == "EDIT"
        if was_edit:
            bpy.ops.object.mode_set(mode="OBJECT")

        if not obj.data.uv_layers:
            obj.data.uv_layers.new(name="UVMap")

        bpy.ops.object.mode_set(mode="EDIT")
        obj = bpy.context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        for v in bm.verts: v.select = True
        for e in bm.edges: e.select = True
        for f in bm.faces: f.select = True
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data, destructive=False)

        method_upper = method.upper()

        def _exec_uv_op():
            if method_upper == "SMART":
                _run_uv_op(bpy.ops.uv.smart_project, angle_limit=66, island_margin=margin, area_weight=0)
            elif method_upper == "ANGLE_BASED":
                _run_uv_op(bpy.ops.uv.unwrap, method="ANGLE_BASED", margin=margin)
            elif method_upper == "CONFORMAL":
                _run_uv_op(bpy.ops.uv.unwrap, method="CONFORMAL", margin=margin)
            elif method_upper == "CUBE":
                _run_uv_op(bpy.ops.uv.cube_project, cube_size=cube_size)
            elif method_upper == "CYLINDER":
                _run_uv_op(bpy.ops.uv.cylinder_project, margin=margin)
            elif method_upper == "SPHERE":
                _run_uv_op(bpy.ops.uv.sphere_project, margin=margin)
            elif method_upper == "PROJECT_FROM_VIEW":
                _run_uv_op(bpy.ops.uv.project_from_view, camera_bounds=True, correct_aspect=True)
            else:
                raise ValueError(f"Unknown method: {method}")

        try:
            _exec_uv_op()
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")

        return {
            "object": obj.name,
            "method": method.upper(),
            "margin": margin if method.upper() != "PROJECT_FROM_VIEW" else None,
        }

    @registry.register(
        name="uv_pack",
        description="Pack UV islands to optimize texture space usage",
        parameters={
            "target": {
                "type": "string",
                "description": "Name of the mesh object. Uses active object if not provided.",
                "required": False,
            },
            "margin": {
                "type": "number",
                "description": "Margin between UV islands (default 0.03)",
                "required": False,
            },
            "rotate": {
                "type": "boolean",
                "description": "Allow rotation of UV islands to improve packing (default true)",
                "required": False,
            },
        },
    )
    def uv_pack(target: str | None = None, margin: float = 0.03, rotate: bool = True):
        if target:
            obj = bpy.data.objects.get(target)
            if obj is None:
                raise ValueError(f"Object '{target}' not found")
            if obj.type != "MESH":
                raise ValueError(f"Object '{target}' is not a mesh")
            _deselect_all()
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
        else:
            obj = bpy.context.active_object
            if obj is None or obj.type != "MESH":
                raise ValueError("No active mesh object. Specify target or select a mesh.")

        if not obj.data.uv_layers:
            raise ValueError(f"Object '{obj.name}' has no UV layers. Use uv_unwrap first.")

        was_edit = obj.mode == "EDIT"

        if not was_edit:
            bpy.ops.object.mode_set(mode="EDIT")
        obj = bpy.context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        for v in bm.verts: v.select = True
        for e in bm.edges: e.select = True
        for f in bm.faces: f.select = True
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data, destructive=False)

        try:
            _run_uv_op(bpy.ops.uv.pack_islands, margin=margin, rotate=rotate)
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")

        return {
            "object": obj.name,
            "margin": margin,
            "rotate": rotate,
        }
