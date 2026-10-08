import json
import unittest

from support import chart, edge, linear, node, report, rule_ids
from iso5807_mcp.examples import EXAMPLES
from iso5807_mcp.model import FlowchartInputError, load_flowchart


def decision_chart(labels, targets=None):
    """Start -> d -> one end per label (or the given targets)."""
    nodes = [node("s", "terminator", "Start"), node("d", "decision", "Score >= 50?")]
    edges = [edge("s", "d")]
    targets = targets or [f"e{i}" for i in range(len(labels))]
    for target in dict.fromkeys(targets):
        nodes.append(node(target, "terminator", f"End {target}"))
    for label, target in zip(labels, targets):
        edges.append(edge("d", target, label))
    return chart(nodes, edges)


class ExamplesTest(unittest.TestCase):
    def test_reference_examples_are_clean(self):
        for name in ("order-processing", "monthly-billing", "refund-request"):
            result = report(EXAMPLES[name])
            self.assertTrue(result["valid"], name)
            self.assertEqual(result["summary"]["errors"], 0, name)
            self.assertEqual(result["summary"]["warnings"], 0, name)

    def test_flawed_example_reports_each_defect(self):
        result = report(EXAMPLES["flawed-login"])
        self.assertFalse(result["valid"])
        self.assertEqual(rule_ids(result, "error"),
                         {"TXT-08", "CON-02", "TXT-03", "FLW-06", "STR-01"})
        self.assertEqual(rule_ids(result, "warning"), {"TXT-08", "TXT-05", "SYM-06"})
        self.assertEqual(rule_ids(result, "info"), {"TXT-06"})
        self.assertEqual(result["alias_resolutions"],
                         {"start": "terminator", "diamond": "decision"})


class DecisionTest(unittest.TestCase):
    def test_single_exit(self):
        result = report(decision_chart(["Yes"]))
        self.assertIn("SYM-09", rule_ids(result, "error"))

    def test_unlabelled_and_duplicate_labels(self):
        self.assertIn("TXT-03", rule_ids(report(decision_chart(["Yes", ""])), "error"))
        self.assertIn("TXT-03", rule_ids(report(decision_chart(["Yes", "yes"])), "error"))

    def test_complementary_labels(self):
        for pair in (["Yes", "No"], ["True", "False"], [">= 50", "< 50"], ["Valid", "Invalid"],
                     ["Found", "Not found"], ["Paid", "Otherwise"]):
            self.assertNotIn("STR-06", rule_ids(report(decision_chart(pair))), pair)
        self.assertIn("STR-06", rule_ids(report(decision_chart(["Yes", "Maybe"])), "info"))
        self.assertIn("STR-06", rule_ids(report(decision_chart([">= 50", "< 40"])), "info"))

    def test_multiway_needs_otherwise(self):
        result = report(decision_chart(["A", "B", "C"]))
        self.assertIn("STR-06", rule_ids(result, "warning"))
        result = report(decision_chart(["A", "B", "Otherwise"]))
        self.assertNotIn("STR-06", rule_ids(result))

    def test_redundant_decision(self):
        result = report(decision_chart(["Yes", "No"], targets=["e0", "e0"]))
        self.assertIn("STR-07", rule_ids(result, "warning"))

    def test_decision_text_should_be_a_condition(self):
        data = decision_chart(["Yes", "No"])
        data["nodes"][1]["text"] = "Order status"
        self.assertIn("TXT-06", rule_ids(report(data), "info"))


