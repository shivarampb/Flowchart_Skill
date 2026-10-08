import unittest

from support import chart, edge, linear, node
from iso5807_mcp import knowledge as kb
from iso5807_mcp.examples import EXAMPLES
from iso5807_mcp.mermaid import MermaidParseError, generate, mermaid_ids, parse_mermaid
from iso5807_mcp.model import flowchart_to_dict, load_flowchart
from iso5807_mcp.validator import validate


def all_symbols_chart():
    nodes = [node("start", "terminator", "Start")]
    edges = []
    previous = "start"
    for node_type in kb.NODE_TYPES:
        if node_type in ("terminator", "annotation", "connector", "off_page_connector",
                         "loop_limit"):
            continue
        nodes.append(node(f"n_{node_type}", node_type, f"{node_type} text"))
        edges.append(edge(previous, f"n_{node_type}"))
        previous = f"n_{node_type}"
    nodes += [
        node("lb", "loop_limit", "for each x", loop_id="L1", role="begin"),
        node("le", "loop_limit", "until done", loop_id="L1", role="end"),
        node("striped", "process", "Striped step", detail_ref="D-7"),
        node("striped_doc", "document", "Striped doc", detail_ref="D-8"),
        node("docs", "document", "Copies", multiple=True),
        node("files", "stored_data", "Files", multiple=True),
        node("tricky", "process", 'He said "hi" #1 <b>x</b> a|b [c] {d} (e)\nsecond line'),
        node("out_a", "connector", "A"), node("in_a", "connector", "A"),
        node("out_p", "connector", "3B", off_page=True),
        node("legacy", "off_page_connector", "P2-A"),
        node("end", "terminator", "End"),
        node("note", "annotation", "An annotation", annotates=["tricky"]),
    ]
    edges += [
        edge(previous, "lb"), edge("lb", "striped"), edge("striped", "le"),
        edge("le", "striped_doc"),
        edge("striped_doc", "docs", "net", kind="communication_link"),
        edge("docs", "files", "alt", kind="dashed"),
        edge("files", "tricky"), edge("tricky", "out_a", 'pipe | quote " <lt>'),
        edge("in_a", "out_p"), edge("in_a", "legacy"), edge("in_a", "end", "Yes"),
    ]
    return chart(nodes, edges, title='All "symbols"')


def renamed(model, ids):
    """Rename ids in a serialized model with the generator's id mapping."""
    for item in model["nodes"]:
        item["id"] = ids[item["id"]]
        if "annotates" in item:
            item["annotates"] = [ids[x] for x in item["annotates"]]
    for item in model["edges"]:
        item["from"], item["to"] = ids[item["from"]], ids[item["to"]]
    return model


def normalized(model):
    model = dict(model)
    model["nodes"] = sorted(model["nodes"], key=lambda n: n["id"])
    model["edges"] = sorted(model["edges"], key=lambda e: (e["from"], e["to"], e.get("label", "")))
    return model


class RoundTripTest(unittest.TestCase):
    def assert_round_trip(self, data, syntax):
        fc = load_flowchart(data)
        code, _ = generate(fc, syntax)
        parsed = parse_mermaid(code, chart_type=fc.chart_type)
        expected = renamed(flowchart_to_dict(fc), mermaid_ids(fc, syntax))
        actual = flowchart_to_dict(load_flowchart(parsed.model))
        self.assertEqual(normalized(actual), normalized(expected), f"{syntax}\n{code}")
        self.assertEqual(parsed.findings, [])

    def test_examples_round_trip(self):
        for name, data in EXAMPLES.items():
            for syntax in ("extended", "classic"):
                with self.subTest(example=name, syntax=syntax):
                    self.assert_round_trip(data, syntax)

    def test_every_symbol_round_trips(self):
        for syntax in ("extended", "classic"):
            with self.subTest(syntax=syntax):
                self.assert_round_trip(all_symbols_chart(), syntax)

    def test_control_transfer_degrades_to_flow(self):
        nodes, edges = linear(node("a", "process", "Main"), node("b", "process", "Handler"))
        edges[1]["kind"] = "control_transfer"
        code, notes = generate(load_flowchart(chart(nodes, edges)))
        self.assertIn("a ==> b", code)
        self.assertTrue(any("Control transfer" in n for n in notes))
        parsed = parse_mermaid(code)
        self.assertNotIn("kind", next(e for e in parsed.model["edges"] if e["from"] == "a"))


