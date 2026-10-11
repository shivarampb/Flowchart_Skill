"""Every rule the tools claim to check is probed with a violating and a conformant chart.

Each probe is a pair of flowcharts that differ only in the defect: the rule must fire on the
first (with its documented severity) and stay silent on the second. A rule marked
automatic, heuristic or partial in the knowledge base without a probe fails the suite, and
so does a rule marked manual (judgment) that the code reports after all.
"""

import re
import unittest
from pathlib import Path

from support import chart, edge, linear, node
from iso5807_mcp import knowledge as kb
from iso5807_mcp.analyzer import analyze
from iso5807_mcp.mermaid import generate, parse_mermaid
from iso5807_mcp.model import FlowchartInputError, load_flowchart
from iso5807_mcp.validator import validate


def findings(data, strict=True):
    fc = load_flowchart(data)
    return validate(fc, strict=strict)["findings"] + analyze(fc)["insights"]


def fired(data, rule_id, strict=True):
    """Severities with which ``rule_id`` fires on ``data`` (validator and analyzer).

    Analyzer advisories are the signal of heuristic rules; for checked rules they are review
    reminders that appear on conformant charts too (e.g. "confirm this loop terminates").
    """
    heuristic = kb.RULES_BY_ID[rule_id]["check"] == "heuristic"
    return {f["severity"] for f in findings(data, strict) if f.get("rule_id") == rule_id
            and (heuristic or f["severity"] != "advisory")}


def program(*middle, **extra):
    nodes, edges = linear(*middle)
    return chart(nodes, edges, **extra)


def decision_chart(labels=("Yes", "No"), targets=None, text="Stock >= quantity?"):
    targets = targets or [f"end{i}" for i in range(len(labels))]
    nodes = [node("s", "terminator", "Start"), node("d", "decision", text)]
    nodes += [node(t, "terminator", f"End {t}") for t in dict.fromkeys(targets)]
    edges = [edge("s", "d")] + [edge("d", t, label) for t, label in zip(targets, labels)]
    return chart(nodes, edges)


def connector_chart(out_id="A", in_id="A", out_type="connector", **in_extra):
    nodes = [node("s", "terminator", "Start"), node("p", "process", "Load orders"),
             node("c_out", out_type, out_id), node("c_in", "connector", in_id, **in_extra),
             node("q", "process", "Ship orders"), node("e", "terminator", "End")]
    edges = [edge("s", "p"), edge("p", "c_out"), edge("c_in", "q"), edge("q", "e")]
    return chart(nodes, edges)


def loop_chart(with_exit):
    nodes = [node("s", "terminator", "Start"), node("a", "process", "Read line"),
             node("b", "process", "Add line to total"), node("e", "terminator", "End")]
    edges = [edge("s", "a"), edge("a", "b"), edge("b", "a")]
    if with_exit:
        nodes.append(node("d", "decision", "More lines?"))
        edges = [edge("s", "a"), edge("a", "b"), edge("b", "d"), edge("d", "a", "Yes"),
                 edge("d", "e", "No")]
    return chart(nodes, edges)


def data_chart(with_output):
    nodes = [node("in", "document", "Orders"), node("p", "process", "Sort orders")]
    edges = [edge("in", "p")]
    if with_output:
        nodes.append(node("out", "stored_data", "Sorted orders"))
        edges.append(edge("p", "out"))
    else:
        nodes.append(node("e", "terminator", "End"))
        edges.append(edge("p", "e"))
    return chart(nodes, edges, chart_type="data")


def parallel_chart(branches):
    nodes = [node("s", "terminator", "Start"), node("fork", "parallel_mode", ""),
             node("join", "parallel_mode", ""), node("e", "terminator", "End")]
    edges = [edge("s", "fork"), edge("join", "e")]
    for i in range(branches):
        nodes.append(node(f"b{i}", "process", f"Run task {i}"))
        edges += [edge("fork", f"b{i}"), edge(f"b{i}", "join")]
    return chart(nodes, edges)


def loop_limit_chart(with_end):
    middle = [node("lb", "loop_limit", "L1: for each order", loop_id="L1", role="begin"),
              node("p", "process", "Price order")]
    if with_end:
        middle.append(node("le", "loop_limit", "L1: next order", loop_id="L1", role="end"))
    return program(*middle)


def unreachable_chart(island):
    nodes, edges = linear(node("p", "process", "Price order"))
    if island:
        nodes += [node("x", "process", "Retry order"), node("y", "process", "Log retry")]
        edges += [edge("x", "y"), edge("y", "x")]
    return chart(nodes, edges)


