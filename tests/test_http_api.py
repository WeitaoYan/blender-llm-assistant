"""Comprehensive HTTP API tests for Blender LLM Assistant addon.

Requires Blender to be running with the addon active on port 15800.

Usage:
    blender --background --python-expr "
    import sys; sys.path.insert(0, 'addon')
    from addon import register; register()
    "
    # Then manually click Start HTTP Server in Blender UI panel,
    # or run pytest from another terminal:
    pytest tests/test_http_api.py -v
"""

import json
import time
import httpx
import pytest
from typing import Any

pytestmark = pytest.mark.blender

BLENDER_URL = "http://127.0.0.1:15800"
TOOL_TIMEOUT = 60.0
_INTERVAL = 0.5  # seconds between tool calls to avoid overwhelming Blender


# ─── Helpers ────────────────────────────────────────────────────────────────


def call_tool(client: httpx.Client, tool: str, params: dict | None = None) -> dict:
    """Call a tool via HTTP SSE endpoint and return the result."""
    time.sleep(_INTERVAL)
    for attempt in range(2):
        try:
            resp = client.post(
                f"{BLENDER_URL}/api/tools/call",
                json={"tool": tool, "params": params or {}},
            )
            assert resp.status_code == 202, f"POST /api/tools/call {tool} failed: {resp.text}"
            data = resp.json()
            task_id = data["task_id"]

            time.sleep(0.1)
            sse_resp = client.get(f"{BLENDER_URL}/api/sse/{task_id}")
            return _parse_sse(sse_resp.text)
        except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError):
            if attempt == 0:
                time.sleep(2.0)
                continue
            raise


def _parse_sse(text: str) -> dict:
    """Parse SSE text and return the final result."""
    result = None
    error = None
    for line in text.strip().split("\n"):
        if line.startswith("data: "):
            data = json.loads(line[6:])
            if "result" in data:
                result = data["result"]
            if "error" in data:
                error = data["error"]
    if error:
        raise RuntimeError(error)
    if result is not None:
        return result
    # Return raw events if no structured result/error found
    events = []
    for line in text.strip().split("\n"):
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return {"events": events}


def tool_names() -> list[str]:
    """Fetch tool list from server."""
    resp = httpx.get(f"{BLENDER_URL}/api/tools/list", timeout=5)
    resp.raise_for_status()
    return [t["name"] for t in resp.json()["tools"]]


def run_python(client: httpx.Client, code: str) -> Any:
    """Run arbitrary Python in Blender sandbox and return result."""
    result = call_tool(client, "execute_python", {"code": code})
    return result.get("result")


# ─── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    limits = httpx.Limits(max_keepalive_connections=0, max_connections=10)
    with httpx.Client(base_url=BLENDER_URL, timeout=TOOL_TIMEOUT, limits=limits) as c:
        yield c


_cube_counter = 0

@pytest.fixture(scope="module")
def test_cube(client) -> str:
    """Create a fresh named test cube unique per module run."""
    global _cube_counter
    _cube_counter += 1
    name = f"TestCube_{_cube_counter}"
    result = call_tool(client, "create_object", {
        "type": "cube", "name": name, "location": [0, 0, 0],
    })
    name = result["name"]
    yield name
    for suffix in ["", "_dup.001", "_bool.001", "_joined.001"]:
        try:
            call_tool(client, "delete_object", {"name": f"{name}{suffix}"})
        except Exception:
            pass


@pytest.fixture
def test_sphere(client) -> str:
    """Create a test sphere for operations needing two objects."""
    result = call_tool(client, "create_object", {
        "type": "sphere", "name": "TestSphere_API",
        "location": [5, 0, 0],
    })
    name = result["name"]
    yield name
    try:
        call_tool(client, "delete_object", {"name": name})
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════
#  Health & Meta
# ══════════════════════════════════════════════════════════════════════════

