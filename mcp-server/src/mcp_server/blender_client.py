import json
import logging

import httpx

logger = logging.getLogger(__name__)


class BlenderClient:
    def __init__(self, base_url: str = "http://127.0.0.1:15800"):
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=30.0)

    async def list_tools(self) -> dict:
        logger.debug("Listing tools from Blender")
        resp = await self._client.get(f"{self.base_url}/api/tools/list")
        resp.raise_for_status()
        return resp.json()

    async def call_tool(self, tool: str, params: dict) -> dict:
        logger.info(f"Calling Blender tool: {tool}({params})")
        resp = await self._client.post(
            f"{self.base_url}/api/tools/call",
            json={"tool": tool, "params": params},
        )
        resp.raise_for_status()
        data = resp.json()
        task_id = data["task_id"]
        logger.debug(f"Tool call queued, task_id={task_id}")

        sse_url = f"{self.base_url}/api/sse/{task_id}"
        async with self._client.stream("GET", sse_url) as sse_resp:
            sse_resp.raise_for_status()
            event_type = None
            event_data = ""

            async for line in sse_resp.aiter_lines():
                line = line.strip()
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    event_data = line[6:]
                elif line == "":
                    if event_type == "success":
                        logger.debug(f"Tool {tool} succeeded via SSE")
                        return json.loads(event_data)["result"]
                    elif event_type == "error":
                        error_msg = json.loads(event_data)["error"]
                        logger.error(f"Tool {tool} failed via SSE: {error_msg}")
                        raise RuntimeError(error_msg)
                    event_type = None
                    event_data = ""

        raise RuntimeError("SSE connection closed without result")

    async def get_scene_info(self) -> dict:
        resp = await self._client.get(f"{self.base_url}/api/scene/info")
        resp.raise_for_status()
        return resp.json()

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(f"{self.base_url}/health", timeout=2.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self):
        await self._client.aclose()
