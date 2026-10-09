import json
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from support import ROOT, SERVER_SCRIPT
from iso5807_mcp.app import create_server
from iso5807_mcp.transport import McpHttpServer

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "test", "version": "0"}}}


class StdioTest(unittest.TestCase):
    def test_session_over_stdio(self):
        messages = [
            INIT,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "generate_mermaid", "arguments": {"flowchart": {
                 "title": "Ünïcode ⚡ title",
                 "nodes": [{"id": "s", "type": "start", "text": "Start"},
                           {"id": "e", "type": "end", "text": "End"}],
                 "edges": [{"from": "s", "to": "e"}]}}}},
        ]
        stdin = "\n".join(json.dumps(m) for m in messages) + "\nnot json\n"
        proc = subprocess.run([sys.executable, str(SERVER_SCRIPT)], input=stdin.encode(),
                              capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        lines = proc.stdout.decode("ascii").splitlines()  # ASCII-only framing
        responses = [json.loads(line) for line in lines]
        self.assertEqual([r.get("id") for r in responses], [1, 2, 3, None])
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(len(responses[1]["result"]["tools"]), 6)
        self.assertIn("Ünïcode ⚡ title", responses[2]["result"]["content"][0]["text"])
        self.assertEqual(responses[3]["error"]["code"], -32700)


class HttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = McpHttpServer(create_server(), "127.0.0.1", 0, "/mcp",
                                  allowed_origins=["https://claude.ai"], auth_token=None)
        cls.secured = McpHttpServer(create_server(), "127.0.0.1", 0, "/secret-mcp",
                                    auth_token="s3cret")
        for server in (cls.httpd, cls.secured):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.secured_base = f"http://127.0.0.1:{cls.secured.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        for server in (cls.httpd, cls.secured):
            server.shutdown()
            server.server_close()

    def send(self, url, payload=None, method="POST", headers=None, raw=None):
        data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None
                                            else None)
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json, text/event-stream")
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read()
                return response.status, dict(response.headers), body
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read()

    def test_request_response(self):
        status, headers, body = self.send(self.base + "/mcp", INIT)
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        self.assertEqual(json.loads(body)["result"]["serverInfo"]["name"], "iso5807-flowchart")
        status, _, body = self.send(self.base + "/mcp",
                                    {"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual((status, body), (202, b""))

    def test_methods_paths_and_errors(self):
        self.assertEqual(self.send(self.base + "/mcp", method="GET")[0], 405)
        self.assertEqual(self.send(self.base + "/mcp", method="DELETE")[0], 405)
        status, _, body = self.send(self.base + "/healthz", method="GET")
        self.assertEqual((status, json.loads(body)["status"]), (200, "ok"))
        self.assertEqual(self.send(self.base + "/other", INIT)[0], 404)
        self.assertEqual(self.send(self.base + "/mcp", raw=b"{oops")[0], 400)

    def test_origin_checks_and_cors(self):
        status, _, _ = self.send(self.base + "/mcp", INIT, headers={"Origin": "https://evil.example"})
        self.assertEqual(status, 403)
        status, headers, _ = self.send(self.base + "/mcp", INIT,
                                       headers={"Origin": "http://localhost:6274"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "http://localhost:6274")
        status, headers, _ = self.send(self.base + "/mcp", method="OPTIONS",
                                       headers={"Origin": "https://claude.ai"})
        self.assertEqual(status, 204)
        self.assertIn("POST", headers["Access-Control-Allow-Methods"])

    def test_bearer_token(self):
        url = self.secured_base + "/secret-mcp"
        self.assertEqual(self.send(url, INIT)[0], 401)
        self.assertEqual(self.send(url, INIT, headers={"Authorization": "Bearer nope"})[0], 401)
        self.assertEqual(self.send(url, INIT, headers={"Authorization": "Bearer s3cret"})[0], 200)


class CliTest(unittest.TestCase):
    def run_cli(self, *args, stdin=None):
        return subprocess.run([sys.executable, str(SERVER_SCRIPT), *args], input=stdin,
                              capture_output=True, text=True, timeout=30, cwd=ROOT)

    def test_validate_and_analyze(self):
        ok = self.run_cli("validate", "examples/order-processing.json")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertTrue(json.loads(ok.stdout)["valid"])
        bad = self.run_cli("validate", "examples/flawed-login.json")
        self.assertEqual(bad.returncode, 1)
        refund = (ROOT / "examples/refund-request.json").read_text()
        analysis = self.run_cli("analyze", "-", stdin=refund)
        self.assertEqual(json.loads(analysis.stdout)["metrics"]["cyclomatic_complexity"], 6)
        missing = self.run_cli("validate", "examples/does-not-exist.json")
        self.assertEqual(missing.returncode, 2)

    def test_mermaid_commands(self):
        result = self.run_cli("mermaid", "examples/monthly-billing.json", "--classic")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith('%%{init: {"flowchart": {"curve": "step"}}}%%\n'
                                                  "flowchart TB\n"))
        check = self.run_cli("check-mermaid", "examples/informal-approval.mmd")
        self.assertEqual(check.returncode, 1)
        self.assertIn("SYM-01", check.stdout)

    def test_check_command(self):
        ok = self.run_cli("check", "examples/refund-request.json")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertTrue(ok.stdout.startswith("ISO 5807 validation: 0 errors, 0 warnings"))
        self.assertIn("Analysis: 5 decisions, cyclomatic complexity 6", ok.stdout)
        self.assertIn("```mermaid\n---\ntitle:", ok.stdout)
        bad = self.run_cli("check", "examples/informal-approval.mmd", "--classic")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("ERROR   SYM-01 [A]", bad.stdout)
        self.assertIn("Mermaid (classic syntax, needs Mermaid >= 10.4.0)", bad.stdout)
        as_json = self.run_cli("check", "-", "--json", "--chart-type", "system",
                               stdin=(ROOT / "examples/order-processing.json").read_text())
        payload = json.loads(as_json.stdout)
        self.assertEqual(payload["validation"]["chart_type"], "system")
        self.assertIn("flowchart TB", payload["mermaid"])

    def test_check_writes_only_mermaid_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sub" / "order.mmd"
            result = self.run_cli("check", "examples/order-processing.json", "--out", str(target))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(target.read_text(encoding="utf-8").startswith("---\ntitle:"))
            refused = self.run_cli("check", "examples/order-processing.json",
                                   "--out", str(Path(tmp) / "notes.txt"))
            self.assertEqual(refused.returncode, 2)
            self.assertFalse((Path(tmp) / "notes.txt").exists())

    def test_rules_command(self):
        listing = self.run_cli("rules")
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertEqual(len(set(re.findall(r"`([A-Z]{3}-\d\d)`", listing.stdout))), 52)
        one = self.run_cli("rules", "con-02")
        self.assertEqual(one.returncode, 0)
        self.assertIn("Rule: Every out-connector has exactly one in-connector", one.stdout)
        self.assertEqual(self.run_cli("rules", "XYZ-01").returncode, 2)
        category = self.run_cli("rules", "--category", "connectors")
        self.assertEqual(set(re.findall(r"`([A-Z]{3}-\d\d)`", category.stdout)),
                         {"CON-01", "CON-02", "CON-03", "CON-04", "CON-05"})

    def test_help_and_version(self):
        self.assertIn("--http", self.run_cli("--help").stdout)
        self.assertIn("1.0.0", self.run_cli("--version").stdout)
        self.assertIn("--out", self.run_cli("check", "--help").stdout)


if __name__ == "__main__":
    unittest.main()
