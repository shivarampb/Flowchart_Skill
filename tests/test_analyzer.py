import unittest

from support import chart, edge, linear, node
from iso5807_mcp.analyzer import analyze, risky_operation
from iso5807_mcp.examples import EXAMPLES
from iso5807_mcp.model import load_flowchart


def run(data):
    return analyze(load_flowchart(data))


def categories(result, severity=None):
    return [i["category"] for i in result["insights"]
            if severity is None or i["severity"] == severity]


class MetricsTest(unittest.TestCase):
    def test_refund_metrics(self):
        metrics = run(EXAMPLES["refund-request"])["metrics"]
        self.assertEqual(metrics["decisions"], 5)
        self.assertEqual(metrics["cyclomatic_complexity"], 6)
        self.assertEqual(metrics["end_to_end_paths"], 7)
        self.assertEqual(metrics["entry_points"], ["start"])
        self.assertEqual(sorted(metrics["exit_points"]),
                         ["end_escalated", "end_refunded", "end_rejected"])

    def test_loop_limit_pairs_count_as_decisions(self):
        metrics = run(EXAMPLES["monthly-billing"])["metrics"]
        self.assertEqual(metrics["loops"]["loop_limit_pairs"], 1)
        self.assertEqual(metrics["cyclomatic_complexity"], 3)  # 1 decision + 1 loop + 1

    def test_cycles_are_reported(self):
        result = run(EXAMPLES["flawed-login"])
        self.assertEqual(result["metrics"]["loops"]["cycles"], 1)
        self.assertIn("loop", categories(result))


class InsightTest(unittest.TestCase):
    def test_single_points_of_failure(self):
        result = run(EXAMPLES["refund-request"])
        mandatory = next(i for i in result["insights"]
                         if i["message"].startswith("Every execution path"))
        self.assertEqual(mandatory["nodes"], ["read_request", "find_order", "order_found"])

    def test_unchecked_fallible_operation(self):
        nodes, edges = linear(node("p", "process", "Charge card"))
        self.assertIn("failure_state", categories(run(chart(nodes, edges)), "warning"))
        nodes = [node("s", "terminator", "Start"), node("p", "process", "Charge card"),
                 node("d", "decision", "Charge approved?"), node("ok", "terminator", "End: paid"),
                 node("no", "process", "Notify customer"), node("x", "terminator", "End: failed")]
        edges = [edge("s", "p"), edge("p", "d"), edge("d", "ok", "Yes"), edge("d", "no", "No"),
                 edge("no", "x")]
        warnings = [i for i in run(chart(nodes, edges))["insights"]
                    if i["category"] == "failure_state" and i["severity"] == "warning"]
        self.assertEqual(warnings, [])

    def test_unbounded_retry(self):
        nodes = [node("s", "terminator", "Start"), node("send", "process", "Send message"),
                 node("ok", "decision", "Delivered?"), node("wait", "process", "Wait and retry"),
                 node("e", "terminator", "End")]
        edges = [edge("s", "send"), edge("send", "ok"), edge("ok", "e", "Yes"),
                 edge("ok", "wait", "No"), edge("wait", "send")]
        messages = " ".join(i["message"] for i in run(chart(nodes, edges))["insights"])
        self.assertIn("no attempt counter or timeout", messages)
        nodes[3]["text"] = "Wait, then retry (max 3 attempts)"
        messages = " ".join(i["message"] for i in run(chart(nodes, edges))["insights"])
        self.assertNotIn("no attempt counter or timeout", messages)

    def test_redundancy_and_happy_path(self):
        nodes, edges = linear(node("a", "process", "Validate address"),
                              node("b", "process", "Store order"),
                              node("c", "process", "Validate address"))
        result = run(chart(nodes, edges))
        self.assertIn("redundancy", categories(result))
        self.assertIn("happy path", " ".join(i["message"] for i in result["insights"]))

    def test_granularity_drift(self):
        nodes, edges = linear(node("a", "process", "Approve credit line"),
                              node("b", "process", "i = i + 1"),
                              node("c", "process", "Ship the goods"))
        self.assertIn("granularity", categories(run(chart(nodes, edges))))
        nodes, edges = linear(node("a", "process", "Validate and then save order"))
        self.assertIn("granularity", categories(run(chart(nodes, edges))))

    def test_negative_outcome_ending_silently(self):
        nodes = [node("s", "terminator", "Start"), node("d", "decision", "Card valid?"),
                 node("p", "process", "Book seat"), node("e", "terminator", "End"),
                 node("x", "terminator", "End: refused")]
        edges = [edge("s", "d"), edge("d", "p", "Yes"), edge("d", "x", "No"), edge("p", "e")]
        messages = " ".join(i["message"] for i in run(chart(nodes, edges))["insights"])
        self.assertIn("ends the flow at once", messages)

    def test_risky_operation_uses_the_leading_verb(self):
        self.assertEqual(risky_operation("process", "Charge card"), "Charge")
        self.assertEqual(risky_operation("process", "Look up order"), "Look up")
        self.assertEqual(risky_operation("process", "Write refund confirmation"), "")
        self.assertEqual(risky_operation("manual_operation", "Clerk checks signature"), "checks")
        self.assertEqual(risky_operation("process", "Calculate tax"), "")


if __name__ == "__main__":
    unittest.main()