class FlowlineTest(unittest.TestCase):
    def test_only_decisions_branch_in_program_charts(self):
        nodes = [node("s", "terminator", "Start"), node("p", "process", "Do work"),
                 node("a", "terminator", "End A"), node("b", "terminator", "End B")]
        data = chart(nodes, [edge("s", "p"), edge("p", "a"), edge("p", "b", "Yes")])
        result = report(data)
        self.assertIn("FLW-06", rule_ids(result, "error"))
        self.assertIn("FLW-06", rule_ids(result, "info"))  # outcome label on a process exit
        data["chart_type"] = "system"
        self.assertNotIn("FLW-06", rule_ids(report(data), "error"))

    def test_self_loop_and_duplicate_lines(self):
        nodes, edges = linear(node("p", "process", "Do work"))
        edges.append(edge("p", "p"))
        self.assertIn("FLW-07", rule_ids(report(chart(nodes, edges)), "error"))
        nodes, edges = linear(node("p", "process", "Do work"))
        edges.append(edge("p", "e"))
        result = report(chart(nodes, edges))
        self.assertIn("FLW-09", rule_ids(result, "warning"))
        self.assertNotIn("FLW-06", rule_ids(result))  # the duplicate is not a second exit

    def test_direction_and_line_kinds(self):
        nodes, edges = linear(node("p", "process", "Do work"))
        self.assertIn("FLW-01", rule_ids(report(chart(nodes, edges, direction="BT"))))
        edges[1]["kind"] = "communication_link"
        self.assertIn("FLW-08", rule_ids(report(chart(nodes, edges)), "warning"))
        edges[1]["kind"] = "smoke signal"
        self.assertIn("FLW-08", rule_ids(report(chart(nodes, edges)), "error"))


class StructureTest(unittest.TestCase):
    def test_missing_terminators_and_dead_ends(self):
        data = chart([node("a", "process", "Do A"), node("b", "process", "Do B")],
                     [edge("a", "b")])
        result = report(data)
        messages = " ".join(f["message"] for f in result["findings"] if f["rule_id"] == "STR-01")
        self.assertIn("no start Terminator", messages)
        self.assertIn("no end Terminator", messages)
        self.assertIn("Flow stops at Process 'b'", messages)

    def test_terminator_in_the_middle(self):
        nodes, edges = linear(node("t", "terminator", "Pause"))
        self.assertIn("SYM-08", rule_ids(report(chart(nodes, edges)), "error"))

    def test_multiple_starts(self):
        nodes = [node("s1", "terminator", "Start 1"), node("s2", "terminator", "Start 2"),
                 node("p", "process", "Do work"), node("e", "terminator", "End")]
        edges = [edge("s1", "p"), edge("s2", "p"), edge("p", "e")]
        self.assertIn("STR-02", rule_ids(report(chart(nodes, edges)), "warning"))

    def test_closed_loop_and_trapped_symbols(self):
        nodes = [node("s", "terminator", "Start"), node("p", "process", "Prepare"),
                 node("a", "process", "Poll queue"), node("b", "process", "Wait"),
                 node("e", "terminator", "End")]
        edges = [edge("s", "p"), edge("p", "a"), edge("a", "b"), edge("b", "a")]
        result = report(chart(nodes, edges))
        ids = rule_ids(result, "error")
        self.assertTrue({"STR-05", "STR-04", "SYM-08"} <= ids, ids)
        trapped = next(f for f in result["findings"] if f["rule_id"] == "STR-04")
        self.assertEqual(trapped["nodes"], ["s", "p"])

    def test_unreachable_island(self):
        nodes, edges = linear(node("p", "process", "Do work"))
        nodes += [node("x", "process", "Orphan X"), node("y", "process", "Orphan Y")]
        edges += [edge("x", "y"), edge("y", "x")]
        result = report(chart(nodes, edges))
        self.assertIn("STR-03", rule_ids(result, "error"))
        self.assertIn("STR-05", rule_ids(result, "error"))

    def test_loop_with_exit_is_fine(self):
        nodes = [node("s", "terminator", "Start"), node("r", "data", "Read record"),
                 node("d", "decision", "End of file?"), node("e", "terminator", "End")]
        edges = [edge("s", "r"), edge("r", "d"), edge("d", "e", "Yes"), edge("d", "r", "No")]
        result = report(chart(nodes, edges))
        self.assertTrue(result["valid"], result["findings"])

    def test_data_flowchart_alternation(self):
        nodes = [node("in", "document", "Order form"), node("p", "process", "Key orders"),
                 node("q", "process", "Sort orders"), node("out", "stored_data", "Order file")]
        edges = [edge("in", "p"), edge("p", "q"), edge("q", "out")]
        result = report(chart(nodes, edges, chart_type="data"))
        self.assertIn("STR-09", rule_ids(result, "warning"))
        self.assertNotIn("STR-01", rule_ids(result))  # data symbols are valid sources/sinks


