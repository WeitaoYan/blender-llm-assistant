import bpy # type: ignore


def register_tools(registry):
    @registry.register(
        name="set_material",
        description="Set material properties on an object",
        parameters={
            "target": {
                "type": "string",
                "description": "Name of the object",
                "required": True,
            },
            "color": {
                "type": "array",
                "description": "RGBA color [r, g, b, a] with values 0-1",
                "items": {"type": "number"},
                "required": False,
            },
            "metallic": {
                "type": "number",
                "description": "Metallic value (0-1)",
                "required": False,
            },
            "roughness": {
                "type": "number",
                "description": "Roughness value (0-1)",
                "required": False,
            },
            "material_name": {
                "type": "string",
                "description": "Custom material name",
                "required": False,
            },
        },
    )
    def set_material(target: str, color=None, metallic=None, roughness=None, material_name=None):
        obj = bpy.data.objects.get(target)
        if obj is None:
            raise ValueError(f"Object '{target}' not found")
        if material_name is None:
            material_name = f"Mat_{target}"

        mat = bpy.data.materials.get(material_name)
        if mat is None:
            mat = bpy.data.materials.new(name=material_name)
            mat.use_nodes = True

        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)

        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        principled = None
        for node in nodes:
            if node.type == "BSDF_PRINCIPLED":
                principled = node
                break

        if principled is None:
            principled = nodes.new(type="ShaderNodeBsdfPrincipled")

        if color is not None:
            if len(color) == 3:
                color = list(color) + [1.0]
            principled.inputs["Base Color"].default_value = color

        if metallic is not None:
            principled.inputs["Metallic"].default_value = metallic

        if roughness is not None:
            principled.inputs["Roughness"].default_value = roughness

        return {
            "object": target,
            "material": material_name,
            "color": color,
            "metallic": metallic,
            "roughness": roughness,
        }