class GeneratorTest(unittest.TestCase):
    def test_extended_output(self):
        code, notes = generate(load_flowchart(EXAMPLES["order-processing"]))
        header = '---\ntitle: "Process customer order"\n---\nflowchart TB\n'
        self.assertTrue(code.startswith(header))
        self.assertIn('order_valid@{ shape: diam, label: "Order data valid?" }', code)
        self.assertIn("order_valid -->|Yes| in_stock", code)
        self.assertIn("charge -.- note_charge", code)
        self.assertIn("accTitle: Process customer order", code)
        self.assertIn("Mermaid >= 11.3.0", notes[0])

    def test_classic_output(self):
        code, notes = generate(load_flowchart(EXAMPLES["monthly-billing"]), "classic")
        self.assertIn('start(["Start"])', code)
        self.assertIn('init{{"Set invoice count = 0"}}', code)
        self.assertIn('loop_begin[/"L1: For each active customer"\\]', code)
        self.assertIn('loop_End[\\"L1: Until no customer left"/]', code)
        self.assertIn("class loop_End iso_loopend", code)
        self.assertNotIn("@{", code)
        self.assertTrue(any("10.4.0" in n for n in notes))

    def test_escaping(self):
        nodes, edges = linear(node("p", "process", 'Say "hi" #2 <now>\nline 2'))
        edges[0]["label"] = "a|b"
        code, _ = generate(load_flowchart(chart(nodes, edges)))
        self.assertIn('label: "Say #34;hi#34; #35;2 #60;now#62;<br>line 2"', code)
        self.assertIn("|a#124;b|", code)

    def test_reserved_ids(self):
        nodes, edges = linear(node("graph", "process", "A"), node("1st", "process", "B"),
                              start="end", end="style")
        fc = load_flowchart(chart(nodes, edges))
        self.assertEqual(mermaid_ids(fc), {"end": "n_end", "graph": "n_graph", "1st": "n_1st",
                                           "style": "n_style"})
        classic = mermaid_ids(load_flowchart(chart(*linear(node("loop_end", "process", "X")))),
                              "classic")
        self.assertEqual(classic["loop_end"], "loop_End")


class ParserTest(unittest.TestCase):
    def test_classic_shapes_and_links(self):
        code = """
        graph LR
            A([Start]) --> B[/Read order/]
            B --> C{Valid?}
            C -- Yes --> D[[Charge payment]] & E[\\Clerk checks/]
            C -->|No| F{{Set retries = 0}}; F --> G[(Orders)]
            D -.-> H((A))
            E --- I>P2]
            J((A)) --> K([End])
        """
        parsed = parse_mermaid(code)
        types = {n["id"]: n["type"] for n in parsed.model["nodes"]}
        self.assertEqual(types, {
            "A": "terminator", "B": "data", "C": "decision", "D": "predefined_process",
            "E": "manual_operation", "F": "preparation", "G": "direct_access_storage",
            "H": "connector", "I": "off_page_connector", "J": "connector", "K": "terminator"})
        self.assertEqual(parsed.model["direction"], "LR")
        labels = {(e["from"], e["to"]): e.get("label") for e in parsed.model["edges"]}
        self.assertEqual(labels[("C", "D")], "Yes")
        self.assertEqual(labels[("C", "E")], "Yes")
        self.assertEqual(labels[("C", "F")], "No")
        self.assertEqual(next(e for e in parsed.model["edges"] if e["from"] == "D")["kind"],
                         "dashed")
        self.assertEqual([f["rule_id"] for f in parsed.findings], ["SYM-03"])  # cylinder

    def test_frontmatter_comments_and_classes(self):
        code = ('---\ntitle: "Quoted: title"\n---\n%%{init: {"theme": "dark"}}%%\n'
                'flowchart TD\n  %% a comment\n  a@{ shape: brace, label: "Note" }\n'
                '  b["Do it"]:::iso_document\n  b -.- a\n  subgraph S\n  c[X]\n  end\n'
                '  c ~~~ b\n  classDef iso_document x\n')
        parsed = parse_mermaid(code)
        self.assertEqual(parsed.model["title"], "Quoted: title")
        types = {n["id"]: n for n in parsed.model["nodes"]}
        self.assertEqual(types["a"]["annotates"], ["b"])
        self.assertEqual(types["b"]["type"], "document")
        self.assertTrue(any("Subgraphs" in n for n in parsed.notes))
        self.assertTrue(any("Invisible" in n for n in parsed.notes))

    def test_outline_misuse_becomes_findings(self):
        code = "flowchart TD\n  A((Start)) --> B(Do work) --> C(End)\n  B --> X[/x\\]\n"
        parsed = parse_mermaid(code)
        rules = sorted((f["rule_id"], f["severity"]) for f in parsed.findings)
        self.assertEqual(rules, [("SYM-01", "error"), ("SYM-03", "warning"),
                                 ("SYM-03", "warning")])
        types = {n["id"]: n["type"] for n in parsed.model["nodes"]}
        self.assertEqual(types, {"A": "terminator", "B": "process", "C": "terminator",
                                 "X": "mermaid:trap-b"})
        report = validate(load_flowchart(parsed.model), extra_findings=parsed.findings)
        self.assertFalse(report["valid"])
        self.assertIn("SYM-01", {f["rule_id"] for f in report["findings"]})

    def test_not_a_flowchart(self):
        with self.assertRaises(MermaidParseError):
            parse_mermaid("sequenceDiagram\n  A->>B: hi\n")


if __name__ == "__main__":
    unittest.main()
