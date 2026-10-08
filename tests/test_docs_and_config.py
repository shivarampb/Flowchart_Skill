"""Keep the guide, the examples and the Claude configuration consistent with the code."""

import json
import re
import unittest

from support import ROOT
from iso5807_mcp import knowledge as kb
from iso5807_mcp.app import GUIDE_FILENAME, SERVER_NAME, guide_path
from iso5807_mcp.examples import EXAMPLES
from iso5807_mcp.mermaid import generate
from iso5807_mcp.model import load_flowchart

GUIDE = ROOT / "docs" / GUIDE_FILENAME
RULE_ID = re.compile(r"\b(?:SYM|FLW|CON|TXT|STR|LAY|MOD)-\d\d\b")


class GuideTest(unittest.TestCase):
    def setUp(self):
        self.guide = GUIDE.read_text(encoding="utf-8")

    def test_every_rule_is_documented_and_no_unknown_ids(self):
        mentioned = set(RULE_ID.findall(self.guide))
        self.assertEqual(set(kb.RULES_BY_ID) - mentioned, set(), "rules missing from the guide")
        self.assertEqual(mentioned - set(kb.RULES_BY_ID), set(), "unknown rule ids in the guide")

    def test_every_iso_symbol_is_documented(self):
        for symbol in kb.SYMBOLS:
            if symbol["family"] != "line":
                self.assertIn(f"`{symbol['id']}`", self.guide, symbol["id"])

    def test_generated_example_is_current(self):
        match = re.search(r"<!-- BEGIN GENERATED: refund-request[^\n]*-->\n```mermaid\n(.*?)```\n"
                          r"<!-- END GENERATED: refund-request -->", self.guide, re.S)
        self.assertIsNotNone(match)
        code, _ = generate(load_flowchart(EXAMPLES["refund-request"]))
        self.assertEqual(match.group(1), code)

    def test_guide_is_served(self):
        self.assertEqual(guide_path(), GUIDE)

    def test_rule_ids_in_other_documents_exist(self):
        for path in (ROOT / "CLAUDE.md", ROOT / "README.md",
                     ROOT / ".claude/skills/iso5807-flowchart/SKILL.md",
                     ROOT / "integrations/claude-ai-project/PROJECT_INSTRUCTIONS.md"):
            unknown = set(RULE_ID.findall(path.read_text(encoding="utf-8"))) - set(kb.RULES_BY_ID)
            self.assertEqual(unknown, set(), path.name)


class ExamplesTest(unittest.TestCase):
    def test_example_files_match_the_package(self):
        for name, data in EXAMPLES.items():
            on_disk = json.loads((ROOT / "examples" / f"{name}.json").read_text(encoding="utf-8"))
            self.assertEqual(on_disk, data, name)


class ClaudeConfigTest(unittest.TestCase):
    def test_mcp_json(self):
        config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        server = config["mcpServers"][SERVER_NAME]
        self.assertEqual(server["type"], "stdio")
        script = server["args"][0].replace("${CLAUDE_PROJECT_DIR:-.}", str(ROOT))
        self.assertTrue((ROOT / script).is_file(), script)

    def test_settings_json(self):
        settings = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertIn(SERVER_NAME, settings["enabledMcpjsonServers"])
        self.assertIn(f"mcp__{SERVER_NAME}__*", settings["permissions"]["allow"])

    def test_skill_frontmatter(self):
        text = (ROOT / ".claude/skills/iso5807-flowchart/SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(match)
        fields = dict(line.split(":", 1) for line in match.group(1).splitlines())
        self.assertEqual(fields["name"].strip(), "iso5807-flowchart")
        self.assertLess(len(fields["description"]), 1024)
        self.assertEqual(fields["allowed-tools"].strip(), f"mcp__{SERVER_NAME}__*")
        self.assertIn("$ARGUMENTS", text)

    def test_claude_desktop_config(self):
        config = json.loads((ROOT / "integrations/claude-desktop/claude_desktop_config.json")
                            .read_text(encoding="utf-8"))
        self.assertTrue(config["mcpServers"][SERVER_NAME]["args"][0].endswith(
            "mcp_server/server.py"))

    def test_tool_names_referenced_in_docs_exist(self):
        from iso5807_mcp.app import create_server
        tools = set(create_server().tools)
        pattern = re.compile(r"\b(iso5807_\w+|validate_\w+|analyze_\w+|generate_\w+)\b")
        for path in (ROOT / "CLAUDE.md", ROOT / ".claude/skills/iso5807-flowchart/SKILL.md",
                     ROOT / "integrations/claude-ai-project/PROJECT_INSTRUCTIONS.md",
                     ROOT / "README.md"):
            for name in set(pattern.findall(path.read_text(encoding="utf-8"))):
                if name.startswith("iso5807_mcp"):
                    continue
                self.assertIn(name, tools, f"{path.name} mentions unknown tool {name}")


if __name__ == "__main__":
    unittest.main()
