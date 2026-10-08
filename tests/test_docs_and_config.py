"""Keep the guide, the examples, the skill and the integration templates consistent."""

import json
import re
import unittest

from support import ROOT
from iso5807_mcp import knowledge as kb
from iso5807_mcp.app import GUIDE_FILENAME, SERVER_NAME, create_server, guide_path
from iso5807_mcp.cli import COMMANDS
from iso5807_mcp.examples import EXAMPLES
from iso5807_mcp.mermaid import generate
from iso5807_mcp.model import load_flowchart
from iso5807_mcp.validator import validate

GUIDE = ROOT / "docs" / GUIDE_FILENAME
SKILL = ROOT / "SKILL.md"
RULE_ID = re.compile(r"\b(?:SYM|FLW|CON|TXT|STR|LAY|MOD)-\d\d\b")
DOCUMENTS = (SKILL, ROOT / "README.md",
             ROOT / "integrations/claude-ai-project/PROJECT_INSTRUCTIONS.md")


def frontmatter(text):
    """Minimal YAML subset: 'key: value' lines and '- item' lists."""
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if match is None:
        raise AssertionError("SKILL.md has no frontmatter")
    fields, key = {}, None
    for line in match.group(1).splitlines():
        item = re.match(r"\s+-\s+(.*)$", line)
        if item and key:
            value = item.group(1).strip()
            fields.setdefault(key, []).append(value[1:-1] if value[:1] == "'" else value)
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if value.strip():
            fields[key] = value.strip().strip('"')
    return fields


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
        for path in DOCUMENTS:
            unknown = set(RULE_ID.findall(path.read_text(encoding="utf-8"))) - set(kb.RULES_BY_ID)
            self.assertEqual(unknown, set(), path.name)

    def test_tool_names_referenced_in_documents_exist(self):
        tools = set(create_server().tools)
        pattern = re.compile(r"\b(iso5807_\w+|validate_\w+|analyze_\w+|generate_\w+)\b")
        for path in DOCUMENTS:
            for name in set(pattern.findall(path.read_text(encoding="utf-8"))):
                if not name.startswith("iso5807_mcp"):
                    self.assertIn(name, tools, f"{path.name} mentions unknown tool {name}")


class ExamplesTest(unittest.TestCase):
    def test_example_files_match_the_package(self):
        for name, data in EXAMPLES.items():
            on_disk = json.loads((ROOT / "examples" / f"{name}.json").read_text(encoding="utf-8"))
            self.assertEqual(on_disk, data, name)


class SkillTest(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")
        self.fields = frontmatter(self.text)

    def test_frontmatter(self):
        self.assertEqual(self.fields["name"], "flowchart_rules")
        self.assertLess(len(self.fields["description"]), 1024)
        self.assertIn("ISO 5807", self.fields["description"])
        self.assertTrue(self.fields["argument-hint"])
        allowed = self.fields["allowed-tools"]
        self.assertIn('Bash(python3 "${CLAUDE_SKILL_DIR}/mcp_server/server.py" *)', allowed)
        self.assertIn(f"mcp__{SERVER_NAME}__*", allowed)
        self.assertIn("Edit(flowcharts/**)", allowed)
        folder = f".claude/skills/{self.fields['name']}/mcp_server/server.py"
        for rule in allowed:
            if rule.startswith("Bash("):
                self.assertTrue("${CLAUDE_SKILL_DIR}/mcp_server/server.py" in rule
                                or folder in rule, rule)

    def test_body(self):
        self.assertIn("$ARGUMENTS", self.text)
        self.assertLess(self.text.count("\n"), 500, "keep SKILL.md under 500 lines")
        for match in re.finditer(r"\$\{CLAUDE_SKILL_DIR\}/([\w./-]+)", self.text):
            self.assertTrue((ROOT / match.group(1)).exists(), match.group(1))

    def test_commands_exist(self):
        used = set(re.findall(r"server\.py\"? (\w[\w-]*)", self.text))
        used |= set(re.findall(r"`(validate|analyze|mermaid|check-mermaid|check)`", self.text))
        self.assertIn("check", used)
        self.assertEqual(used - set(COMMANDS), set())

    def test_json_example_is_conformant(self):
        block = re.search(r"```json\n(.*?)```", self.text, re.S).group(1)
        report = validate(load_flowchart(block))
        self.assertTrue(report["valid"], report["findings"])
        self.assertEqual(report["summary"]["warnings"], 0, report["findings"])

    def test_no_nested_claude_configuration(self):
        # Inside .claude/skills/flowchart_rules/ Claude Code would load these as extra
        # instructions (CLAUDE.md) or as a second skill (.claude/skills/...).
        self.assertFalse((ROOT / ".claude").exists())
        self.assertFalse((ROOT / ".mcp.json").exists())
        stray = [p for p in ROOT.rglob("CLAUDE.md") if ".git" not in p.parts]
        self.assertEqual(stray, [])
        nested_skills = [p for p in ROOT.rglob("SKILL.md")
                         if ".git" not in p.parts and p != SKILL]
        self.assertEqual(nested_skills, [])


class IntegrationTemplateTest(unittest.TestCase):
    def test_project_mcp_template(self):
        config = json.loads((ROOT / "integrations/claude-code/project.mcp.json")
                            .read_text(encoding="utf-8"))
        server = config["mcpServers"][SERVER_NAME]
        self.assertEqual(server["type"], "stdio")
        self.assertEqual(server["args"], [
            "${CLAUDE_PROJECT_DIR:-.}/.claude/skills/flowchart_rules/mcp_server/server.py"])

    def test_project_settings_template(self):
        settings = json.loads((ROOT / "integrations/claude-code/project-settings.json")
                              .read_text(encoding="utf-8"))
        self.assertIn(SERVER_NAME, settings["enabledMcpjsonServers"])
        self.assertEqual(settings["permissions"]["allow"], [f"mcp__{SERVER_NAME}__*"])

    def test_claude_desktop_config(self):
        config = json.loads((ROOT / "integrations/claude-desktop/claude_desktop_config.json")
                            .read_text(encoding="utf-8"))
        self.assertTrue(config["mcpServers"][SERVER_NAME]["args"][0].endswith(
            "mcp_server/server.py"))


if __name__ == "__main__":
    unittest.main()
