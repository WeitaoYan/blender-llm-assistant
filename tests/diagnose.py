"""Diagnose 6 test failures in blender-llm-assistant.

Usage:
    python tests/diagnose.py
"""

import json, time, httpx, sys

URL = "http://127.0.0.1:15800"
AUTH = {"Authorization": "Bearer f7b6f4b3602449f8a22b02de240a17d9"}


def tool(name, params=None):
    r = httpx.post(f"{URL}/api/tools/call", json={"tool": name, "params": params or {}},
                   headers=AUTH, timeout=10)
    assert r.status_code == 202, f"POST failed: {r.text}"
    task_id = r.json()["task_id"]
    time.sleep(0.3)
    sse = httpx.get(f"{URL}/api/sse/{task_id}", headers=AUTH, timeout=10).text
    result, error = None, None
    for line in sse.strip().split("\n"):
        if line.startswith("data: "):
            d = json.loads(line[6:])
            if "result" in d: result = d["result"]
            if "error" in d: error = d["error"]
    if error:
        raise RuntimeError(error)
    return result


def py(code):
    r = tool("execute_python", {"code": code})
    return r.get("result")


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ─── Create a clean cube ──────────────────────────────────────────────────
section("1. Setup: fresh cube")
cube = tool("create_object", {"type": "cube", "name": "DiagCube", "location": [0,0,0]})["name"]
print(f"Cube name: {cube}")

# ─── simulate align_vertices test exactly ────────────────────────────────
section("2. EXACT: align_vertices test sequence")
tool("select_object", {"name": cube})
tool("edit_mode_enter", {"target": cube})
tool("mesh_select_all", {"action": "SELECT"})
# Now call align_vertices like the test does
try:
    r = tool("align_vertices", {"target": cube, "axis": "Y"})
    print(f"align_vertices result: {r}")
except RuntimeError as e:
    print(f">>> align_vertices FAILED: {e}")

# ─── simulate select_similar test exactly ─────────────────────────────────
section("3. EXACT: select_similar test sequence")
tool("select_object", {"name": cube})
tool("edit_mode_enter", {"target": cube})
tool("mesh_select_by_type", {"type": "FACE"})
tool("mesh_select_all", {"action": "SELECT"})
try:
    r = tool("select_similar", {"type": "AREA", "threshold": 0.1})
    print(f"select_similar result: {r}")
except RuntimeError as e:
    print(f">>> select_similar FAILED: {e}")

# ─── simulate ALL 4 UV tests exactly ─────────────────────────────────────
section("4. EXACT: uv_unwrap SMART")
tool("edit_mode_exit")
try:
    r = tool("uv_unwrap", {"target": cube, "method": "SMART", "margin": 0.02})
    print(f"uv_unwrap SMART: {r}")
except RuntimeError as e:
    print(f">>> uv_unwrap SMART FAILED: {e}")

section("5. EXACT: uv_unwrap ANGLE_BASED")
try:
    r = tool("uv_unwrap", {"target": cube, "method": "ANGLE_BASED"})
    print(f"uv_unwrap ANGLE_BASED: {r}")
except RuntimeError as e:
    print(f">>> uv_unwrap ANGLE_BASED FAILED: {e}")

section("6. EXACT: uv_unwrap CUBE")
try:
    r = tool("uv_unwrap", {"target": cube, "method": "CUBE", "cube_size": 2.0})
    print(f"uv_unwrap CUBE: {r}")
except RuntimeError as e:
    print(f">>> uv_unwrap CUBE FAILED: {e}")

section("7. EXACT: uv_pack")
try:
    r = tool("uv_pack", {"target": cube, "margin": 0.01, "rotate": True})
    print(f"uv_pack: {r}")
except RuntimeError as e:
    print(f">>> uv_pack FAILED: {e}")

# ─── RETURN TO EDIT MODE, check cross-call BMesh ─────────────────────────
section("8. DEEP DIAG: bmesh selection across calls")
tool("select_object", {"name": cube})
tool("edit_mode_enter", {"target": cube})
tool("mesh_select_all", {"action": "SELECT"})
r = py(f"""
C = bpy.context
import bmesh
obj = bpy.data.objects.get("{cube}")
bm = bmesh.from_edit_mesh(obj.data)
result = {{
    "active_obj": C.active_object.name if C.active_object else None,
    "mode": C.mode,
    "obj_found": obj is not None,
    "bm_verts_sel": sum(1 for v in bm.verts if v.select),
    "window": C.window is not None,
    "area_type": C.area.type if C.area else None,
}}
""")
print(json.dumps(r, indent=2))
if r.get("bm_verts_sel", 0) == 0:
    print(">>> BMesh selection lost across calls!")
    if r.get("active_obj") != cube:
        print("    -> active_object mismatch")
else:
    print(">>> OK: BMesh selection persists cross-call")

# ─── context override enumeration ─────────────────────────────────────────
section("9. DEEP DIAG: which area types satisfy uv.smart_project poll?")
r = py(f"""
C = bpy.context
obj = bpy.data.objects.get("{cube}")
if obj.mode != "EDIT":
    bpy.ops.object.mode_set(mode="EDIT")
import bmesh
bm = bmesh.from_edit_mesh(obj.data)
for f in bm.faces: f.select = True
bm.select_flush_mode()

results = []
for w in C.window_manager.windows:
    for a in w.screen.areas:
        ctx = {{"window": w, "screen": w.screen, "area": a, "region": None}}
        for rr in a.regions:
            if rr.type == "WINDOW":
                ctx["region"] = rr
                break
        if not ctx["region"]:
            results.append("SKIP " + a.type + " (no WINDOW region)")
            continue
        try:
            with C.temp_override(**ctx):
                bpy.ops.uv.smart_project(angle_limit=66, island_margin=0.02, area_weight=0)
            results.append("OK   " + a.type)
        except Exception as e:
            msg = str(e).replace("'","")[:70]
            results.append("FAIL " + a.type + " -> " + msg)
result = {{"area_types": results}}
""")
for line in r.get("area_types", []):
    print(f"  {line}")

# ─── cleanup ──────────────────────────────────────────────────────────────
section("10. Cleanup")
tool("edit_mode_exit")
tool("delete_object", {"name": cube})
print(f"Deleted {cube}")
print("\nDone.")
