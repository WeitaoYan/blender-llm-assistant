"""High-precision mesh editing tools for Blender addon.

Provides edit mode operations, mesh selection, extrusion, bevel,
loop cut, knife, merge, delete geometry, shading, snapping, and more.
"""

import bpy # type: ignore
import bmesh # type: ignore
import mathutils # type: ignore


def _require_mesh_object(obj_name: str):
    """Get a mesh object by name, or raise."""
    obj = bpy.data.objects.get(obj_name)
    if obj is None:
        raise ValueError(f"Object '{obj_name}' not found")
    if obj.type != "MESH":
        raise ValueError(f"Object '{obj_name}' is not a mesh (type={obj.type})")
    return obj


def _ensure_edit_mode(obj):
    """Switch obj to edit mode; returns True if we entered edit mode now."""
    if obj.mode == "EDIT":
        return False
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    return True


def _ensure_object_mode():
    """Switch to object mode if not already."""
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def register_tools(registry):

    # ================================================================
    #  Edit Mode Control
    # ================================================================

    @registry.register(
        name="edit_mode_enter",
        description="Enter edit mode for a mesh object to modify its vertices, edges, or faces",
        parameters={
            "object": {
                "type": "string",
                "description": "Name of the mesh object to edit",
                "required": True,
            },
        },
    )
    def edit_mode_enter(object: str):
        obj = _require_mesh_object(object)
        _ensure_object_mode()
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(obj.data)
        return {
            "object": object,
            "mode": "EDIT",
            "vertices": len(bm.verts),
            "edges": len(bm.edges),
            "faces": len(bm.faces),
        }

    @registry.register(
        name="edit_mode_exit",
        description="Exit edit mode and return to object mode",
        parameters={},
    )
    def edit_mode_exit():
        if not bpy.context.mode.startswith("EDIT"):
            return {"mode": bpy.context.mode, "note": "Already not in edit mode"}
        bpy.ops.object.mode_set(mode="OBJECT")
        obj = bpy.context.active_object
        return {
            "mode": "OBJECT",
            "active_object": obj.name if obj else None,
        }

    @registry.register(
        name="get_mode",
        description="Get the current interaction mode and active object info",
        parameters={},
    )
    def get_mode():
        obj = bpy.context.active_object
        mode = bpy.context.mode
        result = {
            "mode": mode,
            "active_object": obj.name if obj else None,
        }
        if obj and obj.type == "MESH" and mode == "EDIT":
            bm = bmesh.from_edit_mesh(obj.data)
            result["mesh"] = {
                "vertices": len(bm.verts),
                "edges": len(bm.edges),
                "faces": len(bm.faces),
                "selected_vertices": sum(1 for v in bm.verts if v.select),
                "selected_edges": sum(1 for e in bm.edges if e.select),
                "selected_faces": sum(1 for f in bm.faces if f.select),
            }
        return result

    # ================================================================
    #  Mesh Selection
    # ================================================================

    @registry.register(
        name="mesh_select_all",
        description="Select or deselect all vertices/edges/faces in edit mode",
        parameters={
            "action": {
                "type": "string",
                "description": "SELECT, DESELECT, or INVERT",
                "required": False,
            },
        },
    )
    def mesh_select_all(action: str = "SELECT"):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        action_upper = action.upper()
        if action_upper not in ("SELECT", "DESELECT", "INVERT"):
            raise ValueError(f"Unknown action: {action}. Use SELECT, DESELECT, or INVERT.")
        bpy.ops.mesh.select_all(action=action_upper)
        return {"action": action_upper}

    @registry.register(
        name="mesh_select_by_type",
        description="Set the mesh selection mode (vertex, edge, or face)",
        parameters={
            "type": {
                "type": "string",
                "description": "Selection type: VERT, EDGE, or FACE",
                "required": True,
            },
        },
    )
    def mesh_select_by_type(type: str):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        type_map = {"VERT": True, "EDGE": True, "FACE": True}
        type_upper = type.upper()
        if type_upper not in type_map:
            raise ValueError(f"Unknown type: {type}. Use VERT, EDGE, or FACE.")
        bpy.context.tool_settings.mesh_select_mode = (
            type_upper == "VERT",
            type_upper == "EDGE",
            type_upper == "FACE",
        )
        return {"selection_mode": type_upper}

    @registry.register(
        name="mesh_select_loop",
        description="Select an edge loop from the current selection",
        parameters={},
    )
    def mesh_select_loop():
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.mesh.loop_multi_select(ring=False)
        return {"selected": "edge_loop"}

    @registry.register(
        name="mesh_select_ring",
        description="Select an edge ring from the current selection",
        parameters={},
    )
    def mesh_select_ring():
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.mesh.loop_multi_select(ring=True)
        return {"selected": "edge_ring"}

    @registry.register(
        name="mesh_select_more",
        description="Grow the selection to include adjacent elements",
        parameters={},
    )
    def mesh_select_more():
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.mesh.select_more()
        return {"action": "grow_selection"}

    @registry.register(
        name="mesh_select_less",
        description="Shrink the selection to remove boundary elements",
        parameters={},
    )
    def mesh_select_less():
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.mesh.select_less()
        return {"action": "shrink_selection"}

    @registry.register(
        name="mesh_select_by_axis",
        description="Select vertices/edges/faces on a specific side of the mesh along an axis",
        parameters={
            "axis": {
                "type": "string",
                "description": "Axis: X, Y, or Z",
                "required": True,
            },
            "sign": {
                "type": "string",
                "description": "POSITIVE or NEGATIVE side of the axis",
                "required": True,
            },
            "threshold": {
                "type": "number",
                "description": "Distance from origin along axis to split selection (default 0)",
                "required": False,
            },
        },
    )
    def mesh_select_by_axis(axis: str, sign: str, threshold: float = 0.0):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")

        axis_idx = {"X": 0, "Y": 1, "Z": 2}.get(axis.upper())
        if axis_idx is None:
            raise ValueError(f"Unknown axis: {axis}. Use X, Y, or Z.")

        sign_val = 1 if sign.upper() == "POSITIVE" else -1

        obj = bpy.context.active_object
        bm = bmesh.from_edit_mesh(obj.data)

        sel_mode = bpy.context.tool_settings.mesh_select_mode
        if sel_mode[0]:  # vertex
            for v in bm.verts:
                if sign_val * (v.co[axis_idx] - threshold) >= 0:
                    v.select = True
                else:
                    v.select = False
        elif sel_mode[2]:  # face
            for f in bm.faces:
                center = f.calc_center_median()
                if sign_val * (center[axis_idx] - threshold) >= 0:
                    f.select = True
                else:
                    f.select = False
        else:  # edge
            for e in bm.edges:
                center = (e.verts[0].co + e.verts[1].co) / 2
                if sign_val * (center[axis_idx] - threshold) >= 0:
                    e.select = True
                else:
                    e.select = False

        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data)
        return {"axis": axis.upper(), "side": sign.upper(), "threshold": threshold}

    # ================================================================
    #  Geometry Operations
    # ================================================================

    @registry.register(
        name="mesh_extrude",
        description="Extrude selected vertices, edges, or faces in edit mode",
        parameters={
            "offset_x": {
                "type": "number",
                "description": "Extrusion distance along X axis",
                "required": False,
            },
            "offset_y": {
                "type": "number",
                "description": "Extrusion distance along Y axis",
                "required": False,
            },
            "offset_z": {
                "type": "number",
                "description": "Extrusion distance along Z axis",
                "required": False,
            },
            "individual": {
                "type": "boolean",
                "description": "Extrude each face individually instead of as a region",
                "required": False,
            },
        },
    )
    def mesh_extrude(offset_x: float = 0.0, offset_y: float = 0.0, offset_z: float = 0.0, individual: bool = False):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")

        if individual:
            bpy.ops.mesh.extrude_individual_move(
                TRANSFORM_OT_translate={"value": (offset_x, offset_y, offset_z)}
            )
        else:
            bpy.ops.mesh.extrude_region_move(
                TRANSFORM_OT_translate={"value": (offset_x, offset_y, offset_z)}
            )

        obj = bpy.context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        return {
            "offset": [offset_x, offset_y, offset_z],
            "individual": individual,
            "selected_vertices": sum(1 for v in bm.verts if v.select),
            "selected_faces": sum(1 for f in bm.faces if f.select),
        }

    @registry.register(
        name="mesh_inset",
        description="Inset selected faces inward",
        parameters={
            "thickness": {
                "type": "number",
                "description": "Inset distance (default 0.1)",
                "required": False,
            },
            "depth": {
                "type": "number",
                "description": "Inset depth for extruded inset (0 = flat inset)",
                "required": False,
            },
            "individual": {
                "type": "boolean",
                "description": "Inset each face individually",
                "required": False,
            },
        },
    )
    def mesh_inset(thickness: float = 0.1, depth: float = 0.0, individual: bool = True):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.mesh.inset(
            thickness=thickness,
            depth=depth,
            use_individual=individual,
            use_even_offset=True,
            use_relative_offset=False,
        )
        return {"thickness": thickness, "depth": depth, "individual": individual}

    @registry.register(
        name="mesh_bevel",
        description="Bevel selected vertices or edges",
        parameters={
            "width": {
                "type": "number",
                "description": "Bevel width (default 0.1)",
                "required": False,
            },
            "segments": {
                "type": "integer",
                "description": "Number of bevel segments (default 1)",
                "required": False,
            },
            "profile": {
                "type": "number",
                "description": "Bevel profile shape 0-1 (0.5 = round, default 0.5)",
                "required": False,
            },
            "affect": {
                "type": "string",
                "description": "What to bevel: VERTICES or EDGES (default EDGES)",
                "required": False,
            },
        },
    )
    def mesh_bevel(width: float = 0.1, segments: int = 1, profile: float = 0.5, affect: str = "EDGES"):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")

        affect_upper = affect.upper()
        if affect_upper not in ("VERTICES", "EDGES"):
            raise ValueError(f"Unknown affect: {affect}. Use VERTICES or EDGES.")

        bpy.ops.mesh.bevel(
            offset=width,
            segments=segments,
            profile=profile,
            offset_type="OFFSET",
            affect=affect_upper,
        )
        return {"width": width, "segments": segments, "profile": profile, "affect": affect_upper}

    @registry.register(
        name="mesh_loop_cut",
        description="Add loop cuts to the mesh",
        parameters={
            "count": {
                "type": "integer",
                "description": "Number of cuts (default 1)",
                "required": False,
            },
            "smoothness": {
                "type": "number",
                "description": "Slide smoothness factor 0-1 (default 0)",
                "required": False,
            },
            "object": {
                "type": "string",
                "description": "Object name. If not provided, uses active object",
                "required": False,
            },
        },
    )
    def mesh_loop_cut(count: int = 1, smoothness: float = 0.0, object: str | None = None):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")

        obj = bpy.data.objects.get(object) if object else bpy.context.active_object
        if obj is None or obj.type != "MESH":
            raise ValueError("No valid mesh object in edit mode")
        bm = bmesh.from_edit_mesh(obj.data)

        # Get selected edges to find loops
        selected_edges = [e for e in bm.edges if e.select]

        if not selected_edges:
            # If no edges selected, use bpy.ops which will do a preview
            bpy.ops.mesh.loopcut_slide(
                MESH_OT_loopcut={"number_cuts": count, "smoothness": smoothness},
                TRANSFORM_OT_edge_slide={"value": 0.5, "single_side": False},
            )
        else:
            # Use bmesh to subdivide edges
            bmesh.ops.subdivide_edges(
                bm,
                edges=selected_edges,
                cuts=count,
                smooth=smoothness,
            )

        bmesh.update_edit_mesh(obj.data)
        return {"cuts": count, "smoothness": smoothness}

    @registry.register(
        name="mesh_knife",
        description="Cut geometry with the knife tool along screen-space points",
        parameters={
            "points": {
                "type": "array",
                "description": "List of [x, y] screen-space points for the knife cut",
                "items": {"type": "array", "items": {"type": "number"}},
                "required": True,
            },
        },
    )
    def mesh_knife(points: list):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")

        # For 3D knife, convert screen points to region coordinates
        # This is limited; a more robust approach uses bmesh.ops.bisect_plane
        # Here we provide a bisect-based alternative for precision cuts

        if len(points) < 2:
            raise ValueError("Need at least 2 points for a knife cut")

        obj = bpy.context.active_object
        bm = bmesh.from_edit_mesh(obj.data)

        # Use bisect for a clean cut between two points in 3D
        p1 = mathutils.Vector(points[0])
        p2 = mathutils.Vector(points[1])

        # Calculate plane from the two points and view direction
        cut_dir = (p2 - p1).normalized()
        view_normal = mathutils.Vector((0, 0, 1))  # default Z-up

        plane_no = cut_dir.cross(view_normal).normalized()
        if plane_no.length < 0.001:
            plane_no = cut_dir.cross(mathutils.Vector((0, 1, 0))).normalized()

        plane_co = (p1 + p2) / 2

        _geom = bmesh.ops.bisect_plane(
            bm,
            geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
            plane_co=plane_co,
            plane_no=plane_no,
            clear_inner=False,
            clear_outer=False,
        )

        bmesh.update_edit_mesh(obj.data)
        return {"cut_points": len(points), "plane_co": list(plane_co), "plane_no": list(plane_no)}

    @registry.register(
        name="mesh_bisect",
        description="Bisect (cut) the mesh along a plane defined by a point and normal",
        parameters={
            "plane_co": {
                "type": "array",
                "description": "Point on the cutting plane [x, y, z]",
                "items": {"type": "number"},
                "required": True,
            },
            "plane_no": {
                "type": "array",
                "description": "Normal of the cutting plane [nx, ny, nz]",
                "items": {"type": "number"},
                "required": True,
            },
            "clear_inner": {
                "type": "boolean",
                "description": "Delete geometry on the inner (negative) side of the plane",
                "required": False,
            },
            "clear_outer": {
                "type": "boolean",
                "description": "Delete geometry on the outer (positive) side of the plane",
                "required": False,
            },
            "fill": {
                "type": "boolean",
                "description": "Fill the cut surface with geometry",
                "required": False,
            },
        },
    )
    def mesh_bisect(
        plane_co: list,
        plane_no: list,
        clear_inner: bool = False,
        clear_outer: bool = False,
        fill: bool = True,
    ):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")

        obj = bpy.context.active_object
        bm = bmesh.from_edit_mesh(obj.data)

        geom = bmesh.ops.bisect_plane(
            bm,
            geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
            plane_co=mathutils.Vector(plane_co),
            plane_no=mathutils.Vector(plane_no),
            clear_inner=clear_inner,
            clear_outer=clear_outer,
        )

        if fill:
            # Find edges created by the bisect and fill them
            cut_edges = [e for e in geom.get("geom_cut", []) if isinstance(e, bmesh.types.BMEdge)]
            if cut_edges:
                bmesh.ops.edgenet_fill(bm, edges=cut_edges)

        bmesh.update_edit_mesh(obj.data)
        return {
            "plane_co": plane_co,
            "plane_no": plane_no,
            "clear_inner": clear_inner,
            "clear_outer": clear_outer,
            "fill": fill,
        }

    @registry.register(
        name="mesh_merge",
        description="Merge selected vertices by distance, at center, or at cursor",
        parameters={
            "method": {
                "type": "string",
                "description": "Merge method: BY_DISTANCE, AT_CENTER, AT_CURSOR, AT_FIRST, AT_LAST",
                "required": False,
            },
            "distance": {
                "type": "number",
                "description": "Merge distance for BY_DISTANCE method (default 0.001)",
                "required": False,
            },
        },
    )
    def mesh_merge(method: str = "BY_DISTANCE", distance: float = 0.001):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")

        method_map = {
            "BY_DISTANCE": "merge_by_distance",
            "AT_CENTER": "merge_at_center",
            "AT_CURSOR": "merge_at_cursor",
            "AT_FIRST": "merge_at_first",
            "AT_LAST": "merge_at_last",
        }

        if method.upper() not in method_map:
            valid = ", ".join(method_map.keys())
            raise ValueError(f"Unknown method: {method}. Use one of: {valid}")

        if method.upper() == "BY_DISTANCE":
            bpy.ops.mesh.remove_doubles(threshold=distance, use_unselected=False)
        elif method.upper() == "AT_CENTER":
            bpy.ops.mesh.merge(type="CENTER")
        elif method.upper() == "AT_CURSOR":
            bpy.ops.mesh.merge(type="CURSOR")
        elif method.upper() == "AT_FIRST":
            bpy.ops.mesh.merge(type="FIRST")
        elif method.upper() == "AT_LAST":
            bpy.ops.mesh.merge(type="LAST")

        obj = bpy.context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        return {
            "method": method.upper(),
            "distance": distance if method.upper() == "BY_DISTANCE" else None,
            "remaining_vertices": len(bm.verts),
        }

    @registry.register(
        name="mesh_delete",
        description="Delete selected vertices, edges, or faces in edit mode",
        parameters={
            "type": {
                "type": "string",
                "description": "What to delete: VERT, EDGE, FACE, ONLY_FACE, EDGE_LOOP, or DISSOLVE",
                "required": False,
            },
        },
    )
    def mesh_delete(type: str = "VERT"):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")

        type_map = {
            "VERT": "VERT",
            "EDGE": "EDGE",
            "FACE": "FACE",
            "ONLY_FACE": "ONLY_FACE",
            "EDGE_LOOP": "EDGE_LOOP",
            "DISSOLVE": "DISSOLVE",
        }

        type_upper = type.upper()
        if type_upper not in type_map:
            valid = ", ".join(type_map.keys())
            raise ValueError(f"Unknown delete type: {type}. Use one of: {valid}")

        if type_upper == "DISSOLVE":
            bpy.ops.mesh.dissolve_mode()
        else:
            bpy.ops.mesh.delete(type=type_upper)

        obj = bpy.context.active_object
        # Gracefully handle case where delete removed all geometry
        try:
            bm = bmesh.from_edit_mesh(obj.data)
            verts = len(bm.verts)
            edges = len(bm.edges)
            faces = len(bm.faces)
        except Exception:
            verts = 0
            edges = 0
            faces = 0

        return {
            "deleted_type": type_upper,
            "remaining_vertices": verts,
            "remaining_edges": edges,
            "remaining_faces": faces,
        }

    @registry.register(
        name="mesh_fill",
        description="Fill a hole bounded by selected edges or vertices",
        parameters={},
    )
    def mesh_fill():
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")

        obj = bpy.context.active_object
        bm = bmesh.from_edit_mesh(obj.data)

        # If no edges are selected, auto-select boundary edges to fill holes
        selected_edges = [e for e in bm.edges if e.select]
        if not selected_edges:
            for e in bm.edges:
                if e.is_boundary:
                    e.select = True
            bm.select_flush_mode()
            bmesh.update_edit_mesh(obj.data)

        bpy.ops.mesh.fill()
        bm = bmesh.from_edit_mesh(obj.data)
        return {"filled": True, "faces": len(bm.faces)}

    @registry.register(
        name="mesh_grid_fill",
        description="Grid fill selected edge loops to create a quad grid",
        parameters={
            "span": {
                "type": "integer",
                "description": "Number of spans for the grid",
                "required": False,
            },
        },
    )
    def mesh_grid_fill(span: int = 1):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.mesh.fill_grid(span=span)
        return {"grid_fill": True, "span": span}

    @registry.register(
        name="mesh_bridge",
        description="Bridge two selected edge loops to create faces between them",
        parameters={
            "segments": {
                "type": "integer",
                "description": "Number of segments for the bridge",
                "required": False,
            },
            "twist": {
                "type": "integer",
                "description": "Twist offset for the bridge",
                "required": False,
            },
        },
    )
    def mesh_bridge(segments: int = 1, twist: int = 0):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.mesh.bridge_edge_loops(number_cuts=segments)
        return {"bridged": True, "segments": segments, "twist": twist}

    @registry.register(
        name="mesh_subdivide",
        description="Subdivide selected edges or faces",
        parameters={
            "cuts": {
                "type": "integer",
                "description": "Number of subdivisions (default 1)",
                "required": False,
            },
            "smoothness": {
                "type": "number",
                "description": "Smoothness factor 0-1 (default 0)",
                "required": False,
            },
        },
    )
    def mesh_subdivide(cuts: int = 1, smoothness: float = 0.0):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.mesh.subdivide(number_cuts=cuts, smoothness=smoothness)
        obj = bpy.context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        return {
            "cuts": cuts,
            "smoothness": smoothness,
            "vertices": len(bm.verts),
            "faces": len(bm.faces),
        }

    @registry.register(
        name="mesh_split",
        description="Split selected geometry from the rest (Y key / separate)",
        parameters={
            "method": {
                "type": "string",
                "description": "Split method: SELECTION (detach selected), FACES_BY_EDGES (split faces along edges)",
                "required": False,
            },
        },
    )
    def mesh_split(method: str = "SELECTION"):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")

        if method.upper() == "SELECTION":
            bpy.ops.mesh.split()
        elif method.upper() == "FACES_BY_EDGES":
            bpy.ops.mesh.edge_split()
        else:
            raise ValueError(f"Unknown method: {method}. Use SELECTION or FACES_BY_EDGES.")

        return {"split_method": method.upper()}

    @registry.register(
        name="mesh_separate",
        description="Separate selected geometry into a new object",
        parameters={},
    )
    def mesh_separate():
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")

        old_objects = set(bpy.data.objects.keys())
        bpy.ops.mesh.separate(type="SELECTED")
        new_objects = set(bpy.data.objects.keys()) - old_objects

        return {
            "separated": True,
            "new_objects": list(new_objects),
        }

    @registry.register(
        name="mesh_join",
        description="Join multiple selected objects into a single mesh",
        parameters={
            "objects": {
                "type": "array",
                "description": "List of object names to join. If empty, joins all selected objects.",
                "items": {"type": "string"},
                "required": False,
            },
        },
    )
    def mesh_join(objects: list | None = None):
        _ensure_object_mode()

        if objects:
            bpy.ops.object.select_all(action="DESELECT")
            for name in objects:
                obj = bpy.data.objects.get(name)
                if obj:
                    obj.select_set(True)
                    bpy.context.view_layer.objects.active = obj

        bpy.ops.object.join()

        obj = bpy.context.active_object
        return {
            "result": obj.name if obj else None,
            "vertices": len(obj.data.vertices) if obj and obj.type == "MESH" else 0,
        }

    # ================================================================
    #  Shading & Normals
    # ================================================================

    @registry.register(
        name="shade_smooth",
        description="Set selected faces or entire object to smooth shading",
        parameters={
            "object": {
                "type": "string",
                "description": "Object name. Uses active object if not provided.",
                "required": False,
            },
        },
    )
    def shade_smooth(object: str | None = None):
        if object:
            obj = _require_mesh_object(object)
        else:
            obj = bpy.context.active_object
            if obj is None or obj.type != "MESH":
                raise ValueError("No active mesh object. Specify an object name or select one.")

        was_edit = bpy.context.mode == "EDIT"
        if was_edit:
            bpy.ops.object.mode_set(mode="OBJECT")

        bpy.ops.object.shade_smooth()

        if was_edit:
            bpy.ops.object.mode_set(mode="EDIT")

        return {
            "object": obj.name,
            "shading": "smooth",
        }

    @registry.register(
        name="shade_flat",
        description="Set selected faces or entire object to flat shading",
        parameters={
            "object": {
                "type": "string",
                "description": "Object name. Uses active object if not provided.",
                "required": False,
            },
        },
    )
    def shade_flat(object: str | None = None):
        if object:
            obj = _require_mesh_object(object)
        else:
            obj = bpy.context.active_object
            if obj is None or obj.type != "MESH":
                raise ValueError("No active mesh object. Specify an object name or select one.")

        was_edit = bpy.context.mode == "EDIT"
        if was_edit:
            bpy.ops.object.mode_set(mode="OBJECT")

        bpy.ops.object.shade_flat()

        if was_edit:
            bpy.ops.object.mode_set(mode="EDIT")

        return {"object": obj.name, "shading": "flat"}

    @registry.register(
        name="mesh_normals_recalculate",
        description="Recalculate normals to face outside (or inside)",
        parameters={
            "direction": {
                "type": "string",
                "description": "OUTSIDE or INSIDE (default OUTSIDE)",
                "required": False,
            },
        },
    )
    def mesh_normals_recalculate(direction: str = "OUTSIDE"):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")

        if direction.upper() == "OUTSIDE":
            bpy.ops.mesh.normals_make_consistent(inside=False)
        elif direction.upper() == "INSIDE":
            bpy.ops.mesh.normals_make_consistent(inside=True)
        else:
            raise ValueError(f"Unknown direction: {direction}. Use OUTSIDE or INSIDE.")

        return {"direction": direction.upper()}

    @registry.register(
        name="mesh_flip_normals",
        description="Flip the normals of selected faces",
        parameters={},
    )
    def mesh_flip_normals():
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.mesh.flip_normals()
        return {"flipped": True}

    # ================================================================
    #  Snapping & Precision
    # ================================================================

    @registry.register(
        name="snap_config",
        description="Configure snapping settings for precise modeling",
        parameters={
            "enable": {
                "type": "boolean",
                "description": "Enable or disable snapping",
                "required": True,
            },
            "snap_to": {
                "type": "string",
                "description": "Snap target: VERTEX, EDGE, FACE, VOLUME, EDGE_MIDPOINT, EDGE_PERPENDICULAR, INCREMENT, GRID",
                "required": False,
            },
            "affect": {
                "type": "string",
                "description": "What snapping affects: MOVE, ROTATE, SCALE (comma-separated)",
                "required": False,
            },
        },
    )
    def snap_config(enable: bool, snap_to: str = "VERTEX", affect: str | None = None):
        ts = bpy.context.scene.tool_settings
        ts.use_snap = enable

        if snap_to:
            snap_map = {
                "VERTEX": "VERTEX",
                "EDGE": "EDGE",
                "FACE": "FACE",
                "VOLUME": "VOLUME",
                "EDGE_MIDPOINT": "EDGE_MIDPOINT",
                "EDGE_PERPENDICULAR": "EDGE_PERPENDICULAR",
                "INCREMENT": "INCREMENT",
                "GRID": "GRID",
            }
            snap_upper = snap_to.upper()
            if snap_upper not in snap_map:
                raise ValueError(f"Unknown snap target: {snap_to}")
            ts.snap_elements = {snap_upper}

        if affect:
            affects = [a.strip().upper() for a in affect.split(",")]
            ts.use_snap_translate = "MOVE" in affects
            ts.use_snap_rotate = "ROTATE" in affects
            ts.use_snap_scale = "SCALE" in affects

        return {
            "snap_enabled": enable,
            "snap_to": snap_to.upper() if snap_to else None,
            "snap_affects": affect,
        }

    @registry.register(
        name="set_cursor",
        description="Set the 3D cursor to a specific location",
        parameters={
            "location": {
                "type": "array",
                "description": "Cursor location [x, y, z]",
                "items": {"type": "number"},
                "required": True,
            },
        },
    )
    def set_cursor(location: list):
        bpy.context.scene.cursor.location = location
        return {"cursor": list(bpy.context.scene.cursor.location)}

    @registry.register(
        name="set_origin",
        description="Set the origin of an object",
        parameters={
            "object": {
                "type": "string",
                "description": "Object name",
                "required": True,
            },
            "origin_to": {
                "type": "string",
                "description": "Where to set origin: GEOMETRY, CURSOR, CENTER_OF_MASS",
                "required": False,
            },
        },
    )
    def set_origin(object: str, origin_to: str = "GEOMETRY"):
        obj = _require_mesh_object(object)
        _ensure_object_mode()
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)

        origin_map = {
            "GEOMETRY": "ORIGIN_GEOMETRY",
            "CURSOR": "ORIGIN_CURSOR",
            "CENTER_OF_MASS": "ORIGIN_CENTER_OF_MASS",
        }
        origin_upper = origin_to.upper()
        if origin_upper not in origin_map:
            raise ValueError(f"Unknown origin: {origin_to}. Use GEOMETRY, CURSOR, or CENTER_OF_MASS.")

        bpy.ops.object.origin_set(type=origin_map[origin_upper])

        return {
            "object": object,
            "origin": origin_upper,
            "new_location": list(obj.location),
        }

    @registry.register(
        name="apply_transform",
        description="Apply (freeze) object transforms (location, rotation, scale) to the mesh data",
        parameters={
            "object": {
                "type": "string",
                "description": "Object name",
                "required": True,
            },
            "apply_location": {
                "type": "boolean",
                "description": "Apply location (default true)",
                "required": False,
            },
            "apply_rotation": {
                "type": "boolean",
                "description": "Apply rotation (default true)",
                "required": False,
            },
            "apply_scale": {
                "type": "boolean",
                "description": "Apply scale (default true)",
                "required": False,
            },
        },
    )
    def apply_transform(
        object: str,
        apply_location: bool = True,
        apply_rotation: bool = True,
        apply_scale: bool = True,
    ):
        obj = _require_mesh_object(object)
        _ensure_object_mode()
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)

        bpy.ops.object.transform_apply(
            location=apply_location,
            rotation=apply_rotation,
            scale=apply_scale,
        )

        return {
            "object": object,
            "location": list(obj.location),
            "rotation": list(obj.rotation_euler),
            "scale": list(obj.scale),
        }

    # ================================================================
    #  Vertex Groups & Shape Keys
    # ================================================================

    @registry.register(
        name="vertex_group_create",
        description="Create a new vertex group on a mesh object",
        parameters={
            "object": {
                "type": "string",
                "description": "Object name",
                "required": True,
            },
            "group_name": {
                "type": "string",
                "description": "Name of the vertex group",
                "required": True,
            },
        },
    )
    def vertex_group_create(object: str, group_name: str):
        obj = _require_mesh_object(object)
        vg = obj.vertex_groups.get(group_name)
        if vg is None:
            vg = obj.vertex_groups.new(name=group_name)
        return {"object": object, "vertex_group": group_name, "index": vg.index}

    @registry.register(
        name="vertex_group_assign",
        description="Assign selected vertices to a vertex group with a given weight",
        parameters={
            "object": {
                "type": "string",
                "description": "Object name",
                "required": True,
            },
            "group_name": {
                "type": "string",
                "description": "Vertex group name",
                "required": True,
            },
            "weight": {
                "type": "number",
                "description": "Weight value 0-1 (default 1.0)",
                "required": False,
            },
        },
    )
    def vertex_group_assign(object: str, group_name: str, weight: float = 1.0):
        obj = _require_mesh_object(object)
        vg = obj.vertex_groups.get(group_name)
        if vg is None:
            raise ValueError(f"Vertex group '{group_name}' not found on '{object}'")

        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode to assign vertices. Use edit_mode_enter first.")

        bm = bmesh.from_edit_mesh(obj.data)
        selected_verts = [v for v in bm.verts if v.select]

        # We need to exit edit mode briefly to assign via the API, or use bpy.ops
        # Using bpy.ops approach
        bpy.ops.object.vertex_group_assign()

        return {"object": object, "group": group_name, "weight": weight, "assigned_vertices": len(selected_verts)}

    @registry.register(
        name="vertex_group_remove",
        description="Remove selected vertices from a vertex group",
        parameters={
            "object": {
                "type": "string",
                "description": "Object name",
                "required": True,
            },
            "group_name": {
                "type": "string",
                "description": "Vertex group name",
                "required": True,
            },
        },
    )
    def vertex_group_remove(object: str, group_name: str):
        obj = _require_mesh_object(object)
        vg = obj.vertex_groups.get(group_name)
        if vg is None:
            raise ValueError(f"Vertex group '{group_name}' not found on '{object}'")

        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")

        bpy.ops.object.vertex_group_remove_from()
        return {"object": object, "group": group_name}

    @registry.register(
        name="shape_key_create",
        description="Create a shape key (basis or relative) on a mesh object",
        parameters={
            "object": {
                "type": "string",
                "description": "Object name",
                "required": True,
            },
            "key_name": {
                "type": "string",
                "description": "Name for the shape key. 'Basis' creates the basis key.",
                "required": True,
            },
            "from_mix": {
                "type": "boolean",
                "description": "Create from current mix of shape keys",
                "required": False,
            },
        },
    )
    def shape_key_create(object: str, key_name: str, from_mix: bool = False):
        obj = _require_mesh_object(object)
        _ensure_object_mode()

        if obj.data.shape_keys is None:
            obj.shape_key_add(name="Basis")

        if key_name.upper() != "BASIS":
            sk = obj.shape_key_add(name=key_name, from_mix=from_mix)
            return {"object": object, "shape_key": key_name, "index": sk.name}

        return {"object": object, "shape_key": "Basis", "note": "Basis already exists or was created"}

    @registry.register(
        name="shape_key_set_value",
        description="Set the influence value of a shape key",
        parameters={
            "object": {
                "type": "string",
                "description": "Object name",
                "required": True,
            },
            "key_name": {
                "type": "string",
                "description": "Shape key name",
                "required": True,
            },
            "value": {
                "type": "number",
                "description": "Influence value 0-1 (default 1.0)",
                "required": False,
            },
        },
    )
    def shape_key_set_value(object: str, key_name: str, value: float = 1.0):
        obj = _require_mesh_object(object)
        if obj.data.shape_keys is None:
            raise ValueError(f"Object '{object}' has no shape keys")

        sk = obj.data.shape_keys.key_blocks.get(key_name)
        if sk is None:
            available = [k.name for k in obj.data.shape_keys.key_blocks]
            raise ValueError(f"Shape key '{key_name}' not found. Available: {available}")

        sk.value = max(0.0, min(1.0, value))
        return {"object": object, "shape_key": key_name, "value": sk.value}

    # ================================================================
    #  Collection & Hierarchy
    # ================================================================

    @registry.register(
        name="collection_create",
        description="Create a new collection in the scene",
        parameters={
            "name": {
                "type": "string",
                "description": "Collection name",
                "required": True,
            },
        },
    )
    def collection_create(name: str):
        coll = bpy.data.collections.get(name)
        if coll is None:
            coll = bpy.data.collections.new(name)
            bpy.context.scene.collection.children.link(coll)
        return {"collection": name, "created": True}

    @registry.register(
        name="collection_add_object",
        description="Add an object to a collection",
        parameters={
            "object": {
                "type": "string",
                "description": "Object name",
                "required": True,
            },
            "collection": {
                "type": "string",
                "description": "Collection name",
                "required": True,
            },
        },
    )
    def collection_add_object(object: str, collection: str):
        obj = bpy.data.objects.get(object)
        if obj is None:
            raise ValueError(f"Object '{object}' not found")

        coll = bpy.data.collections.get(collection)
        if coll is None:
            raise ValueError(f"Collection '{collection}' not found")

        # Unlink from all other collections first
        for c in obj.users_collection:
            c.objects.unlink(obj)
        coll.objects.link(obj)

        return {"object": object, "collection": collection}

    @registry.register(
        name="set_parent",
        description="Set a parent-child relationship between two objects",
        parameters={
            "child": {
                "type": "string",
                "description": "Child object name",
                "required": True,
            },
            "parent": {
                "type": "string",
                "description": "Parent object name. Use empty string to clear parent.",
                "required": False,
            },
            "keep_transform": {
                "type": "boolean",
                "description": "Keep the child's world-space transform (default true)",
                "required": False,
            },
        },
    )
    def set_parent(child: str, parent: str = "", keep_transform: bool = True):
        child_obj = bpy.data.objects.get(child)
        if child_obj is None:
            raise ValueError(f"Child object '{child}' not found")

        parent_obj = None
        if parent:
            parent_obj = bpy.data.objects.get(parent)
            if parent_obj is None:
                raise ValueError(f"Parent object '{parent}' not found")
            child_obj.parent = parent_obj
        else:
            child_obj.parent = None

        if keep_transform and parent and parent_obj:
            child_obj.matrix_parent_inverse = parent_obj.matrix_world.inverted()

        return {
            "child": child,
            "parent": parent or None,
            "keep_transform": keep_transform,
        }

    # ================================================================
    #  Measurement & Analysis
    # ================================================================

    @registry.register(
        name="measure_distance",
        description="Measure the distance between two selected vertices or two objects",
        parameters={
            "object_a": {
                "type": "string",
                "description": "First object name",
                "required": False,
            },
            "object_b": {
                "type": "string",
                "description": "Second object name",
                "required": False,
            },
            "vertex_a": {
                "type": "integer",
                "description": "Index of first vertex (if in edit mode)",
                "required": False,
            },
            "vertex_b": {
                "type": "integer",
                "description": "Index of second vertex (if in edit mode)",
                "required": False,
            },
        },
    )
    def measure_distance(
        object_a: str | None = None,
        object_b: str | None = None,
        vertex_a: int | None = None,
        vertex_b: int | None = None,
    ):
        if bpy.context.mode == "EDIT" and vertex_a is not None and vertex_b is not None:
            obj = bpy.context.active_object
            bm = bmesh.from_edit_mesh(obj.data)
            v_a = bm.verts[vertex_a] if vertex_a < len(bm.verts) else None
            v_b = bm.verts[vertex_b] if vertex_b < len(bm.verts) else None
            if v_a is None or v_b is None:
                raise ValueError("Vertex index out of range")
            dist = (v_a.co - v_b.co).length
            return {"distance": round(dist, 6), "unit": "blender_units"}

        if object_a and object_b:
            obj_a = bpy.data.objects.get(object_a)
            obj_b = bpy.data.objects.get(object_b)
            if obj_a is None:
                raise ValueError(f"Object '{object_a}' not found")
            if obj_b is None:
                raise ValueError(f"Object '{object_b}' not found")
            dist = (obj_a.location - obj_b.location).length
            return {"distance": round(dist, 6), "unit": "blender_units", "center_to_center": True}

        # Fallback: measure between active and selected
        if bpy.context.mode == "EDIT":
            obj = bpy.context.active_object
            bm = bmesh.from_edit_mesh(obj.data)
            selected = [v for v in bm.verts if v.select]
            if len(selected) >= 2:
                dist = (selected[0].co - selected[1].co).length
                return {"distance": round(dist, 6), "unit": "blender_units", "vertex_indices": [selected[0].index, selected[1].index]}

        raise ValueError("Provide two object names, two vertex indices in edit mode, or select two vertices.")

    @registry.register(
        name="measure_angle",
        description="Measure the angle between three selected vertices or three objects",
        parameters={
            "object_a": {
                "type": "string",
                "description": "First object name",
                "required": False,
            },
            "object_b": {
                "type": "string",
                "description": "Middle (pivot) object name",
                "required": False,
            },
            "object_c": {
                "type": "string",
                "description": "Third object name",
                "required": False,
            },
        },
    )
    def measure_angle(
        object_a: str | None = None,
        object_b: str | None = None,
        object_c: str | None = None,
    ):
        import math

        if object_a and object_b:
            obj_a = bpy.data.objects.get(object_a)
            obj_b = bpy.data.objects.get(object_b)
            if not obj_a or not obj_b:
                raise ValueError("One or more objects not found")
            if object_c:
                obj_c = bpy.data.objects.get(object_c)
                if not obj_c:
                    raise ValueError("One or more objects not found")
                va = mathutils.Vector(obj_a.location) - mathutils.Vector(obj_b.location)
                vc = mathutils.Vector(obj_c.location) - mathutils.Vector(obj_b.location)
                angle = va.angle(vc)
            else:
                va = mathutils.Vector(obj_a.location)
                vc = mathutils.Vector(obj_b.location)
                angle = va.angle(vc)
            return {"angle_rad": round(angle, 6), "angle_deg": round(math.degrees(angle), 2)}

        # Edit mode: use first 3 selected vertices
        if bpy.context.mode == "EDIT":
            obj = bpy.context.active_object
            bm = bmesh.from_edit_mesh(obj.data)
            selected = [v for v in bm.verts if v.select]
            if len(selected) >= 3:
                va = selected[0].co - selected[1].co
                vc = selected[2].co - selected[1].co
                angle = va.angle(vc)
                return {"angle_rad": round(angle, 6), "angle_deg": round(math.degrees(angle), 2)}

        raise ValueError("Provide two or three object names, or select three vertices in edit mode.")

    @registry.register(
        name="get_mesh_stats",
        description="Get detailed statistics about a mesh object",
        parameters={
            "object": {
                "type": "string",
                "description": "Object name. Uses active object if not provided.",
                "required": False,
            },
        },
    )
    def get_mesh_stats(object: str | None = None):
        if object:
            obj = _require_mesh_object(object)
        else:
            obj = bpy.context.active_object
            if obj is None or obj.type != "MESH":
                raise ValueError("No active mesh object.")

        mesh = obj.data
        verts = len(mesh.vertices)
        edges = len(mesh.edges)
        faces = len(mesh.polygons)
        tris = sum(len(p.vertices) - 2 for p in mesh.polygons)

        # Bounding box
        bbox_local = [list(v) for v in obj.bound_box]
        bbox_world = [list(obj.matrix_world @ mathutils.Vector(v)) for v in obj.bound_box]

        # Count n-gons
        ngons = sum(1 for p in mesh.polygons if len(p.vertices) > 4)
        quads = sum(1 for p in mesh.polygons if len(p.vertices) == 4)
        tris_only = sum(1 for p in mesh.polygons if len(p.vertices) == 3)

        return {
            "object": obj.name,
            "vertices": verts,
            "edges": edges,
            "faces": faces,
            "triangles": tris,
            "quads": quads,
            "ngons": ngons,
            "tris_only": tris_only,
            "bbox_local": bbox_local,
            "bbox_world": bbox_world,
            "materials": [m.name for m in obj.data.materials if m],
            "modifiers": [{"name": m.name, "type": m.type} for m in obj.modifiers],
            "vertex_groups": [vg.name for vg in obj.vertex_groups],
            "shape_keys": [sk.name for sk in obj.data.shape_keys.key_blocks] if obj.data.shape_keys else [],
        }

    # ================================================================
    #  Edit Mode Precise Transform (P0)
    # ================================================================

    @registry.register(
        name="mesh_transform_selected",
        description="Move/rotate/scale selected geometry in edit mode with exact values",
        parameters={
            "object": {
                "type": "string",
                "description": "Object name",
                "required": True,
            },
            "mode": {
                "type": "string",
                "description": "Transform mode: TRANSLATE, ROTATE, or SCALE (default TRANSLATE)",
                "required": False,
            },
            "value": {
                "type": "array",
                "description": "Transform value: [x, y, z] for translation/scale, or angle in radians followed by axis for rotation",
                "items": {"type": "number"},
                "required": True,
            },
            "orient_type": {
                "type": "string",
                "description": "Transform orientation: GLOBAL, LOCAL, NORMAL, GIMBAL, VIEW (default GLOBAL)",
                "required": False,
            },
            "orient_axis": {
                "type": "string",
                "description": "Rotation axis: X, Y, Z (only for ROTATE mode, default Z)",
                "required": False,
            },
        },
    )
    def mesh_transform_selected(
        object: str,
        mode: str = "TRANSLATE",
        value: list | None = None,
        orient_type: str = "GLOBAL",
        orient_axis: str = "Z",
    ):
        obj = _require_mesh_object(object)
        if not bpy.context.mode.startswith("EDIT") or bpy.context.active_object != obj:
            raise ValueError("Must be in edit mode on the specified object.")

        if not value:
            raise ValueError("value is required")

        mode_upper = mode.upper()
        orient_type_upper = orient_type.upper()

        if mode_upper == "TRANSLATE":
            bpy.ops.transform.translate(
                value=tuple(value),
                orient_type=orient_type_upper,
            )
        elif mode_upper == "ROTATE":
            orient_axis_upper = orient_axis.upper()
            bpy.ops.transform.rotate(
                value=value[0],
                orient_axis=orient_axis_upper,
                orient_type=orient_type_upper,
            )
        elif mode_upper == "SCALE":
            bpy.ops.transform.resize(
                value=tuple(value),
                orient_type=orient_type_upper,
            )
        else:
            raise ValueError(f"Unknown mode: {mode}. Use TRANSLATE, ROTATE, or SCALE.")

        bm = bmesh.from_edit_mesh(obj.data)
        return {
            "mode": mode_upper,
            "value": value,
            "orient_type": orient_type_upper,
            "selected_vertices": sum(1 for v in bm.verts if v.select),
        }

    @registry.register(
        name="mesh_vert_slide",
        description="Slide selected vertices along the surface of the mesh",
        parameters={
            "value": {
                "type": "number",
                "description": "Slide factor from -1 to 1 (default 0). Negative slides backward, positive forward.",
                "required": False,
            },
        },
    )
    def mesh_vert_slide(value: float = 0.0):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.transform.vert_slide(value=value)
        return {"slide_value": value}

    @registry.register(
        name="mesh_edge_slide",
        description="Slide selected edges along the mesh surface",
        parameters={
            "value": {
                "type": "number",
                "description": "Slide factor from -1 to 1 (default 0). Negative slides backward, positive forward.",
                "required": False,
            },
        },
    )
    def mesh_edge_slide(value: float = 0.0):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.transform.edge_slide(value=value)
        return {"slide_value": value}

    @registry.register(
        name="proportional_edit",
        description="Configure proportional (bio) editing for organic high-precision modeling",
        parameters={
            "enable": {
                "type": "boolean",
                "description": "Enable or disable proportional editing",
                "required": True,
            },
            "falloff": {
                "type": "string",
                "description": "Falloff type: SMOOTH, SPHERE, ROOT, INVERSE_SQUARE, SHARP, LINEAR, CONSTANT, RANDOM, PROJECT (default SMOOTH)",
                "required": False,
            },
            "radius": {
                "type": "number",
                "description": "Radius of proportional editing in Blender units (default 1.0)",
                "required": False,
            },
            "connected": {
                "type": "boolean",
                "description": "Only affect connected geometry (default false)",
                "required": False,
            },
        },
    )
    def proportional_edit(enable: bool, falloff: str = "SMOOTH", radius: float = 1.0, connected: bool = False):
        ts = bpy.context.scene.tool_settings
        ts.use_proportional_edit = enable
        ts.proportional_edit_falloff = falloff.upper()
        ts.proportional_size = radius
        ts.use_proportional_connected = connected

        return {
            "proportional_enabled": enable,
            "falloff": falloff.upper(),
            "radius": radius,
            "connected": connected,
        }

    # ================================================================
    #  Subdivision Control & Marking (P1)
    # ================================================================

    @registry.register(
        name="mesh_crease",
        description="Set crease weight on selected edges for subdivision surface control",
        parameters={
            "weight": {
                "type": "number",
                "description": "Crease weight 0-1 (default 1.0). 1 = fully sharp edge under subdivision.",
                "required": False,
            },
        },
    )
    def mesh_crease(weight: float = 1.0):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        weight = max(0.0, min(1.0, weight))
        obj = bpy.context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        selected_edges = [e for e in bm.edges if e.select]
        for e in selected_edges:
            e[bm.edges.layers.float.get("crease_edge") or bm.edges.layers.float.new("crease_edge")] = weight
        bmesh.update_edit_mesh(obj.data)
        return {"weight": weight, "creased_edges": len(selected_edges)}

    @registry.register(
        name="mesh_mark_sharp",
        description="Mark selected edges as sharp (for edge-split / auto-smooth)",
        parameters={
            "clear": {
                "type": "boolean",
                "description": "If true, clear sharp instead of marking (default false)",
                "required": False,
            },
        },
    )
    def mesh_mark_sharp(clear: bool = False):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.mesh.mark_sharp(clear=clear)
        return {"marked_sharp": not clear}

    @registry.register(
        name="mesh_mark_seam",
        description="Mark selected edges as UV seams for UV unwrapping",
        parameters={
            "clear": {
                "type": "boolean",
                "description": "If true, clear seam instead of marking (default false)",
                "required": False,
            },
        },
    )
    def mesh_mark_seam(clear: bool = False):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.mesh.mark_seam(clear=clear)
        return {"marked_seam": not clear}

    # ================================================================
    #  Symmetry (P1)
    # ================================================================

    @registry.register(
        name="mesh_symmetrize",
        description="Symmetrize the mesh along an axis, mirroring geometry from one side to the other",
        parameters={
            "direction": {
                "type": "string",
                "description": "Direction: POSITIVE_X, NEGATIVE_X, POSITIVE_Y, NEGATIVE_Y, POSITIVE_Z, NEGATIVE_Z (default POSITIVE_X)",
                "required": False,
            },
        },
    )
    def mesh_symmetrize(direction: str = "POSITIVE_X"):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.mesh.symmetrize(direction=direction.upper())
        obj = bpy.context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        return {
            "direction": direction.upper(),
            "vertices": len(bm.verts),
            "faces": len(bm.faces),
        }

    # ================================================================
    #  Face Operations (P2)
    # ================================================================

    @registry.register(
        name="mesh_poke",
        description="Poke selected faces (add a center vertex, triangulating the face)",
        parameters={},
    )
    def mesh_poke():
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.mesh.poke()
        obj = bpy.context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        return {"poked": True, "faces": len(bm.faces)}

    @registry.register(
        name="mesh_triangulate",
        description="Convert selected faces to triangles (quad to tri conversion)",
        parameters={
            "quad_method": {
                "type": "string",
                "description": "Quad method: BEAUTY, FIXED, FIXED_ALTERNATE, SHORTEST_DIAGONAL (default BEAUTY)",
                "required": False,
            },
        },
    )
    def mesh_triangulate(quad_method: str = "BEAUTY"):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.mesh.quads_convert_to_tris(quad_method=quad_method.upper())
        obj = bpy.context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        tris = sum(1 for f in bm.faces if len(f.verts) == 3)
        return {"triangulated": True, "triangles": tris}

    # ================================================================
    #  Cleanup Tools (P2)
    # ================================================================

    @registry.register(
        name="mesh_limited_dissolve",
        description="Dissolve geometry within a given angle limit (clean up edges/vertices)",
        parameters={
            "angle_limit": {
                "type": "number",
                "description": "Angle limit in radians (default 0.1745 = 10 degrees). Higher values dissolve more.",
                "required": False,
            },
            "dissolve_type": {
                "type": "string",
                "description": "What to dissolve: VERTICES, EDGES, FACES, ALL (default ALL)",
                "required": False,
            },
        },
    )
    def mesh_limited_dissolve(angle_limit: float = 0.1745, dissolve_type: str = "ALL"):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        type_upper = dissolve_type.upper()
        if type_upper == "ALL":
            bpy.ops.mesh.dissolve_limited(angle_limit=angle_limit)
        elif type_upper == "VERTICES":
            bpy.ops.mesh.dissolve_verts(use_face_split=False)
        elif type_upper == "EDGES":
            bpy.ops.mesh.dissolve_edges(use_verts=True)
        elif type_upper == "FACES":
            bpy.ops.mesh.delete(type="DISSOLVE")
        else:
            raise ValueError(f"Unknown dissolve_type: {dissolve_type}. Use ALL, VERTICES, EDGES, or FACES.")
        return {"angle_limit": angle_limit, "dissolve_type": type_upper}

    @registry.register(
        name="mesh_delete_loose",
        description="Delete loose vertices, edges, or faces that are not connected to the main mesh",
        parameters={
            "type": {
                "type": "string",
                "description": "What to delete: VERT, EDGE, FACE, ALL (default ALL)",
                "required": False,
            },
        },
    )
    def mesh_delete_loose(type: str = "ALL"):
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        type_upper = type.upper()
        if type_upper == "ALL":
            bpy.ops.mesh.delete_loose(use_verts=True, use_edges=True, use_faces=True)
        elif type_upper == "VERT":
            bpy.ops.mesh.delete_loose(use_verts=True, use_edges=False, use_faces=False)
        elif type_upper == "EDGE":
            bpy.ops.mesh.delete_loose(use_verts=False, use_edges=True, use_faces=False)
        elif type_upper == "FACE":
            bpy.ops.mesh.delete_loose(use_verts=False, use_edges=False, use_faces=True)
        else:
            raise ValueError(f"Unknown type: {type}. Use ALL, VERT, EDGE, or FACE.")
        obj = bpy.context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        return {
            "type": type_upper,
            "remaining_vertices": len(bm.verts),
            "remaining_faces": len(bm.faces),
        }

    # ================================================================
    #  Normals Tools (P3)
    # ================================================================

    @registry.register(
        name="mesh_set_normals_from_faces",
        description="Set custom normals on selected faces from their face normals",
        parameters={},
    )
    def mesh_set_normals_from_faces():
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.mesh.set_normals_from_faces()
        return {"normals_set_from_faces": True}

    @registry.register(
        name="mesh_normals_smooth",
        description="Smooth normals of selected faces by averaging with adjacent face normals",
        parameters={},
    )
    def mesh_normals_smooth():
        if not bpy.context.mode.startswith("EDIT"):
            raise ValueError("Must be in edit mode. Use edit_mode_enter first.")
        bpy.ops.mesh.faces_shade_smooth()
        return {"normals_smoothed": True}
