"""High-precision curve creation and conversion tools."""

import bpy
import bmesh
import mathutils


def _deselect_all():
    for obj in bpy.data.objects:
        obj.select_set(False)


def register_tools(registry):

    @registry.register(
        name="create_curve",
        description="Create a Bezier or NURBS curve object with control points",
        parameters={
            "type": {
                "type": "string",
                "description": "Curve type: BEZIER or NURBS (default BEZIER)",
                "required": False,
            },
            "points": {
                "type": "array",
                "description": "Control points [[x, y, z], ...] (requires at least 2)",
                "items": {"type": "array", "items": {"type": "number"}},
                "required": True,
            },
            "location": {
                "type": "array",
                "description": "Location [x, y, z]",
                "items": {"type": "number"},
                "required": False,
            },
            "rotation": {
                "type": "array",
                "description": "Rotation [rx, ry, rz] in radians",
                "items": {"type": "number"},
                "required": False,
            },
            "name": {
                "type": "string",
                "description": "Custom name for the curve object",
                "required": False,
            },
            "bevel_depth": {
                "type": "number",
                "description": "Bevel depth for tube-like curves (default 0)",
                "required": False,
            },
            "bevel_resolution": {
                "type": "integer",
                "description": "Bevel resolution (default 0)",
                "required": False,
            },
            "fill_mode": {
                "type": "string",
                "description": "Fill mode: FULL, FRONT, BACK, HALF (default FULL)",
                "required": False,
            },
            "order": {
                "type": "integer",
                "description": "NURBS curve order (default 4). Only used for NURBS type.",
                "required": False,
            },
        },
    )
    def create_curve(
        type: str = "BEZIER",
        points: list | None = None,
        location=None,
        rotation=None,
        name=None,
        bevel_depth: float = 0.0,
        bevel_resolution: int = 0,
        fill_mode: str = "FULL",
        order: int = 4,
    ):
        if points is None or len(points) < 2:
            raise ValueError("At least 2 control points are required")
        if location is None:
            location = [0, 0, 0]
        if rotation is None:
            rotation = [0, 0, 0]

        type_upper = type.upper()
        if type_upper not in ("BEZIER", "NURBS"):
            raise ValueError("type must be BEZIER or NURBS")

        fill_upper = fill_mode.upper()
        valid_fill = {"FULL", "FRONT", "BACK", "HALF"}
        if fill_upper not in valid_fill:
            raise ValueError(f"fill_mode must be one of {valid_fill}")

        curve_data = bpy.data.curves.new(name=name or f"{type_upper}_Curve", type="CURVE")
        curve_data.dimensions = "3D"
        curve_data.bevel_depth = bevel_depth
        curve_data.bevel_resolution = bevel_resolution
        curve_data.fill_mode = fill_upper

        if type_upper == "BEZIER":
            spline = curve_data.splines.new("BEZIER")
            spline.bezier_points.add(len(points) - 1)
            for i, p in enumerate(points):
                spline.bezier_points[i].co = p
                spline.bezier_points[i].handle_left_type = "AUTO"
                spline.bezier_points[i].handle_right_type = "AUTO"
        else:
            spline = curve_data.splines.new("NURBS")
            spline.points.add(len(points) - 1)
            for i, p in enumerate(points):
                spline.points[i].co = (p[0], p[1], p[2], 1.0)
            spline.order_u = min(order, len(points))
            spline.use_endpoint_u = True

        obj = bpy.data.objects.new(name=curve_data.name, object_data=curve_data)
        obj.location = location
        obj.rotation_euler = rotation
        bpy.context.collection.objects.link(obj)

        return {
            "name": obj.name,
            "type": type_upper,
            "points": len(points),
            "location": list(obj.location),
        }

    @registry.register(
        name="convert_curve_mesh",
        description="Convert between mesh and curve objects",
        parameters={
            "target": {
                "type": "string",
                "description": "Name of the object to convert",
                "required": True,
            },
            "direction": {
                "type": "string",
                "description": "TO_MESH: convert curve to mesh. TO_CURVE: convert mesh to curve.",
                "required": True,
            },
        },
    )
    def convert_curve_mesh(target: str, direction: str):
        obj = bpy.data.objects.get(target)
        if obj is None:
            raise ValueError(f"Object '{target}' not found")

        dir_upper = direction.upper()
        if dir_upper not in ("TO_MESH", "TO_CURVE"):
            raise ValueError("direction must be TO_MESH or TO_CURVE")

        _deselect_all()
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

        if dir_upper == "TO_MESH":
            if obj.type != "CURVE":
                raise ValueError(f"Object '{target}' is not a curve (type={obj.type})")
            bpy.ops.object.convert(target="MESH")
        else:
            if obj.type != "MESH":
                raise ValueError(f"Object '{target}' is not a mesh (type={obj.type})")
            bpy.ops.object.mode_set(mode="EDIT")
            obj = bpy.context.active_object
            bm = bmesh.from_edit_mesh(obj.data)
            for f in bm.faces: f.select = True
            bm.select_flush_mode()
            bmesh.update_edit_mesh(obj.data, destructive=False)
            bpy.ops.mesh.delete(type="ONLY_FACE")
            bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.object.convert(target="CURVE")

        # Force depsgraph update to reflect type change
        bpy.context.view_layer.update()
        new_obj = bpy.context.active_object
        return {
            "original": target,
            "result": new_obj.name,
            "result_type": new_obj.type,
        }
