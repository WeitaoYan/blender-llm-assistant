"""Shared fixtures and configuration for tests."""

import httpx
import pytest
from typing import AsyncIterator

BLENDER_URL = "http://127.0.0.1:15800"
TOOL_TIMEOUT = 60.0


def pytest_addoption(parser):
    parser.addoption(
        "--blender-url",
        default=BLENDER_URL,
        help=f"Blender HTTP API URL (default: {BLENDER_URL})",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "blender: mark test as requiring a running Blender instance",
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests marked with @pytest.mark.blender if Blender is unavailable."""
    if config.getoption("--blender-url") != BLENDER_URL:
        return
    try:
        import urllib.request
        resp = urllib.request.urlopen(f"{BLENDER_URL}/health", timeout=2)
        if resp.status == 200:
            return
    except Exception:
        pass

    # Blender not reachable — skip all blender-marked tests
    skip_blender = pytest.mark.skip(reason=f"Blender not reachable at {BLENDER_URL}")
    for item in items:
        if item.get_closest_marker("blender"):
            item.add_marker(skip_blender)


@pytest.fixture(scope="session")
def blender_url(request) -> str:
    return request.config.getoption("--blender-url")


@pytest.fixture(scope="session")
def http_client(blender_url) -> httpx.Client:
    with httpx.Client(base_url=blender_url, timeout=10.0) as client:
        yield client


@pytest.fixture(scope="session")
async def async_client(blender_url) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=blender_url, timeout=TOOL_TIMEOUT) as client:
        yield client
