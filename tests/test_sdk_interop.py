"""Interoperability with the official MCP Python SDK client (skipped if it is not installed)."""

import asyncio
import json
import socket
import subprocess
import sys
import time
import unittest

from support import SERVER_SCRIPT
from iso5807_mcp.examples import EXAMPLES

try:
    from mcp import Client, StdioServerParameters  # MCP Python SDK >= 2
except ImportError:  # pragma: no cover - depends on the environment
    Client = None


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def exercise(target):
    async with Client(target) as client:
        tools = await client.list_tools()
        result = await client.call_tool("validate_flowchart",
                                        {"flowchart": EXAMPLES["order-processing"]})
        report = json.loads(result.content[0].text)
        bad = await client.call_tool("validate_flowchart", {"flowchart": {"oops": 1}})
        guide = await client.read_resource("iso5807://guide")
        prompt = await client.get_prompt("review_flowchart", {"flowchart": "flowchart TB\n a-->b"})
        return {
            "tools": sorted(t.name for t in tools.tools),
            "valid": report["valid"],
            "bad_is_error": bad.is_error,
            "guide": guide.contents[0].text[:60],
            "prompt": prompt.messages[0].content.text[:40],
        }


@unittest.skipIf(Client is None, "MCP Python SDK (>= 2) not installed")
class SdkInteropTest(unittest.TestCase):
    def check(self, outcome):
        self.assertEqual(len(outcome["tools"]), 6)
        self.assertTrue(outcome["valid"])
        self.assertTrue(outcome["bad_is_error"])
        self.assertIn("ANSI/ISO 5807", outcome["guide"])
        self.assertTrue(outcome["prompt"].startswith("Review the flowchart"))

    def test_stdio(self):
        params = StdioServerParameters(command=sys.executable, args=[str(SERVER_SCRIPT)])
        self.check(asyncio.run(exercise(params)))

    def test_streamable_http(self):
        port = free_port()
        proc = subprocess.Popen([sys.executable, str(SERVER_SCRIPT), "--http", "--port", str(port)],
                                stderr=subprocess.DEVNULL)
        try:
            deadline = time.time() + 10
            while time.time() < deadline:
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                    break
                except OSError:
                    time.sleep(0.1)
            self.check(asyncio.run(exercise(f"http://127.0.0.1:{port}/mcp")))
        finally:
            proc.terminate()
            proc.wait(10)


if __name__ == "__main__":
    unittest.main()