class ConnectorTest(unittest.TestCase):
    def build(self, out_text="A", in_text="A", **in_extra):
        nodes = [node("s", "terminator", "Start"), node("p", "process", "Do work"),
                 node("c_out", "connector", out_text), node("c_in", "connector", in_text,
                                                            **in_extra),
                 node("q", "process", "Finish work"), node("e", "terminator", "End")]
        edges = [edge("s", "p"), edge("p", "c_out"), edge("c_in", "q"), edge("q", "e")]
        return chart(nodes, edges)

    def test_matched_pair_is_valid(self):
        result = report(self.build())
        self.assertTrue(result["valid"], result["findings"])
        self.assertNotIn("STR-03", rule_ids(result))

    def test_unmatched_connectors(self):
        result = report(self.build(in_text="B"))
        errors = [f for f in result["findings"] if f["rule_id"] == "CON-02"]
        self.assertEqual(len(errors), 2)

    def test_off_page_continuation(self):
        data = self.build(in_text="B")
        for item in data["nodes"]:
            if item["type"] == "connector":
                item["off_page"] = True
        result = report(data)
        self.assertTrue(result["valid"], result["findings"])
        self.assertIn("CON-02", rule_ids(result, "info"))

    def test_connector_roles_and_identifiers(self):
        data = self.build(out_text="Continue at shipping")
        data["nodes"][3]["text"] = "Continue at shipping"
        self.assertIn("CON-03", rule_ids(report(data), "warning"))
        data = self.build()
        data["edges"].append(edge("c_out", "q"))
        self.assertIn("CON-01", rule_ids(report(data), "error"))
        data = self.build()
        data["nodes"].append(node("c_in2", "connector", "A"))
        data["edges"].append(edge("c_in2", "q"))
        self.assertIn("CON-02", rule_ids(report(data), "error"))

    def test_legacy_off_page_connector(self):
        data = self.build()
        data["nodes"][2]["type"] = data["nodes"][3]["type"] = "off_page_connector"
        self.assertIn("CON-04", rule_ids(report(data), "warning"))
        self.assertNotIn("CON-04", rule_ids(report(data, strict=False)))


