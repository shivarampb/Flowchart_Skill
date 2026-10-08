import json
import unittest

import support  # noqa: F401
from iso5807_mcp.app import SERVER_NAME, create_server
from iso5807_mcp.examples import EXAMPLES
from iso5807_mcp.protocol import SUPPORTED_PROTOCOL_VERSIONS


class ProtocolTest(unittest.TestCase):
    def setUp(self):
        self.server = create_server()
        self.next_id = 0

    def request(self, method, params=None):
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            message["params"] = params
        response = self.server.handle(message)
        self.assertEqual(response["id"], self.next_id)
        return response

    def result(self, method, params=None):
        response = self.request(method, params)
        self.assertNotIn("error", response, response)
        return response["result"]

    def call(self, tool, arguments):
        return self.result("tools/call", {"name": tool, "arguments": arguments})

    # -- lifecycle -------------------------------------------------------------
    def test_initialize_negotiates_versions(self):
        for version in SUPPORTED_PROTOCOL_VERSIONS:
            result = self.result("initialize", {"protocolVersion": version, "capabilities": {},
                                                "clientInfo": {"name": "t", "version": "0"}})
            self.assertEqual(result["protocolVersion"], version)
        result = self.result("initialize", {"protocolVersion": "1999-01-01"})
        self.assertEqual(result["protocolVersion"], SUPPORTED_PROTOCOL_VERSIONS[0])
        self.assertEqual(result["serverInfo"]["name"], SERVER_NAME)
        self.assertEqual(set(result["capabilities"]), {"tools", "resources", "prompts"})
        self.assertIn("validate_flowchart", result["instructions"])

    def test_jsonrpc_edge_cases(self):
        self.assertEqual(self.result("ping"), {})
        notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self.assertIsNone(self.server.handle(notification))
        self.assertEqual(self.request("server/discover")["error"]["code"], -32601)
        self.assertEqual(self.request("nope/nope")["error"]["code"], -32601)
        self.assertEqual(self.server.handle({"id": 1, "method": "ping"})["error"]["code"], -32600)
        self.assertEqual(self.server.handle([])["error"]["code"], -32600)
        batch = self.server.handle([{"jsonrpc": "2.0", "id": "a", "method": "ping"},
                                    {"jsonrpc": "2.0", "method": "notifications/cancelled"}])
        self.assertEqual(batch, [{"jsonrpc": "2.0", "id": "a", "result": {}}])
        bad_params = self.server.handle({"jsonrpc": "2.0", "id": 9, "method": "tools/list",
                                         "params": [1]})
        self.assertEqual(bad_params["error"]["code"], -32602)
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "id": 5, "result": {}}))

    # -- tools -----------------------------------------------------------------
    def test_tools_list(self):
        tools = self.result("tools/list")["tools"]
        names = [t["name"] for t in tools]
        self.assertEqual(names, ["iso5807_symbol_reference", "iso5807_rules",
                                 "validate_flowchart", "analyze_flowchart", "generate_mermaid",
                                 "validate_mermaid"])
        for tool in tools:
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertTrue(tool["annotations"]["readOnlyHint"])
            self.assertTrue(tool["description"])

    def test_reference_tools(self):
        result = self.call("iso5807_symbol_reference", {"symbol": "diamond"})
        self.assertFalse(result["isError"])
        self.assertEqual(json.loads(result["content"][0]["text"])["symbol"]["id"], "decision")
        result = self.call("iso5807_symbol_reference", {"chart_type": "program_network"})
        ids = {s["id"] for s in json.loads(result["content"][0]["text"])["symbols"]}
        self.assertNotIn("decision", ids)
        result = self.call("iso5807_symbol_reference", {"symbol": "cloud"})
        self.assertTrue(result["isError"])
        result = self.call("iso5807_rules", {"category": "connectors"})
        self.assertEqual(json.loads(result["content"][0]["text"])["count"], 5)
        self.assertTrue(self.call("iso5807_rules", {"rule_id": "ZZZ-01"})["isError"])
        self.assertTrue(self.call("iso5807_rules", {"category": "colour"})["isError"])

    def test_validate_and_analyze_tools(self):
        result = self.call("validate_flowchart", {"flowchart": EXAMPLES["order-processing"]})
        self.assertTrue(json.loads(result["content"][0]["text"])["valid"])
        result = self.call("validate_flowchart", {"flowchart": json.dumps(EXAMPLES["flawed-login"]),
                                                  "strict": "false"})
        self.assertFalse(json.loads(result["content"][0]["text"])["valid"])
        result = self.call("validate_flowchart", EXAMPLES["order-processing"])  # unwrapped
        self.assertFalse(result["isError"])
        self.assertTrue(self.call("validate_flowchart", {})["isError"])
        self.assertTrue(self.call("validate_flowchart", {"flowchart": {"x": 1}})["isError"])
        self.assertTrue(self.call("validate_flowchart", {"flowchart": EXAMPLES["order-processing"],
                                                         "strict": "maybe"})["isError"])
        result = self.call("analyze_flowchart", {"flowchart": EXAMPLES["refund-request"]})
        self.assertEqual(json.loads(result["content"][0]["text"])["metrics"]["decisions"], 5)

    def test_generate_and_validate_mermaid(self):
        result = self.call("generate_mermaid", {"flowchart": EXAMPLES["order-processing"],
                                                "syntax": "classic"})
        text = result["content"][0]["text"]
        self.assertIn("```mermaid\nflowchart TB\n", text)
        summary = json.loads(result["content"][1]["text"])
        self.assertEqual(summary["min_mermaid_version"], "10.4.0")
        self.assertTrue(summary["valid"])
        result = self.call("generate_mermaid", {"flowchart": EXAMPLES["flawed-login"]})
        self.assertIn("NOT conformant", result["content"][0]["text"])
        self.assertTrue(self.call("generate_mermaid", {"flowchart": EXAMPLES["order-processing"],
                                                       "syntax": "svg"})["isError"])
        code = text.split("```mermaid\n", 1)[1].rsplit("```", 1)[0]
        result = self.call("validate_mermaid", {"mermaid": code})
        payload = json.loads(result["content"][0]["text"])
        self.assertTrue(payload["validation"]["valid"])
        self.assertEqual(len(payload["flowchart"]["nodes"]), 13)
        result = self.call("validate_mermaid", {"mermaid": "pie\n  \"a\": 1"})
        self.assertTrue(result["isError"])

    def test_unknown_tool_is_a_protocol_error(self):
        response = self.request("tools/call", {"name": "draw_uml", "arguments": {}})
        self.assertEqual(response["error"]["code"], -32602)

    # -- resources and prompts -------------------------------------------------
    def test_resources(self):
        resources = self.result("resources/list")["resources"]
        uris = [r["uri"] for r in resources]
        self.assertIn("iso5807://guide", uris)
        for resource in resources:
            content = self.result("resources/read", {"uri": resource["uri"]})["contents"][0]
            self.assertEqual(content["mimeType"], resource["mimeType"])
            if resource["mimeType"] != "text/markdown":
                json.loads(content["text"])
        guide = self.result("resources/read", {"uri": "iso5807://guide"})["contents"][0]["text"]
        self.assertIn("Part 2: Analysis of the flowcharting skill", guide)
        templates = self.result("resources/templates/list")["resourceTemplates"]
        self.assertEqual(len(templates), 2)
        rule = self.result("resources/read", {"uri": "iso5807://rules/STR-05"})
        self.assertEqual(json.loads(rule["contents"][0]["text"])["rule"]["id"], "STR-05")
        missing = self.request("resources/read", {"uri": "iso5807://rules/XXX-00"})
        self.assertEqual(missing["error"]["code"], -32002)

    def test_prompts(self):
        prompts = self.result("prompts/list")["prompts"]
        self.assertEqual([p["name"] for p in prompts], ["design_flowchart", "review_flowchart"])
        result = self.result("prompts/get", {"name": "design_flowchart",
                                             "arguments": {"process_description": "Hire staff",
                                                           "chart_type": "system"}})
        text = result["messages"][0]["content"]["text"]
        self.assertIn("Hire staff", text)
        self.assertIn("system flowchart", text)
        self.assertEqual(self.request("prompts/get", {"name": "review_flowchart"})["error"]["code"],
                         -32602)


if __name__ == "__main__":
    unittest.main()