def dead_end_chart(trapped):
    nodes = [node("s", "terminator", "Start"), node("a", "process", "Poll queue"),
             node("d", "decision", "Message received?"), node("e", "terminator", "End")]
    edges = [edge("s", "a"), edge("a", "d"), edge("d", "a", "No")]
    edges.append(edge("d", "a" if trapped else "e", "Retry" if trapped else "Yes"))
    return chart(nodes, edges)


def annotated_chart(on_flow):
    data = program(node("p", "process", "Compute tax"))
    note = node("n", "annotation", "Rate table R-7")
    if on_flow:
        data["edges"].append(edge("n", "p"))
    else:
        note["annotates"] = ["p"]
    data["nodes"].append(note)
    return data


def steps_chart(count):
    return program(*[node(f"p{i}", "process", f"Do step {i}") for i in range(count - 2)])


PROBES = {
    # rule: (violating chart, conformant chart, severities expected on the violation, strict)
    "SYM-01": (program(node("p", "cloud", "Price order")),
               program(node("p", "process", "Price order")), {"error"}, True),
    "SYM-04": (program(node("p", "parallel_mode", "Price", detail_ref="XB4")),
               program(node("p", "process", "Price order", detail_ref="XB4")), {"error"}, True),
    "SYM-06": (program(node("p", "document", "Invoice")),
               dict(program(node("p", "document", "Invoice")), chart_type="system"),
               {"warning"}, True),
    "SYM-07": (program(node("p", "process", "Print copies", multiple=True)),
               dict(program(node("p", "document", "Invoice copies", multiple=True)),
                    chart_type="system"), {"warning"}, True),
    "SYM-08": (chart([node("s", "terminator", "Start"), node("m", "terminator", "Pause"),
                      node("e", "terminator", "End")], [edge("s", "m"), edge("m", "e")]),
               program(node("m", "process", "Wait for approval")), {"error"}, True),
    "SYM-09": (decision_chart(labels=("Yes",)), decision_chart(), {"error"}, True),
    "SYM-10": (parallel_chart(1), parallel_chart(2), {"warning"}, True),
    "SYM-11": (loop_limit_chart(False), loop_limit_chart(True), {"error"}, True),
    "SYM-12": (chart([node("s", "terminator", "Start"), node("x", "ellipsis", "..."),
                      node("e", "terminator", "End")], [edge("s", "e")]),
               chart([node("a", "data", "File 1"), node("x", "ellipsis", "..."),
                      node("b", "data", "File n")], [edge("a", "x"), edge("x", "b")],
                     chart_type="data"), {"warning"}, True),
    "FLW-01": (dict(program(node("p", "process", "Price order")), direction="BT"),
               dict(program(node("p", "process", "Price order")), direction="LR"),
               {"warning"}, True),
    "FLW-06": (chart([node("s", "terminator", "Start"), node("p", "process", "Price order"),
                      node("e1", "terminator", "End"), node("e2", "terminator", "End 2")],
                     [edge("s", "p"), edge("p", "e1"), edge("p", "e2")]),
               decision_chart(), {"error"}, True),
    "FLW-07": (dict(program(node("p", "process", "Price order")),
                    edges=[edge("s", "p"), edge("p", "p"), edge("p", "e")]),
               program(node("p", "process", "Price order")), {"error"}, True),
    "FLW-08": (dict(program(node("p", "process", "Call pricing")),
                    edges=[edge("s", "p", kind="control_transfer"), edge("p", "e")]),
               dict(program(node("p", "process", "Call pricing")), chart_type="system",
                    edges=[edge("s", "p", kind="control_transfer"), edge("p", "e")]),
               {"warning"}, True),
    "FLW-09": (dict(program(node("p", "process", "Price order")),
                    edges=[edge("s", "p"), edge("s", "p"), edge("p", "e")]),
               program(node("p", "process", "Price order")), {"warning"}, True),
    "CON-01": (dict(connector_chart(), edges=connector_chart()["edges"] + [edge("c_out", "q")]),
               connector_chart(), {"error"}, True),
    "CON-02": (connector_chart(in_id="B"), connector_chart(), {"error"}, True),
    "CON-03": (connector_chart(out_id="NEXTPAGE", in_id="NEXTPAGE"), connector_chart(),
               {"warning"}, True),
    "CON-04": (dict(connector_chart(out_type="off_page_connector", out_id="3A", in_id="3A")),
               connector_chart(out_id="3A", in_id="3A"), {"warning"}, True),
    "TXT-01": (program(node("p", "process", "Calculate the invoice total including every "
                                            "discount, surcharge and tax rate")),
               program(node("p", "process", "Calculate invoice total")), {"warning"}, True),
    "TXT-03": (decision_chart(labels=("Yes", "")), decision_chart(), {"error"}, True),
    "TXT-05": (program(node("p", "process", "Order valid?")),
               program(node("p", "process", "Validate order")), {"warning"}, True),
    "TXT-06": (decision_chart(text="Order"), decision_chart(text="Order complete?"), {"info"},
               True),
    "TXT-07": (program(node("p", "process", "")), program(node("p", "process", "Price order")),
               {"warning"}, True),
    "TXT-08": (annotated_chart(True), annotated_chart(False), {"error", "warning"}, True),
    "STR-01": (chart([node("s", "terminator", "Start"), node("p", "process", "Price order")],
                     [edge("s", "p")]),
               program(node("p", "process", "Price order")), {"error"}, True),
    "STR-02": (chart([node("s1", "terminator", "Start"), node("s2", "terminator", "Restart"),
                      node("e", "terminator", "End")], [edge("s1", "e"), edge("s2", "e")]),
               program(node("p", "process", "Price order")), {"warning"}, True),
    "STR-03": (unreachable_chart(True), unreachable_chart(False), {"error"}, True),
    "STR-04": (dead_end_chart(True), dead_end_chart(False), {"error"}, True),
    "STR-05": (loop_chart(False), loop_chart(True), {"error", "warning"}, True),
    "STR-06": (decision_chart(labels=("Red", "Green", "Blue")),
               decision_chart(labels=("Red", "Green", "Otherwise")), {"warning"}, True),
    "STR-07": (decision_chart(targets=["end0", "end0"]), decision_chart(), {"warning"}, True),
    "STR-08": (program(node("p", "process", "Charge card")),
               chart([node("s", "terminator", "Start"), node("p", "process", "Charge card"),
                      node("d", "decision", "Charge approved?"),
                      node("ok", "terminator", "End: paid"),
                      node("n", "process", "Notify customer"),
                      node("x", "terminator", "End: unpaid")],
                     [edge("s", "p"), edge("p", "d"), edge("d", "ok", "Yes"),
                      edge("d", "n", "No"), edge("n", "x")]), {"warning"}, True),
    "STR-09": (data_chart(False), data_chart(True), {"warning"}, True),
    "LAY-01": (steps_chart(31), steps_chart(30), {"warning"}, True),
    "LAY-02": (program(node("a", "process", "Approve credit line"),
                       node("b", "process", "i = i + 1"), node("c", "process", "Ship goods")),
               program(node("a", "process", "Approve credit line"),
                       node("b", "process", "Count approvals"),
                       node("c", "process", "Ship goods")), {"advisory"}, True),
    "LAY-03": (program(node("a", "process", "Validate address"),
                       node("b", "process", "Store order"),
                       node("c", "process", "Validate address")),
               program(node("a", "process", "Validate address"),
                       node("b", "process", "Store order")), {"advisory"}, True),
    "LAY-05": (dict(program(node("p", "process", "Price order")), title=""),
               program(node("p", "process", "Price order")), {"info"}, True),
    "MOD-01": (program(node("p", "process", "Price order"), node("p", "process", "Ship")),
               program(node("p", "process", "Price order"), node("q", "process", "Ship")),
               {"error"}, True),
    "MOD-02": (dict(program(node("p", "process", "Price order")),
                    edges=[edge("s", "p"), edge("p", "nowhere"), edge("p", "e")]),
               program(node("p", "process", "Price order")), {"error"}, True),
    "MOD-03": (dict(program(node("p", "process", "Price order")), direction="DIAGONAL"),
               program(node("p", "process", "Price order")), {"warning"}, True),
}

