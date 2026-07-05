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
                "target": {
                    "type": "string",
                    "description": "Name of the object",
                    "required": True,
                },
            "type": {
                "type": "string",
                "description": "Modifier type: subsurf, mirror, bevel, array, solidify, screw, simple_deform, shrinkwrap, decimate, remesh, weld",
                "required": True,
            },
            "params": {
                "type": "object",
                "description": "Modifier-specific parameters",
                "required": False,
            },
        },
    )
    def add_modifier(target: str, type: str, params: dict | None = None):
        obj = bpy.data.objects.get(target)
        if obj is None:
            raise ValueError(f"Object '{target}' not found")
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
            mod.offset = params.get("offset", -1.0)
        elif type == "screw":
            mod.angle = params.get("angle", 6.28319)
            mod.steps = params.get("steps", 16)
            mod.render_steps = params.get("render_steps", 16)
            mod.screw_offset = params.get("screw_offset", 0.0)
            mod.iterations = params.get("iterations", 1)
            mod.axis = params.get("axis", "Z")
        elif type == "simple_deform":
            mod.deform_method = params.get("method") or params.get("deform_method", "BEND")
            mod.angle = params.get("angle", 0.7854)
            mod.deform_axis = params.get("deform_axis", "Z")
        elif type == "shrinkwrap":
            target_name = params.get("target", "")
            if target_name:
                target_obj = bpy.data.objects.get(target_name)
                if target_obj is None:
                    raise ValueError(f"Shrinkwrap target object '{target_name}' not found")
                mod.target = target_obj
            mod.offset = params.get("offset", 0.0)
            mod.wrap_method = params.get("wrap_method", "NEAREST_SURFACEPOINT")
            mod.subsurf_levels = params.get("subsurf_levels", 0)
        elif type == "decimate":
            mod.ratio = params.get("ratio", 0.5)
            mod.use_collapse_triangulate = params.get("use_collapse_triangulate", False)
        elif type == "remesh":
            mod.mode = params.get("mode", "SMOOTH")
            mod.octree_depth = params.get("octree_depth", 6)
            mod.scale = params.get("scale", 0.9)
        elif type == "weld":
            mod.merge_threshold = params.get("merge_threshold", 0.001)

        return {
            "object": target,
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

    # ================================================================
    #  Alignment (Object Mode)
    # ================================================================

    @registry.register(
        name="align_objects",
        description="Align objects along an axis (min/center/max)",
        parameters={
            "objects": {
                "type": "array",
                "description": "List of object names to align. If empty, aligns all selected objects.",
                "items": {"type": "string"},
                "required": False,
            },
            "axis": {
                "type": "string",
                "description": "Axis to align: X, Y, or Z",
                "required": True,
            },
            "align_to": {
                "type": "string",
                "description": "Alignment mode: MIN, CENTER, MAX (default CENTER)",
                "required": False,
            },
            "reference": {
                "type": "string",
                "description": "Reference object name. If not provided, uses the bounding box of all selected objects.",
                "required": False,
            },
        },
    )
    def align_objects(
        objects: list | None = None,
        axis: str = "X",
        align_to: str = "CENTER",
        reference: str | None = None,
    ):
        axis_idx = {"X": 0, "Y": 1, "Z": 2}.get(axis.upper())
        if axis_idx is None:
            raise ValueError(f"Unknown axis: {axis}. Use X, Y, or Z.")

        align_upper = align_to.upper()
        if align_upper not in ("MIN", "CENTER", "MAX"):
            raise ValueError("align_to must be MIN, CENTER, or MAX")

        if objects:
            targets = []
            for name in objects:
                obj = bpy.data.objects.get(name)
                if obj is None:
                    raise ValueError(f"Object '{name}' not found")
                targets.append(obj)
        else:
            targets = [obj for obj in bpy.context.selected_objects if obj.type == "MESH"]
            if not targets:
                targets = list(bpy.context.selected_objects)
            if not targets:
                raise ValueError("No objects specified or selected")

        # Determine reference bounds
        if reference:
            ref_obj = bpy.data.objects.get(reference)
            if ref_obj is None:
                raise ValueError(f"Reference object '{reference}' not found")
            ref_min = ref_obj.location[axis_idx]
            ref_max = ref_min
            # Use bounding box for size
            bbox = [ref_obj.matrix_world @ mathutils.Vector(v) for v in ref_obj.bound_box]
            ref_coords = [v[axis_idx] for v in bbox]
            ref_min = min(ref_coords)
            ref_max = max(ref_coords)
        else:
            all_coords = []
            for obj in targets:
                bbox = [obj.matrix_world @ mathutils.Vector(v) for v in obj.bound_box]
                all_coords.extend([v[axis_idx] for v in bbox])
            ref_min = min(all_coords)
            ref_max = max(all_coords)

        ref_center = (ref_min + ref_max) / 2

        for obj in targets:
            bbox = [obj.matrix_world @ mathutils.Vector(v) for v in obj.bound_box]
            obj_coords = [v[axis_idx] for v in bbox]
            obj_min = min(obj_coords)
            obj_max = max(obj_coords)
            obj_center = (obj_min + obj_max) / 2

            if align_upper == "MIN":
                offset = ref_min - obj_min
            elif align_upper == "CENTER":
                offset = ref_center - obj_center
            else:
                offset = ref_max - obj_max

            obj.location[axis_idx] += offset

        return {
            "aligned_objects": len(targets),
            "axis": axis.upper(),
            "align_to": align_upper,
            "reference": reference or "selection_bounds",
        }

    # ================================================================
    #  Light
    # ================================================================

    @registry.register(
        name="create_light",
        description="Create a light object in the scene",
        parameters={
            "type": {
                "type": "string",
                "description": "Light type: POINT, SUN, SPOT, or AREA (default POINT)",
                "required": False,
            },
            "energy": {
                "type": "number",
                "description": "Light intensity (default 100 for POINT/SPOT/AREA, 1 for SUN)",
                "required": False,
            },
            "color": {
                "type": "array",
                "description": "RGB color [r, g, b] values 0-1 (default [1, 1, 1])",
                "items": {"type": "number"},
                "required": False,
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
                "description": "Custom name for the light",
                "required": False,
            },
        },
    )
    def create_light(
        type: str = "POINT",
        energy: float | None = None,
        color: list | None = None,
        location: list | None = None,
        rotation: list | None = None,
        name: str | None = None,
    ):
        type_upper = type.upper()
        valid_types = {"POINT", "SUN", "SPOT", "AREA"}
        if type_upper not in valid_types:
            raise ValueError(f"Unknown light type: {type}. Use {valid_types}")

        if location is None:
            location = [0, 0, 0]
        if rotation is None:
            rotation = [0, 0, 0]
        if color is None:
            color = [1, 1, 1]
        if energy is None:
            energy = 1.0 if type_upper == "SUN" else 100.0

        light_data = bpy.data.lights.new(name=name or f"Light_{type_upper}", type=type_upper)
        light_data.energy = energy
        light_data.color = color

        obj = bpy.data.objects.new(name=light_data.name, object_data=light_data)
        obj.location = location
        obj.rotation_euler = rotation
        bpy.context.collection.objects.link(obj)

        return {
            "name": obj.name,
            "type": type_upper,
            "energy": energy,
            "color": color,
            "location": list(obj.location),
        }

    # ================================================================
    #  Camera
    # ================================================================

    @registry.register(
        name="create_camera",
        description="Create a camera object in the scene",
        parameters={
            "type": {
                "type": "string",
                "description": "Camera type: PERSPECTIVE, ORTHOGRAPHIC, or PANO (default PERSPECTIVE)",
                "required": False,
            },
            "location": {
                "type": "array",
                "description": "Location [x, y, z]",
                "items": {"type": "number"},
                "required": False,
            },
            "rotation": {
                "type": "array",
                "description": "Rotation [rx, ry, rz] in radians (default [0, 0, 0])",
                "items": {"type": "number"},
                "required": False,
            },
            "focal_length": {
                "type": "number",
                "description": "Focal length in mm (default 50). For PERSPECTIVE cameras.",
                "required": False,
            },
            "orthographic_scale": {
                "type": "number",
                "description": "Orthographic scale (default 6). For ORTHOGRAPHIC cameras.",
                "required": False,
            },
            "name": {
                "type": "string",
                "description": "Custom name for the camera",
                "required": False,
            },
            "make_active": {
                "type": "boolean",
                "description": "Set as active scene camera (default true)",
                "required": False,
            },
        },
    )
    def create_camera(
        type: str = "PERSPECTIVE",
        location: list | None = None,
        rotation: list | None = None,
        focal_length: float = 50.0,
        orthographic_scale: float = 6.0,
        name: str | None = None,
        make_active: bool = True,
    ):
        type_map = {"PERSPECTIVE": "PERSP", "ORTHOGRAPHIC": "ORTHO", "PANO": "PANO"}
        type_upper = type.upper()
        if type_upper not in type_map:
            raise ValueError("type must be PERSPECTIVE, ORTHOGRAPHIC, or PANO")
        cam_type = type_map[type_upper]

        if location is None:
            location = [0, 0, 0]
        if rotation is None:
            rotation = [0, 0, 0]

        cam_data = bpy.data.cameras.new(name=name or "Camera")
        cam_data.type = cam_type
        if cam_type == "PERSP":
            cam_data.lens = focal_length
        elif cam_type == "ORTHO":
            cam_data.ortho_scale = orthographic_scale

        obj = bpy.data.objects.new(name=cam_data.name, object_data=cam_data)
        obj.location = location
        obj.rotation_euler = rotation
        bpy.context.collection.objects.link(obj)

        if make_active:
            bpy.context.scene.camera = obj

        return {
            "name": obj.name,
            "type": type_upper,
            "location": list(obj.location),
            "focal_length": focal_length if cam_type == "PERSP" else None,
        }
