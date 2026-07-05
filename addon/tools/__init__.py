from . import object_ops, material, scene, mesh_edit, curve_ops, uv_ops


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register(self, name: str, description: str, parameters: dict):
        def decorator(func):
            self._tools[name] = {
                "func": func,
                "description": description,
                "parameters": parameters,
            }
            return func
        return decorator

    def get(self, name: str):
        info = self._tools.get(name)
        if info:
            return info["func"]
        return None

    def get_all(self):
        return {
            name: {
                "description": info["description"],
                "parameters": info["parameters"],
            }
            for name, info in self._tools.items()
        }


tool_registry = ToolRegistry()

object_ops.register_tools(tool_registry)
material.register_tools(tool_registry)
scene.register_tools(tool_registry)
mesh_edit.register_tools(tool_registry)
curve_ops.register_tools(tool_registry)
uv_ops.register_tools(tool_registry)