# Rules the tools only partly check: the probe covers the symptom they can see. SYM-03
# (non-ISO outlines) exists only in Mermaid input; test_mermaid_outline_misuse probes it.
PARTIAL_PROBES = {
    "SYM-05": (program(node("p", "predefined_process", "Compute tax", detail_ref="T1")),
               program(node("p", "process", "Compute tax", detail_ref="T1")), {"info"}, True),
}
MERMAID_PROBED = {"SYM-03"}
PACKAGE = Path(kb.__file__).resolve().parent


class RuleCoverageTest(unittest.TestCase):
    def test_every_checked_rule_has_a_probe(self):
        checked = {r["id"] for r in kb.RULES if r["check"] in ("automatic", "heuristic")}
        self.assertEqual(checked - set(PROBES), set(), "add a probe for these rules")
        self.assertEqual(set(PROBES) - checked, set(), "these probed rules are not 'checked'")
        partial = {r["id"] for r in kb.RULES if r["check"] == "partial"}
        self.assertEqual(partial, set(PARTIAL_PROBES) | MERMAID_PROBED)

    def test_judgment_rules_are_never_reported(self):
        reported = set()
        for path in PACKAGE.glob("*.py"):
            if path.name != "knowledge.py":
                reported |= set(re.findall(r'"([A-Z]{3}-\d\d)"', path.read_text("utf-8")))
        manual = {r["id"] for r in kb.RULES if r["check"] == "manual"}
        self.assertEqual(reported & manual, set(), "mark these rules 'partial' and probe them")
        self.assertEqual(reported - set(kb.RULES_BY_ID), set())

    def test_probes(self):
        for rule_id, (bad, good, severities, strict) in {**PROBES, **PARTIAL_PROBES}.items():
            with self.subTest(rule=rule_id):
                got = fired(bad, rule_id, strict)
                self.assertTrue(got, f"{rule_id} did not fire on its violating chart")
                self.assertLessEqual(got, severities | {"info", "advisory"},
                                     f"{rule_id} fired with unexpected severity {got}")
                self.assertTrue(got & severities, f"{rule_id} fired only as {got}")
                self.assertEqual(fired(good, rule_id, strict), set(),
                                 f"{rule_id} fired on its conformant chart")

    def test_three_way_comparison_is_complete(self):
        self.assertEqual(fired(decision_chart(labels=("< 0", "= 0", "> 0")), "STR-06"), set())
        overlapping = decision_chart(labels=("< 0", "= 0", ">= 0"))
        self.assertEqual(fired(overlapping, "STR-06"), {"warning"})

    def test_lenient_mode_accepts_the_template_connector(self):
        consistent = connector_chart(out_type="off_page_connector", out_id="3A", in_id="3A")
        consistent["nodes"][3]["type"] = "off_page_connector"
        self.assertEqual(fired(consistent, "CON-04", strict=False), set())
        self.assertEqual(fired(consistent, "CON-04"), {"warning"})
        mixed = PROBES["CON-04"][0]  # pentagon paired with a circle: flagged in both modes
        self.assertEqual(fired(mixed, "CON-04", strict=False), {"warning"})

    def test_model_errors_that_stop_loading(self):
        for data in ({"nodes": "none"}, {"nodes": [], "edges": {}}):
            with self.assertRaisesRegex(FlowchartInputError, "MOD-03"):
                load_flowchart(data)

    def test_mermaid_route_reports_the_same_structural_rules(self):
        """A violation survives generate -> parse: Mermaid input is checked like JSON."""
        structural = ["SYM-08", "SYM-09", "SYM-10", "FLW-06", "FLW-09", "CON-01", "CON-02",
                      "TXT-03", "TXT-05", "TXT-06", "TXT-08", "STR-01", "STR-02", "STR-03",
                      "STR-04", "STR-05", "STR-06", "STR-07", "STR-08", "LAY-02", "LAY-03"]
        for rule_id in structural:
            bad = PROBES[rule_id][0]
            with self.subTest(rule=rule_id):
                code, _ = generate(load_flowchart(bad))
                parsed = parse_mermaid(code, chart_type=load_flowchart(bad).chart_type)
                fc = load_flowchart(parsed.model)
                got = {f["rule_id"] for f in validate(fc)["findings"]}
                got |= {i.get("rule_id") for i in analyze(fc)["insights"]}
                self.assertIn(rule_id, got)

    def test_mermaid_outline_misuse(self):
        rounded = 'flowchart TB\n  s([Start]) --> p(Price order) --> e([End])\n'
        stadium = 'flowchart TB\n  s([Start]) --> p[Price order] --> e([End])\n'
        circle = 'flowchart TB\n  s((Start)) --> p[Price order] --> e([End])\n'
        self.assertEqual(self._mermaid_rules(rounded) & {"SYM-03"}, {"SYM-03"})
        self.assertEqual(self._mermaid_rules(stadium) & {"SYM-01", "SYM-03"}, set())
        self.assertIn("SYM-01", self._mermaid_rules(circle))

    def _mermaid_rules(self, code):
        parsed = parse_mermaid(code)
        report = validate(load_flowchart(parsed.model), extra_findings=parsed.findings)
        return {f["rule_id"] for f in report["findings"]}


if __name__ == "__main__":
    unittest.main()
