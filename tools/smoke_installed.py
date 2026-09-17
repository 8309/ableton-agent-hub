"""Run with a clean installed wheel, no source PYTHONPATH and no Live calls."""
import asyncio
import json
from pathlib import Path
import tempfile

import ableton_bridge
from ableton_bridge.install import install_hub
from ableton_bridge.mcp_server import mcp
from mcp import Client


async def main():
    async with Client(mcp, raise_exceptions=True) as client:
        tools = await client.list_tools()
    names = [tool.name for tool in tools.tools]
    assert len(names) == 27, names
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "Hub"
        installed = install_hub(target)
        repeated = install_hub(target)
        assert installed["ok"] and installed["changed_file_count"] == 33
        assert repeated["ok"] and repeated["changed_file_count"] == 0
    print(json.dumps({"version": ableton_bridge.__version__, "module": ableton_bridge.__file__,
                      "tools": len(names), "installed_assets": 33, "idempotent": True,
                      "live_calls": 0}))


if __name__ == "__main__":
    asyncio.run(main())