class SymbolTest(unittest.TestCase):
    def test_loop_limits(self):
        def loop_chart(**overrides):
            begin = node("lb", "loop_limit", "for each line", loop_id="L1", role="begin")
            end = node("le", "loop_limit", "until done", loop_id="L1", role="end")
            begin.update(overrides.get("begin", {}))
            end.update(overrides.get("end", {}))
            nodes, edges = linear(begin, node("p", "process", "Price line"), end)
            return chart(nodes, edges)

        self.assertTrue(report(loop_chart())["valid"])
        result = report(loop_chart(begin={"role": None}, end={"role": None}))
        self.assertIn("SYM-11", rule_ids(result, "info"))
        result = report(loop_chart(end={"loop_id": "L2"}))
        self.assertIn("SYM-11", rule_ids(result, "error"))
        result = report(loop_chart(begin={"loop_id": None}))
        self.assertIn("SYM-11", rule_ids(result, "error"))
        result = report(loop_chart(begin={"role": "end"}, end={"role": "begin"}))
        self.assertIn("SYM-11", rule_ids(result, "error"))  # end part not reachable

    def test_annotations(self):
        nodes, edges = linear(node("p", "process", "Compute tax"))
        nodes.append(node("n", "annotation", "Rate table T-7", annotates=["p"]))
        self.assertTrue(report(chart(nodes, edges))["valid"])
        nodes[-1]["annotates"] = ["ghost"]
        self.assertIn("MOD-02", rule_ids(report(chart(nodes, edges)), "error"))
        nodes[-1].pop("annotates")
        self.assertIn("TXT-08", rule_ids(report(chart(nodes, edges)), "warning"))
        edges.append(edge("n", "p"))
        self.assertIn("TXT-08", rule_ids(report(chart(nodes, edges)), "error"))
        edges[-1]["kind"] = "dashed"
        self.assertTrue(report(chart(nodes, edges))["valid"])

    def test_text_rules(self):
        nodes, edges = linear(node("p", "process", "Ship it?"))
        self.assertIn("TXT-05", rule_ids(report(chart(nodes, edges)), "warning"))
        nodes, edges = linear(node("p", "process", "x" * 61))
        self.assertIn("TXT-01", rule_ids(report(chart(nodes, edges)), "warning"))
        nodes, edges = linear(node("p", "process", ""))
        self.assertIn("TXT-07", rule_ids(report(chart(nodes, edges)), "warning"))

    def test_chart_type_symbol_policy(self):
        nodes, edges = linear(node("p", "document", "Invoice"))
        self.assertIn("SYM-06", rule_ids(report(chart(nodes, edges)), "warning"))
        self.assertNotIn("SYM-06", rule_ids(report(chart(nodes, edges), strict=False)))
        self.assertNotIn("SYM-06", rule_ids(report(chart(nodes, edges, chart_type="system"))))

    def test_striped_and_multiple_symbols(self):
        nodes, edges = linear(node("p", "process", "Validate order", detail_ref="A12"))
        self.assertTrue(report(chart(nodes, edges))["valid"])
        nodes, edges = linear(node("p", "process", "Validate order", striped=True))
        self.assertIn("SYM-04", rule_ids(report(chart(nodes, edges)), "warning"))
        nodes, edges = linear(node("p", "terminator", "X", detail_ref="A1"))
        self.assertIn("SYM-04", rule_ids(report(chart(nodes, edges)), "error"))
        nodes, edges = linear(node("p", "predefined_process", "Pay", detail_ref="A1"))
        self.assertIn("SYM-05", rule_ids(report(chart(nodes, edges)), "info"))
        nodes, edges = linear(node("p", "process", "Work", multiple=True))
        self.assertIn("SYM-07", rule_ids(report(chart(nodes, edges)), "warning"))

    def test_parallel_mode(self):
        nodes, edges = linear(node("p", "parallel_mode", ""))
        self.assertIn("SYM-10", rule_ids(report(chart(nodes, edges)), "warning"))
        nodes = [node("s", "terminator", "Start"), node("fork", "parallel_mode", ""),
                 node("a", "process", "Pack goods"), node("b", "process", "Print invoice"),
                 node("join", "parallel_mode", ""), node("e", "terminator", "End")]
        edges = [edge("s", "fork"), edge("fork", "a"), edge("fork", "b"), edge("a", "join"),
                 edge("b", "join"), edge("join", "e")]
        self.assertTrue(report(chart(nodes, edges))["valid"])

    def test_unknown_symbol_and_density(self):
        nodes, edges = linear(node("p", "decison", "OK?"))
        result = report(chart(nodes, edges))
        sym = next(f for f in result["findings"] if f["rule_id"] == "SYM-01")
        self.assertIn("decision", sym["message"])
        nodes, edges = linear(*[node(f"p{i}", "process", f"Step {i}") for i in range(30)])
        self.assertIn("LAY-01", rule_ids(report(chart(nodes, edges)), "warning"))
        nodes, edges = linear(node("p", "process", "Do work"))
        self.assertIn("LAY-05", rule_ids(report(chart(nodes, edges, title="")), "info"))


class ModelTest(unittest.TestCase):
    def test_input_forms(self):
        data = EXAMPLES["order-processing"]
        self.assertTrue(report(json.dumps(data))["valid"])
        self.assertTrue(report({"flowchart": data})["valid"])
        with self.assertRaises(FlowchartInputError):
            load_flowchart({"edges": []})
        with self.assertRaises(FlowchartInputError):
            load_flowchart("{not json")

    def test_model_integrity(self):
        nodes, edges = linear(node("p", "process", "Do work"))
        nodes.append(node("p", "process", "Again"))
        edges.append(edge("p", "nowhere"))
        result = report(chart(nodes, edges))
        self.assertIn("MOD-01", rule_ids(result, "error"))
        self.assertIn("MOD-02", rule_ids(result, "error"))
        self.assertIn("MOD-03", rule_ids(report(chart([], []))))


if __name__ == "__main__":
    unittest.main()
