import bpy # type: ignore
import mathutils # type: ignore


OBJECT_TYPES = {
    "cube": "CUBE",
    "sphere": "UV_SPHERE",
    "cylinder": "CYLINDER",
    "cone": "CONE",
    "torus": "TORUS",
    "uv_sphere": "UV_SPHERE",
    "ico_sphere": "ICO_SPHERE",
}


def _ensure_object_mode():
    """Switch to object mode if not already."""
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def _deselect_all():
    """Deselect all objects without requiring a VIEW_3D context."""
    for obj in bpy.data.objects:
        obj.select_set(False)
    bpy.context.view_layer.objects.active = None


def register_tools(registry):

    @registry.register(
        name="create_object",
        description="Create a new mesh object in the scene",
        parameters={
            "type": {
                "type": "string",
                "description": "Object type: cube, sphere, cylinder, cone, torus, uv_sphere, ico_sphere",
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
            "scale": {
                "type": "array",
                "description": "Scale [sx, sy, sz]",
                "items": {"type": "number"},
                "required": False,
            },
            "name": {
                "type": "string",
                "description": "Custom name for the object",
                "required": False,
            },
        },
    )
    def create_object(type: str = "cube", location=None, rotation=None, scale=None, name=None):
        bpy_type = OBJECT_TYPES.get(type.lower())
        if bpy_type is None:
            raise ValueError(f"Unknown object type: {type}")

        if location is None:
            location = [0, 0, 0]
        if rotation is None:
            rotation = [0, 0, 0]
        if scale is None:
            scale = [1, 1, 1]

        _deselect_all()

        if type == "cube":
            bpy.ops.mesh.primitive_cube_add(location=location, rotation=rotation)
        elif type in ("sphere", "uv_sphere"):
            bpy.ops.mesh.primitive_uv_sphere_add(location=location, rotation=rotation)
        elif type == "cylinder":
            bpy.ops.mesh.primitive_cylinder_add(location=location, rotation=rotation)
        elif type == "cone":
            bpy.ops.mesh.primitive_cone_add(location=location, rotation=rotation)
        elif type == "torus":
            bpy.ops.mesh.primitive_torus_add(location=location, rotation=rotation)
        elif type == "ico_sphere":
            bpy.ops.mesh.primitive_ico_sphere_add(location=location, rotation=rotation)

        obj = bpy.context.active_object
        obj.scale = tuple(scale)
        if name:
            obj.name = name

        return {
            "name": obj.name,
            "type": type,
            "location": list(obj.location),
            "rotation": list(obj.rotation_euler),
            "scale": list(obj.scale),
        }

    @registry.register(
        name="select_object",
        description="Select an object by name",
        parameters={
            "name": {
                "type": "string",
                "description": "Name of the object to select",
                "required": True,
            },
        },
    )
    def select_object(name: str):
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise ValueError(f"Object '{name}' not found")
        _deselect_all()
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        return {"selected": name}

    @registry.register(
        name="delete_object",
        description="Delete an object by name",
        parameters={
            "name": {
                "type": "string",
                "description": "Name of the object to delete",
                "required": True,
            },
        },
    )
    def delete_object(name: str):
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise ValueError(f"Object '{name}' not found")
        _deselect_all()
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.delete()
        return {"deleted": name}

    @registry.register(
        name="transform_object",
        description="Transform (move/rotate/scale) an object",
        parameters={
            "name": {
                "type": "string",
                "description": "Name of the object",
                "required": True,
            },
            "location": {
                "type": "array",
                "description": "New location [x, y, z]",
                "items": {"type": "number"},
                "required": False,
            },
            "rotation": {
                "type": "array",
                "description": "New rotation [rx, ry, rz] in radians",
                "items": {"type": "number"},
                "required": False,
            },
            "scale": {
                "type": "array",
                "description": "New scale [sx, sy, sz]",
                "items": {"type": "number"},
                "required": False,
            },
        },
    )
    def transform_object(name: str, location=None, rotation=None, scale=None):
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise ValueError(f"Object '{name}' not found")

        if location is not None:
            obj.location = location
        if rotation is not None:
            obj.rotation_euler = rotation
        if scale is not None:
            obj.scale = scale

        return {
            "name": obj.name,
            "location": list(obj.location),
            "rotation": list(obj.rotation_euler),
            "scale": list(obj.scale),
        }

    @registry.register(
        name="duplicate_object",
        description="Duplicate an object",
        parameters={
            "name": {
                "type": "string",
                "description": "Name of the object to duplicate",
                "required": True,
            },
            "offset": {
                "type": "array",
                "description": "Offset [x, y, z] for the duplicate",
                "items": {"type": "number"},
                "required": False,
            },
        },
    )
    def duplicate_object(name: str, offset=None):
        if offset is None:
            offset = [2, 0, 0]
        obj = bpy.data.objects.get(name)
        if obj is None:
            raise ValueError(f"Object '{name}' not found")

        _ensure_object_mode()
        _deselect_all()
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.duplicate()

        new_obj = bpy.context.active_object
        new_obj.location = mathutils.Vector(obj.location) + mathutils.Vector(offset)

        return {
            "original": name,
            "duplicate": new_obj.name,
            "location": list(new_obj.location),
        }

    @registry.register(
        name="add_modifier",
        description="Add a modifier to an object",
        parameters={
            "object": {
                "type": "string",
                "description": "Name of the object",
                "required": True,
            },
            "type": {
                "type": "string",
                "description": "Modifier type: subsurf, mirror, bevel, array, solidify, boolean",
                "required": True,
            },
            "params": {
                "type": "object",
                "description": "Modifier-specific parameters",
                "required": False,
            },
        },
    )
    def add_modifier(object: str, type: str, params: dict | None = None):
        obj = bpy.data.objects.get(object)
        if obj is None:
            raise ValueError(f"Object '{object}' not found")
        if params is None:
            params = {}

        mod = obj.modifiers.new(name=f"{type}_{obj.name}", type=type.upper())

        if type == "subsurf":
            mod.levels = params.get("levels", 1)
            mod.render_levels = params.get("render_levels", 2)
        elif type == "mirror":
            mod.use_axis[0] = params.get("use_x", True)
            mod.use_axis[1] = params.get("use_y", False)
            mod.use_axis[2] = params.get("use_z", False)
        elif type == "bevel":
            mod.width = params.get("width", 0.05)
            mod.segments = params.get("segments", 1)
        elif type == "array":
            mod.count = params.get("count", 2)
            mod.relative_offset_displace = params.get("offset", (1, 0, 0))
        elif type == "solidify":
            mod.thickness = params.get("thickness", 0.05)

        return {
            "object": object,
            "modifier": mod.name,
            "type": type,
        }

    @registry.register(
        name="boolean_operation",
        description="Perform a boolean operation between two objects",
        parameters={
            "object_a": {
                "type": "string",
                "description": "First object name (base)",
                "required": True,
            },
            "object_b": {
                "type": "string",
                "description": "Second object name (operand)",
                "required": True,
            },
            "operation": {
                "type": "string",
                "description": "Operation: union, difference, intersect",
                "required": True,
            },
        },
    )
    def boolean_operation(object_a: str, object_b: str, operation: str):
        obj_a = bpy.data.objects.get(object_a)
        obj_b = bpy.data.objects.get(object_b)
        if obj_a is None:
            raise ValueError(f"Object '{object_a}' not found")
        if obj_b is None:
            raise ValueError(f"Object '{object_b}' not found")

        _deselect_all()
        obj_a.select_set(True)
        bpy.context.view_layer.objects.active = obj_a

        bool_map = {
            "union": "UNION",
            "difference": "DIFFERENCE",
            "intersect": "INTERSECT",
        }
        bool_type = bool_map.get(operation.lower())
        if bool_type is None:
            raise ValueError(f"Unknown boolean operation: {operation}")

        mod = obj_a.modifiers.new(name=f"boolean_{object_b}", type="BOOLEAN")
        mod.object = obj_b
        mod.operation = bool_type

        bpy.ops.object.modifier_apply(modifier=mod.name)

        bpy.data.objects.remove(obj_b, do_unlink=True)

        return {
            "result": object_a,
            "operation": operation,
            "operand_deleted": object_b,
        }
