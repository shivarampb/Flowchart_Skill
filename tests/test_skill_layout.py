"""The package works when copied to <project>/.claude/skills/flowchart_rules/."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import ROOT
from iso5807_mcp.examples import EXAMPLES

SKILL_PATH = Path(".claude") / "skills" / "flowchart_rules"


class SkillLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.project = Path(cls.tmp.name) / "my project"  # a space, as on many Windows paths
        cls.skill_dir = cls.project / SKILL_PATH
        shutil.copytree(ROOT, cls.skill_dir,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def skill_command(self):
        """The check command exactly as SKILL.md shows it, with ${CLAUDE_SKILL_DIR} filled in."""
        text = (self.skill_dir / "SKILL.md").read_text(encoding="utf-8")
        command = re.search(r'```bash\n(python3 "\$\{CLAUDE_SKILL_DIR\}/[^\n]+) check FILE\n',
                            text).group(1)
        return command.replace("${CLAUDE_SKILL_DIR}", str(self.skill_dir))

    def run_shell(self, command):
        return subprocess.run(command, shell=True, cwd=self.project, capture_output=True,
                              text=True, timeout=60)

    def test_check_command_from_skill_md(self):
        if os.name == "nt":  # pragma: no cover - the quoting below is POSIX shell syntax
            self.skipTest("POSIX shell quoting")
        command = self.skill_command().replace("python3", f'"{sys.executable}"', 1)
        model = self.project / "flowcharts" / "refund.json"
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_text(json.dumps(EXAMPLES["refund-request"]), encoding="utf-8")
        result = self.run_shell(f"{command} check flowcharts/refund.json "
                                "--out flowcharts/refund.mmd")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ISO 5807 validation: 0 errors, 0 warnings", result.stdout)
        self.assertIn("```mermaid", result.stdout)
        self.assertTrue((self.project / "flowcharts" / "refund.mmd").read_text().startswith("---"))

    def test_mcp_template_launches_the_server(self):
        config = json.loads((self.skill_dir / "integrations/claude-code/project.mcp.json")
                            .read_text(encoding="utf-8"))
        server = config["mcpServers"]["iso5807-flowchart"]
        for project_dir in (str(self.project), None):  # env var set, or default "." (cwd)
            arg = server["args"][0].replace("${CLAUDE_PROJECT_DIR:-.}", project_dir or ".")
            messages = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2025-11-25", "capabilities": {}}},
                {"jsonrpc": "2.0", "id": 2, "method": "resources/read",
                 "params": {"uri": "iso5807://guide"}},
            ]
            stdin = "\n".join(json.dumps(m) for m in messages) + "\n"
            proc = subprocess.run([sys.executable, arg], input=stdin, cwd=self.project,
                                  capture_output=True, text=True, timeout=60)
            responses = [json.loads(line) for line in proc.stdout.splitlines()]
            self.assertEqual(responses[0]["result"]["serverInfo"]["name"], "iso5807-flowchart")
            guide = responses[1]["result"]["contents"][0]["text"]
            self.assertIn("Part 2: Analysis of the flowcharting skill", guide)


if __name__ == "__main__":
    unittest.main()
