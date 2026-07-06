# Test Coverage Report

```
Blender version: 4.5
Server:          sync HTTP (stdlib http.server.ThreadingHTTPServer)
Test suite:      extensions/tests/test_http_api.py
Run date:        2026-07-06
```

## Summary

| Metric           | Value            |
| ---------------- | ---------------- |
| Registered tools | 68               |
| Test methods     | 127              |
| Pass / Fail      | **127 / 0**      |
| Tool coverage    | **100%** (68/68) |
| Run time         | ~7.8 min         |

## Module Breakdown

| Module                      | Tools | Tests | Coverage |
| --------------------------- | ----- | ----- | -------- |
| `addon/tools/object_ops.py` | 7     | 16    | ✅ 100%  |
| `addon/tools/mesh_edit.py`  | 58    | 73    | ✅ 100%  |
| `addon/tools/scene.py`      | 2     | 6     | ✅ 100%  |
| `addon/tools/material.py`   | 1     | 3     | ✅ 100%  |

## Endpoint Coverage

| Endpoint                     | Status         |
| ---------------------------- | -------------- |
| `GET /health`                | ✅             |
| `GET /api/tools/list`        | ✅             |
| `GET /api/scene/info`        | ✅             |
| `POST /api/scene/screenshot` | ✅             |
| `POST /api/tools/call`       | ✅ (all tests) |
| `GET /api/sse/{task_id}`     | ✅             |

## Tool-Level Coverage

### Object Ops (`object_ops.py`)

- `create_object` — test_create_object, test_create_all_types
- `select_object` — test_select_object, test_select_object_not_found
- `delete_object` — test_delete_object, test_delete_not_found
- `transform_object` — test_transform_object, test_transform_partial
- `duplicate_object` — test_duplicate_object, test_duplicate_default_offset
- `add_modifier` — test_add_modifier_subsurf / mirror / bevel / array / solidify
- `boolean_operation` — test_boolean_operation

### Material (`material.py`)

- `set_material` — test_set_material, test_set_material_default_name, test_set_material_not_found

### Scene / Python (`scene.py`)

- `get_scene_info` — test_get_scene_info
- `execute_python` — test_execute_python_simple / math / sandbox_blocked_import / sandbox_blocked_open / bpy_access

### Edit Mode (`mesh_edit.py`)

- `edit_mode_enter` — test_edit_mode_enter
- `edit_mode_exit` — test_edit_mode_exit
- `get_mode` — test_get_mode

### Mesh Selection (`mesh_edit.py`)

- `mesh_select_all` — test_mesh_select_all
- `mesh_select_by_type` — test_mesh_select_by_type
- `mesh_select_loop` — test_mesh_select_loop
- `mesh_select_ring` — test_mesh_select_ring
- `mesh_select_more` — test_mesh_select_more_less
- `mesh_select_less` — test_mesh_select_more_less
- `mesh_select_by_axis` — test_mesh_select_by_axis

### Geometry Ops (`mesh_edit.py`)

- `mesh_extrude` — test_mesh_extrude
- `mesh_inset` — test_mesh_inset
- `mesh_bevel` — test_mesh_bevel
- `mesh_loop_cut` — test_mesh_loop_cut
- `mesh_bisect` — test_mesh_bisect
- `mesh_knife` — test_mesh_knife
- `mesh_merge` — test_mesh_merge_by_distance, test_mesh_merge_at_center
- `mesh_delete` — test_mesh_delete
- `mesh_fill` — test_mesh_fill
- `mesh_subdivide` — test_mesh_subdivide
- `mesh_split` — test_mesh_split
- `mesh_separate` — test_mesh_separate
- `mesh_poke` — test_mesh_poke
- `mesh_triangulate` — test_mesh_triangulate
- `mesh_limited_dissolve` — test_mesh_limited_dissolve
- `mesh_delete_loose` — test_mesh_delete_loose

### Shading / Normals (`mesh_edit.py`)

- `shade_smooth` — test_shade_smooth
- `shade_flat` — test_shade_flat
- `mesh_normals_recalculate` — test_normals_recalculate
- `mesh_flip_normals` — test_flip_normals

### Precision / Transform (`mesh_edit.py`)

- `snap_config` — test_snap_config_enable, test_snap_config_disable
- `set_cursor` — test_set_cursor
- `set_origin` — test_set_origin_to_geometry
- `apply_transform` — test_apply_transform
- `mesh_transform_selected` — test_mesh_transform_selected
- `mesh_vert_slide` — test_mesh_vert_slide
- `mesh_edge_slide` — test_mesh_edge_slide
- `proportional_edit` — test_proportional_edit

### Vertex Groups (`mesh_edit.py`)

- `vertex_group_create` — test_vertex_group_create
- `vertex_group_assign` — test_vertex_group_assign
- `vertex_group_remove` — test_vertex_group_remove

### Shape Keys (`mesh_edit.py`)

- `shape_key_create` — test_shape_key_basis, test_shape_key_relative
- `shape_key_set_value` — test_shape_key_set_value

### Collections (`mesh_edit.py`)

- `collection_create` — test_collection_create
- `collection_add_object` — test_collection_add_object
- `set_parent` — test_set_parent

### Measurement (`mesh_edit.py`)

- `measure_distance` — test_measure_distance_objects
- `measure_angle` — test_measure_angle_objects
- `get_mesh_stats` — test_get_mesh_stats

### Edge Marking (`mesh_edit.py`)

- `mesh_crease` — test_mesh_crease
- `mesh_mark_sharp` — test_mesh_mark_sharp
- `mesh_mark_seam` — test_mesh_mark_seam
- `mesh_symmetrize` — test_mesh_symmetrize
- `mesh_set_normals_from_faces` — test_set_normals_from_faces
- `mesh_normals_smooth` — test_normals_smooth

### Advanced Mesh (`mesh_edit.py`)

- `mesh_join` — test_mesh_join
- `mesh_grid_fill` — test_mesh_grid_fill
- `mesh_bridge` — test_mesh_bridge

### Error Handling

- Invalid tool name — test_invalid_tool_name
- Invalid parameters — test_invalid_parameters
- Edit-mode gating — test_tool_not_in_edit_mode
- Nonexistent SSE task — test_sse_nonexistent_task

## Untested Tools

**None.** All 68 registered tools are covered.
