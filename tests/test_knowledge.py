import unittest

import support  # noqa: F401  (sets the import path)
from iso5807_mcp import knowledge as kb
from iso5807_mcp.mermaid import CLASSIC_SHAPES, EXTENDED_SHAPES


class KnowledgeBaseTest(unittest.TestCase):
    def test_rules_are_well_formed(self):
        ids = [r["id"] for r in kb.RULES]
        self.assertEqual(len(ids), len(set(ids)), "rule ids must be unique")
        for rule in kb.RULES:
            self.assertIn(rule["category"], kb.RULE_CATEGORIES, rule["id"])
            self.assertIn(rule["severity"], kb.SEVERITIES, rule["id"])
            self.assertIn(rule["basis"], ("ISO 5807", "Practice", "Schema"), rule["id"])
            self.assertIn(rule["check"], ("automatic", "heuristic", "manual"), rule["id"])
            for key in ("title", "rule", "rationale", "fix"):
                self.assertTrue(rule[key].strip(), f"{rule['id']} lacks {key}")
            self.assertRegex(rule["id"], r"^(SYM|FLW|CON|TXT|STR|LAY|MOD)-\d\d$")

    def test_every_node_type_has_a_symbol_and_mermaid_shapes(self):
        for node_type in kb.NODE_TYPES:
            self.assertIn(node_type, kb.SYMBOLS_BY_ID)
            self.assertIn(node_type, EXTENDED_SHAPES)
            self.assertIn(node_type, CLASSIC_SHAPES)
        for symbol in kb.SYMBOLS:
            for key in ("geometry", "meaning", "use_when", "do_not", "text_convention",
                        "flow_convention", "mermaid"):
                self.assertTrue(symbol[key], f"{symbol['id']} lacks {key}")

    def test_iso_symbol_set_is_complete(self):
        iso = {s["id"] for s in kb.SYMBOLS if s["standard"] == "ISO 5807"}
        self.assertEqual(len(iso), 25)  # 10 data + 7 process + 4 line + 4 special
        self.assertEqual(kb.SYMBOLS_BY_ID["off_page_connector"]["standard"], "ANSI X3.5 (legacy)")

    def test_type_aliases(self):
        self.assertEqual(kb.resolve_type("Start"), ("terminator", None))
        self.assertEqual(kb.resolve_type("I/O"), ("data", None))
        self.assertEqual(kb.resolve_type("diamond"), ("decision", None))
        self.assertEqual(kb.resolve_type("Predefined Process"), ("predefined_process", None))
        self.assertEqual(kb.resolve_type("loop-end"), ("loop_limit", "end"))
        self.assertEqual(kb.resolve_type("database"), ("direct_access_storage", None))
        self.assertEqual(kb.resolve_type("hexagon"), ("preparation", None))
        self.assertEqual(kb.resolve_type("swimlane"), (None, None))
        self.assertIn("decision", kb.suggest_types("decison"))

    def test_symbol_reference_filters(self):
        program = kb.symbol_reference(chart_type="program")
        ids = {s["id"] for s in program["symbols"]}
        self.assertIn("data", ids)
        self.assertNotIn("document", ids)
        self.assertEqual(kb.symbol_reference("rhombus")["symbol"]["id"], "decision")
        self.assertEqual(kb.symbol_reference("zigzag")["symbol"]["id"], "communication_link")
        with self.assertRaises(KeyError):
            kb.symbol_reference("cloud")

    def test_rules_reference(self):
        self.assertEqual(kb.rules_reference(rule_id="con-02")["rule"]["id"], "CON-02")
        connectors = kb.rules_reference(category="connectors")
        self.assertTrue(all(r["category"] == "connectors" for r in connectors["rules"]))
        iso = kb.rules_reference(basis="ISO")
        self.assertTrue(all(r["basis"] == "ISO 5807" for r in iso["rules"]))
        with self.assertRaises(KeyError):
            kb.rules_reference(rule_id="XYZ-99")


if __name__ == "__main__":
    unittest.main()