class TestHealth:
    def test_health_endpoint(self, client):
        resp = client.get(f"{BLENDER_URL}/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_list_tools(self, client):
        resp = client.get(f"{BLENDER_URL}/api/tools/list")
        assert resp.status_code == 200
        tools = resp.json()["tools"]
        assert isinstance(tools, list)
        assert len(tools) > 0
        names = [t["name"] for t in tools]
        # Spot-check core tools
        for required in ["create_object", "select_object", "delete_object",
                         "set_material", "get_scene_info", "execute_python",
                         "edit_mode_enter", "mesh_extrude", "mesh_merge"]:
            assert required in names, f"Missing required tool: {required}"

    def test_scene_info(self, client):
        resp = client.get(f"{BLENDER_URL}/api/scene/info")
        assert resp.status_code == 200
        data = resp.json()
        assert "objects" in data
        assert "scene_name" in data

    def test_screenshot(self, client):
        resp = client.post(f"{BLENDER_URL}/api/scene/screenshot")
        assert resp.status_code == 200
        data = resp.json()
        assert "image" in data
        assert data["format"] == "png"


# ══════════════════════════════════════════════════════════════════════════
#  Object Operations
# ══════════════════════════════════════════════════════════════════════════

class TestObjectOps:
    def test_create_object(self, client):
        result = call_tool(client, "create_object", {
            "type": "cube", "name": "TestCreate",
            "location": [1, 2, 3], "rotation": [0, 0, 0.5], "scale": [2, 2, 2],
        })
        assert result["name"] == "TestCreate"
        assert result["type"] == "cube"
        assert result["location"] == [1, 2, 3]
        call_tool(client, "delete_object", {"name": "TestCreate"})

    def test_create_all_types(self, client):
        types = ["cube", "sphere", "cylinder", "cone", "torus", "ico_sphere"]
        for i, t in enumerate(types):
            result = call_tool(client, "create_object", {
                "type": t, "name": f"TestType_{t}", "location": [i * 3, 0, 0],
            })
            assert result["type"] == t
            call_tool(client, "delete_object", {"name": f"TestType_{t}"})

    def test_select_object(self, client, test_cube):
        result = call_tool(client, "select_object", {"name": test_cube})
        assert result["selected"] == test_cube

    def test_select_object_not_found(self, client):
        with pytest.raises(RuntimeError, match="not found"):
            call_tool(client, "select_object", {"name": "NonExistentObj"})

    def test_transform_object(self, client, test_cube):
        result = call_tool(client, "transform_object", {
            "name": test_cube,
            "location": [10, 20, 30],
            "rotation": [0.1, 0.2, 0.3],
            "scale": [3, 3, 3],
        })
        assert result["location"] == [10, 20, 30]

    def test_transform_partial(self, client, test_cube):
        result = call_tool(client, "transform_object", {
            "name": test_cube, "location": [0, 0, 0],
        })
        assert result["location"] == [0, 0, 0]

    def test_duplicate_object(self, client, test_cube):
        result = call_tool(client, "duplicate_object", {
            "name": test_cube, "offset": [3, 0, 0],
        })
        assert result["original"] == test_cube
        dup_name = result["duplicate"]
        call_tool(client, "delete_object", {"name": dup_name})

    def test_duplicate_default_offset(self, client, test_cube):
        result = call_tool(client, "duplicate_object", {"name": test_cube})
        dup_name = result["duplicate"]
        call_tool(client, "delete_object", {"name": dup_name})

    def test_delete_object(self, client):
        call_tool(client, "create_object", {
            "type": "cube", "name": "ToDelete",
        })
        result = call_tool(client, "delete_object", {"name": "ToDelete"})
        assert result["deleted"] == "ToDelete"

    def test_delete_not_found(self, client):
        with pytest.raises(RuntimeError, match="not found"):
            call_tool(client, "delete_object", {"name": "AlreadyGone"})


# ══════════════════════════════════════════════════════════════════════════
#  Material
# ══════════════════════════════════════════════════════════════════════════

class TestMaterial:
    def test_set_material(self, client, test_cube):
        result = call_tool(client, "set_material", {
            "object": test_cube,
            "color": [0.8, 0.1, 0.1, 1.0],
            "metallic": 0.5,
            "roughness": 0.3,
            "material_name": "TestRedMetal",
        })
        assert result["material"] == "TestRedMetal"
        assert result["metallic"] == 0.5

    def test_set_material_default_name(self, client, test_cube):
        result = call_tool(client, "set_material", {
            "object": test_cube, "color": [1, 1, 1],
        })
        assert "Mat_" in result["material"]

    def test_set_material_not_found(self, client):
        with pytest.raises(RuntimeError, match="not found"):
            call_tool(client, "set_material", {
                "object": "NonExistentMatObj",
            })


# ══════════════════════════════════════════════════════════════════════════
#  Scene / Python Execution
# ══════════════════════════════════════════════════════════════════════════

class TestScene:
    def test_get_scene_info(self, client, test_cube):
        result = call_tool(client, "get_scene_info")
        assert "objects" in result
        assert len(result["objects"]) > 0
        names = [o["name"] for o in result["objects"]]
        assert test_cube in names

    def test_execute_python_simple(self, client):
        result = call_tool(client, "execute_python", {
            "code": "result = 42",
        })
        assert result["executed"] is True
        assert result["result"] == 42

    def test_execute_python_math(self, client):
        result = call_tool(client, "execute_python", {
            "code": (
                "import math\n"
                "vals = [math.sqrt(i) for i in range(10)]\n"
                "result = sum(vals)"
            ),
        })
        assert result["executed"] is True
        assert isinstance(result["result"], float)

    def test_execute_python_sandbox_blocked_import(self, client):
        with pytest.raises(RuntimeError, match="Import of.*os.*not allowed"):
            call_tool(client, "execute_python", {
                "code": "import os; result = os.listdir('.')",
            })

    def test_execute_python_sandbox_blocked_open(self, client):
        with pytest.raises(RuntimeError, match="open|not found|NameError"):
            call_tool(client, "execute_python", {
                "code": "result = open('/etc/passwd').read()",
            })

    def test_execute_python_bpy_access(self, client, test_cube):
        result = call_tool(client, "execute_python", {
            "code": f"obj = D.objects.get('{test_cube}'); result = obj.name if obj else None",
        })
        assert result["result"] == test_cube


# ══════════════════════════════════════════════════════════════════════════
#  Modifiers & Boolean
# ══════════════════════════════════════════════════════════════════════════

class TestModifiers:
    def test_add_modifier_subsurf(self, client, test_cube):
        result = call_tool(client, "add_modifier", {
            "object": test_cube, "type": "subsurf",
            "params": {"levels": 2},
        })
        assert "subsurf" in result["modifier"]

    def test_add_modifier_mirror(self, client, test_cube):
        result = call_tool(client, "add_modifier", {
            "object": test_cube, "type": "mirror",
        })
        assert "mirror" in result["modifier"]

    def test_add_modifier_bevel(self, client, test_cube):
        result = call_tool(client, "add_modifier", {
            "object": test_cube, "type": "bevel",
            "params": {"width": 0.05, "segments": 2},
        })
        assert "bevel" in result["modifier"]

    def test_add_modifier_array(self, client, test_cube):
        result = call_tool(client, "add_modifier", {
            "object": test_cube, "type": "array",
            "params": {"count": 5},
        })
        assert "array" in result["modifier"]

    def test_add_modifier_solidify(self, client, test_cube):
        result = call_tool(client, "add_modifier", {
            "object": test_cube, "type": "solidify",
            "params": {"thickness": 0.1},
        })
        assert "solidify" in result["modifier"]

    def test_boolean_operation(self, client, test_cube, test_sphere):
        result = call_tool(client, "boolean_operation", {
            "object_a": test_cube,
            "object_b": test_sphere,
            "operation": "difference",
        })
        assert result["result"] == test_cube


# ══════════════════════════════════════════════════════════════════════════
#  Edit Mode Control
# ══════════════════════════════════════════════════════════════════════════

class TestEditMode:
    def test_edit_mode_enter(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        result = call_tool(client, "edit_mode_enter", {"object": test_cube})
        assert result["mode"] == "EDIT"
        call_tool(client, "edit_mode_exit")

    def test_edit_mode_exit(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        result = call_tool(client, "edit_mode_exit")
        assert result["mode"] == "OBJECT"

    def test_get_mode(self, client):
        result = call_tool(client, "get_mode")
        assert "mode" in result

    # ── Mesh Selection ──

    def test_mesh_select_all(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        result = call_tool(client, "mesh_select_all", {"action": "SELECT"})
        assert result["action"] == "SELECT"
        call_tool(client, "mesh_select_all", {"action": "DESELECT"})
        call_tool(client, "mesh_select_all", {"action": "INVERT"})
        call_tool(client, "edit_mode_exit")

    def test_mesh_select_by_type(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        for sel_type in ["VERT", "EDGE", "FACE"]:
            result = call_tool(client, "mesh_select_by_type", {"type": sel_type})
            assert result["selection_mode"] == sel_type
        call_tool(client, "edit_mode_exit")

    def test_mesh_select_loop(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "EDGE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_select_loop")
        assert "edge_loop" in result["selected"]
        call_tool(client, "edit_mode_exit")

    def test_mesh_select_ring(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "EDGE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_select_ring")
        assert "edge_ring" in result["selected"]
        call_tool(client, "edit_mode_exit")

    def test_mesh_select_more_less(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "FACE"})
        # Select one face
        run_python(client, (
            "C = bpy.context\n"
            "bm = bmesh.from_edit_mesh(C.active_object.data)\n"
            "bm.faces.ensure_lookup_table()\n"
            "bm.faces[0].select = True\n"
            "bmesh.update_edit_mesh(C.active_object.data)\n"
            "result = True"
        ))
        result = call_tool(client, "mesh_select_more")
        assert "grow" in result["action"]
        result = call_tool(client, "mesh_select_less")
        assert "shrink" in result["action"]
        call_tool(client, "edit_mode_exit")

    def test_mesh_select_by_axis(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "VERT"})
        result = call_tool(client, "mesh_select_by_axis", {
            "axis": "X", "sign": "POSITIVE",
        })
        assert result["axis"] == "X"
        call_tool(client, "edit_mode_exit")

    # ── Geometry Operations ──

    def test_mesh_extrude(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "FACE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_extrude", {
            "offset_z": 1.0, "individual": False,
        })
        assert result["offset"] == [0, 0, 1.0]
        call_tool(client, "edit_mode_exit")

    def test_mesh_inset(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "FACE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_inset", {
            "thickness": 0.2, "depth": 0.0, "individual": False,
        })
        assert result["thickness"] == 0.2
        call_tool(client, "edit_mode_exit")

    def test_mesh_bevel(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "EDGE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_bevel", {
            "width": 0.1, "segments": 2, "affect": "EDGES",
        })
        assert result["affect"] == "EDGES"
        call_tool(client, "edit_mode_exit")

    def test_mesh_loop_cut(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        result = call_tool(client, "mesh_loop_cut", {
            "count": 2, "object": test_cube,
        })
        assert result["cuts"] == 2
        call_tool(client, "edit_mode_exit")

    def test_mesh_bisect(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        result = call_tool(client, "mesh_bisect", {
            "plane_co": [0, 0, 0],
            "plane_no": [0, 1, 0],
            "clear_inner": False, "clear_outer": False, "fill": True,
        })
        assert result["plane_co"] == [0, 0, 0]
        call_tool(client, "edit_mode_exit")

    def test_mesh_knife(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        result = call_tool(client, "mesh_knife", {
            "points": [[-1, -1, 0], [1, 1, 0]],
        })
        assert result["cut_points"] == 2
        call_tool(client, "edit_mode_exit")

    def test_mesh_merge_by_distance(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "VERT"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_merge", {
            "method": "BY_DISTANCE", "distance": 0.01,
        })
        assert result["method"] == "BY_DISTANCE"
        call_tool(client, "edit_mode_exit")

    def test_mesh_merge_at_center(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "VERT"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_merge", {"method": "AT_CENTER"})
        assert result["method"] == "AT_CENTER"
        call_tool(client, "edit_mode_exit")

    def test_mesh_delete(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "FACE"})
        # Select first face if it exists, otherwise all faces
        run_python(client, (
            "bm = bmesh.from_edit_mesh(C.active_object.data)\n"
            "bm.faces.ensure_lookup_table()\n"
            "for f in bm.faces: f.select = False\n"
            "if bm.faces: bm.faces[0].select = True\n"
            "bmesh.update_edit_mesh(C.active_object.data)\n"
            "result = True"
        ))
        result = call_tool(client, "mesh_delete", {"type": "FACE"})
        assert "deleted_type" in result
        call_tool(client, "edit_mode_exit")

    def test_mesh_fill(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        # Ensure we have a face to remove; if cube was mangled, restore it
        run_python(client, (
            "bm = bmesh.from_edit_mesh(C.active_object.data)\n"
            "if len(bm.faces) == 0:\n"
            "    bmesh.ops.create_cube(bm, size=2)\n"
            "else:\n"
            "    for f in list(bm.faces)[:1]: bm.faces.remove(f)\n"
            "bmesh.update_edit_mesh(C.active_object.data)\n"
            "bm.faces.ensure_lookup_table()\n"
            "for e in bm.edges: e.select = bool(e.link_faces)\n"
            "result = True"
        ))
        result = call_tool(client, "mesh_fill")
        assert "filled" in result
        call_tool(client, "edit_mode_exit")

    def test_mesh_subdivide(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_subdivide", {
            "cuts": 2, "smoothness": 0.1,
        })
        assert result["cuts"] == 2
        call_tool(client, "edit_mode_exit")

    def test_mesh_split(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "FACE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_split", {"method": "SELECTION"})
        assert "SELECTION" in result["split_method"]
        call_tool(client, "edit_mode_exit")

    def test_mesh_separate(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "FACE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_separate")
        assert result["separated"] is True
        call_tool(client, "edit_mode_exit")
        # Cleanup separated objects
        for obj_name in result.get("new_objects", []):
            try:
                call_tool(client, "delete_object", {"name": obj_name})
            except Exception:
                pass

    def test_mesh_poke(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "FACE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_poke")
        assert result["poked"] is True
        call_tool(client, "edit_mode_exit")

    def test_mesh_triangulate(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "FACE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_triangulate")
        assert result["triangulated"] is True
        call_tool(client, "edit_mode_exit")

    def test_mesh_limited_dissolve(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_limited_dissolve", {
            "angle_limit": 0.05, "dissolve_type": "ALL",
        })
        assert "angle_limit" in result
        call_tool(client, "edit_mode_exit")

    def test_mesh_delete_loose(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_delete_loose", {"type": "ALL"})
        assert result["type"] == "ALL"
        call_tool(client, "edit_mode_exit")


# ══════════════════════════════════════════════════════════════════════════
#  Shading & Normals
# ══════════════════════════════════════════════════════════════════════════

class TestShading:
    def test_shade_smooth(self, client, test_cube):
        result = call_tool(client, "shade_smooth", {
            "object": test_cube,
        })
        assert result["shading"] == "smooth"

    def test_shade_flat(self, client, test_cube):
        result = call_tool(client, "shade_flat", {"object": test_cube})
        assert result["shading"] == "flat"

    def test_normals_recalculate(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        result = call_tool(client, "mesh_normals_recalculate", {"direction": "OUTSIDE"})
        assert result["direction"] == "OUTSIDE"
        call_tool(client, "edit_mode_exit")

    def test_flip_normals(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "FACE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_flip_normals")
        assert result["flipped"] is True
        call_tool(client, "edit_mode_exit")


# ══════════════════════════════════════════════════════════════════════════
#  Snapping, Cursor, Origin, Transform
# ══════════════════════════════════════════════════════════════════════════

class TestPrecision:
    def test_snap_config_enable(self, client):
        result = call_tool(client, "snap_config", {
            "enable": True, "snap_to": "VERTEX",
        })
        assert result["snap_enabled"] is True

    def test_snap_config_disable(self, client):
        result = call_tool(client, "snap_config", {"enable": False})
        assert result["snap_enabled"] is False

    def test_set_cursor(self, client):
        result = call_tool(client, "set_cursor", {"location": [1.5, -2.5, 3.0]})
        assert result["cursor"] == [1.5, -2.5, 3.0]

    def test_set_origin_to_geometry(self, client, test_cube):
        result = call_tool(client, "set_origin", {
            "object": test_cube, "origin_to": "GEOMETRY",
        })
        assert result["origin"] == "GEOMETRY"

    def test_apply_transform(self, client, test_cube):
        call_tool(client, "transform_object", {
            "name": test_cube, "scale": [2, 2, 2],
        })
        result = call_tool(client, "apply_transform", {
            "object": test_cube,
            "apply_location": True,
            "apply_rotation": True,
            "apply_scale": True,
        })
        assert result["object"] == test_cube
        # Reset
        call_tool(client, "transform_object", {
            "name": test_cube, "scale": [1, 1, 1],
        })
        call_tool(client, "apply_transform", {
            "object": test_cube,
        })

    def test_mesh_transform_selected(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "VERT"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_transform_selected", {
            "object": test_cube,
            "mode": "TRANSLATE",
            "value": [1, 0, 0],
            "orient_type": "GLOBAL",
        })
        assert result["mode"] == "TRANSLATE"
        call_tool(client, "edit_mode_exit")

    def test_mesh_vert_slide(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "VERT"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_vert_slide", {"value": 0.5})
        assert "slide_value" in result
        call_tool(client, "edit_mode_exit")

    def test_mesh_edge_slide(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "EDGE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_edge_slide", {"value": 0.5})
        assert "slide_value" in result
        call_tool(client, "edit_mode_exit")

    def test_proportional_edit(self, client):
        all_tools = tool_names()
        if "proportional_edit" not in all_tools:
            pytest.skip("proportional_edit tool not available")
        result = call_tool(client, "proportional_edit", {
            "enable": True, "falloff": "SMOOTH", "radius": 2.0,
        })
        assert result["proportional_enabled"] is True
        result = call_tool(client, "proportional_edit", {"enable": False})
        assert result["proportional_enabled"] is False


# ══════════════════════════════════════════════════════════════════════════
#  Vertex Groups & Shape Keys
# ══════════════════════════════════════════════════════════════════════════

class TestVertexGroups:
    def test_vertex_group_create(self, client, test_cube):
        result = call_tool(client, "vertex_group_create", {
            "object": test_cube, "group_name": "TestGroup",
        })
        assert result["vertex_group"] == "TestGroup"

    def test_vertex_group_assign(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "vertex_group_assign", {
            "object": test_cube, "group_name": "TestGroup", "weight": 0.8,
        })
        assert result["group"] == "TestGroup"
        call_tool(client, "edit_mode_exit")

    def test_vertex_group_remove(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "vertex_group_remove", {
            "object": test_cube, "group_name": "TestGroup",
        })
        assert result["group"] == "TestGroup"
        call_tool(client, "edit_mode_exit")


class TestShapeKeys:
    def test_shape_key_basis(self, client, test_cube):
        result = call_tool(client, "shape_key_create", {
            "object": test_cube, "key_name": "Basis",
        })
        assert "Basis" in result["shape_key"]

    def test_shape_key_relative(self, client, test_cube):
        result = call_tool(client, "shape_key_create", {
            "object": test_cube, "key_name": "Smile",
        })
        assert "Smile" in result["shape_key"]

    def test_shape_key_set_value(self, client, test_cube):
        result = call_tool(client, "shape_key_set_value", {
            "object": test_cube, "key_name": "Smile", "value": 0.5,
        })
        assert result["value"] == 0.5


# ══════════════════════════════════════════════════════════════════════════
#  Collections & Hierarchy
# ══════════════════════════════════════════════════════════════════════════

class TestCollections:
    def test_collection_create(self, client):
        result = call_tool(client, "collection_create", {"name": "TestCollection"})
        assert result["collection"] == "TestCollection"

    def test_collection_add_object(self, client, test_cube):
        result = call_tool(client, "collection_add_object", {
            "object": test_cube, "collection": "TestCollection",
        })
        assert result["object"] == test_cube
        assert result["collection"] == "TestCollection"

    def test_set_parent(self, client, test_cube, test_sphere):
        result = call_tool(client, "set_parent", {
            "child": test_sphere, "parent": test_cube,
        })
        assert result["child"] == test_sphere
        assert result["parent"] == test_cube
        # Clear parent
        call_tool(client, "set_parent", {"child": test_sphere})


# ══════════════════════════════════════════════════════════════════════════
#  Measurement & Analysis
# ══════════════════════════════════════════════════════════════════════════

class TestMeasurement:
    def test_measure_distance_objects(self, client, test_cube, test_sphere):
        call_tool(client, "transform_object", {
            "name": test_cube, "location": [0, 0, 0],
        })
        call_tool(client, "transform_object", {
            "name": test_sphere, "location": [3, 0, 0],
        })
        result = call_tool(client, "measure_distance", {
            "object_a": test_cube, "object_b": test_sphere,
        })
        assert result["distance"] == pytest.approx(3.0, abs=0.01)

    def test_measure_angle_objects(self, client, test_cube, test_sphere):
        call_tool(client, "transform_object", {
            "name": test_cube, "location": [-1, 0, 0],
        })
        call_tool(client, "transform_object", {
            "name": test_sphere, "location": [1, 0, 0],
        })
        result = call_tool(client, "measure_angle", {
            "object_a": test_cube,
            "object_b": test_sphere,
        })
        assert "angle_rad" in result

    def test_get_mesh_stats(self, client, test_cube):
        result = call_tool(client, "get_mesh_stats", {"object": test_cube})
        assert result["object"] == test_cube
        assert isinstance(result["vertices"], int)


# ══════════════════════════════════════════════════════════════════════════
#  Edge/Surface Marking
# ══════════════════════════════════════════════════════════════════════════

class TestMarking:
    def test_mesh_crease(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "EDGE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_crease", {"weight": 0.8})
        assert result["weight"] == 0.8
        call_tool(client, "edit_mode_exit")

    def test_mesh_mark_sharp(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "EDGE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_mark_sharp")
        assert result["marked_sharp"] is True
        # Clear
        result = call_tool(client, "mesh_mark_sharp", {"clear": True})
        assert result["marked_sharp"] is False
        call_tool(client, "edit_mode_exit")

    def test_mesh_mark_seam(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "EDGE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_mark_seam")
        assert result["marked_seam"] is True
        call_tool(client, "edit_mode_exit")

    def test_mesh_symmetrize(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        result = call_tool(client, "mesh_symmetrize", {"direction": "POSITIVE_X"})
        assert result["direction"] == "POSITIVE_X"
        call_tool(client, "edit_mode_exit")

    def test_set_normals_from_faces(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "FACE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_set_normals_from_faces")
        assert result["normals_set_from_faces"] is True
        call_tool(client, "edit_mode_exit")

    def test_normals_smooth(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "FACE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_normals_smooth")
        assert result["normals_smoothed"] is True
        call_tool(client, "edit_mode_exit")


# ══════════════════════════════════════════════════════════════════════════
#  Join / Bridge / Grid Fill
# ══════════════════════════════════════════════════════════════════════════

class TestAdvancedMesh:
    def test_mesh_join(self, client, test_cube, test_sphere):
        # Recreate sphere as it may have been consumed by boolean
        dup = call_tool(client, "duplicate_object", {"name": test_cube})
        dup_name = dup["duplicate"]
        result = call_tool(client, "mesh_join", {"objects": [test_cube, dup_name]})
        assert result["result"] is not None

    def test_mesh_grid_fill(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        # Create a hole then grid fill
        run_python(client, (
            "bm = bmesh.from_edit_mesh(C.active_object.data)\n"
            "bm.faces.ensure_lookup_table()\n"
            "for f in list(bm.faces)[:1]: bm.faces.remove(f)\n"
            "bmesh.update_edit_mesh(C.active_object.data)\n"
            "result = True"
        ))
        call_tool(client, "mesh_select_by_type", {"type": "EDGE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_grid_fill", {"span": 1})
        assert result["grid_fill"] is True
        call_tool(client, "edit_mode_exit")

    def test_mesh_bridge(self, client, test_cube):
        call_tool(client, "select_object", {"name": test_cube})
        call_tool(client, "edit_mode_enter", {"object": test_cube})
        call_tool(client, "mesh_select_by_type", {"type": "EDGE"})
        call_tool(client, "mesh_select_all", {"action": "SELECT"})
        result = call_tool(client, "mesh_bridge", {"segments": 2})
        assert result["bridged"] is True
        call_tool(client, "edit_mode_exit")


# ══════════════════════════════════════════════════════════════════════════
#  Error Handling
# ══════════════════════════════════════════════════════════════════════════

class TestErrorHandling:
    def test_invalid_tool_name(self, client):
        resp = client.post(f"{BLENDER_URL}/api/tools/call", json={
            "tool": "nonexistent_tool", "params": {},
        })
        assert resp.status_code == 202
        data = resp.json()
        task_id = data["task_id"]
        sse_resp = client.get(f"{BLENDER_URL}/api/sse/{task_id}")
        # _parse_sse raises RuntimeError on error events — catch and verify
        with pytest.raises(RuntimeError, match="not found"):
            _parse_sse(sse_resp.text)

    def test_invalid_parameters(self, client):
        with pytest.raises(RuntimeError):
            call_tool(client, "create_object", {"type": "invalid_type"})

    def test_tool_not_in_edit_mode(self, client):
        # Ensure we start in object mode
        try:
            call_tool(client, "edit_mode_exit")
        except Exception:
            pass
        with pytest.raises(RuntimeError, match="edit mode"):
            call_tool(client, "mesh_extrude", {"offset_z": 1})

    def test_sse_nonexistent_task(self, client):
        resp = client.get(f"{BLENDER_URL}/api/sse/nonexistent-task-id")
        assert resp.status_code == 404
