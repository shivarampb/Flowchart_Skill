"""Rule-based conformance checks against ANSI/ISO 5807:1985."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Optional, Set, Tuple

from . import knowledge as kb
from .graph import FlowGraph, reachable, strongly_connected_components
from .model import Edge, Flowchart, Node
from .report import count_findings, finding, sort_findings

TEXT_LIMIT = 60
DECISION_TEXT_LIMIT = 50
PAGE_SYMBOL_LIMIT = 30
CONNECTOR_ID_LIMIT = 4
OFF_PAGE_ID_LIMIT = 8

POSITIVE_LABELS = {
    "yes", "y", "true", "t", "1", "ok", "pass", "passed", "valid", "success", "successful",
    "succeeded", "found", "approved", "accept", "accepted", "available", "exists", "match",
    "matched", "on", "correct", "complete", "completed", "done", "authorized", "authorised",
    "in stock", "present", "positive", "enough", "sufficient", "paid", "confirmed",
}
NEGATIVE_LABELS = {
    "no", "n", "false", "f", "0", "not ok", "nok", "fail", "failed", "failure", "invalid",
    "error", "not found", "rejected", "reject", "denied", "unavailable", "not available",
    "missing", "no match", "mismatch", "off", "incorrect", "incomplete", "timeout",
    "timed out", "unauthorized", "unauthorised", "declined", "out of stock", "absent",
    "negative", "not enough", "insufficient", "unpaid", "not confirmed", "not done",
}
DEFAULT_LABELS = {
    "else", "otherwise", "default", "other", "others", "any other", "anything else",
    "none of the above", "all other", "all others", "unknown", "other value", "other values",
}
QUESTION_WORDS = {
    "is", "are", "was", "were", "does", "do", "did", "has", "have", "had", "can", "could",
    "will", "would", "should", "shall", "may", "must", "any", "all", "if", "whether",
    "which", "what", "how", "more", "less", "enough", "too",
}
_OPS = {"<": "<", ">": ">", "<=": "<=", ">=": ">=", "=": "=", "==": "=", "!=": "!=",
        "<>": "!=", "≠": "!=", "≤": "<=", "≥": ">="}
_COMPLEMENT = {frozenset(("<", ">=")), frozenset((">", "<=")), frozenset(("=", "!="))}
_OP_RE = re.compile(r"^\s*(<=|>=|!=|==|<>|≤|≥|≠|<|>|=)\s*(.+?)\s*$")

STRIPABLE = tuple(t for t in kb.PROCESS_FAMILY if t not in ("parallel_mode", "loop_limit")) + \
    kb.DATA_FAMILY
TEXT_OPTIONAL = ("parallel_mode", "ellipsis", "loop_limit")


def norm_label(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold()).strip(" .!:")


def is_default_label(label: str) -> bool:
    value = norm_label(label)
    return value in DEFAULT_LABELS or value.startswith(("other", "else", "any other"))


def is_outcome_label(label: str) -> bool:
    value = norm_label(label)
    return value in POSITIVE_LABELS or value in NEGATIVE_LABELS


def _comparison(label: str) -> Optional[Tuple[str, str]]:
    match = _OP_RE.match(label)
    if not match:
        return None
    return _OPS[match.group(1)], match.group(2).casefold()


def complementary(first: str, second: str) -> bool:
    """True when two Decision exit labels obviously cover all outcomes."""
    a, b = norm_label(first), norm_label(second)
    if (a in POSITIVE_LABELS and b in NEGATIVE_LABELS) or (
            b in POSITIVE_LABELS and a in NEGATIVE_LABELS):
        return True
    for x, y in ((a, b), (b, a)):
        for prefix in ("not ", "no ", "non-", "non ", "un", "in", "not-"):
            if y == prefix + x:
                return True
    if is_default_label(a) or is_default_label(b):
        return True
    ca, cb = _comparison(first), _comparison(second)
    if ca and cb and ca[1] == cb[1] and frozenset((ca[0], cb[0])) in _COMPLEMENT:
        return True
    return False


def looks_like_condition(text: str) -> bool:
    stripped = text.strip()
    if stripped.endswith("?") or re.search(r"[<>=≠≤≥]", stripped):
        return True
    words = re.findall(r"[A-Za-z]+", stripped.lower())
    return bool(words) and words[0] in QUESTION_WORDS


def _ids(nodes: List[Node]) -> List[str]:
    return [n.id for n in nodes]


def _fmt(ids: List[str], limit: int = 8) -> str:
    shown = ", ".join(f"'{i}'" for i in ids[:limit])
    return shown + (f" and {len(ids) - limit} more" if len(ids) > limit else "")


class FlowContext:
    """Derived structure shared by the validator and the analyzer."""

    def __init__(self, fc: Flowchart) -> None:
        self.fc = fc
        self.findings: List[Dict[str, object]] = []
        self.by_id = fc.by_id
        self.annotation_ids: Set[str] = {n.id for n in fc.nodes if n.type == "annotation"}
        self.flow_nodes: List[Node] = [n for n in fc.nodes if n.type != "annotation"]
        self.ids: List[str] = _ids(self.flow_nodes)
        self.attached_annotations: Set[str] = set()
        self.flow_edges: List[Edge] = []
        self.out_edges: Dict[str, List[Edge]] = {i: [] for i in self.ids}
        self.in_edges: Dict[str, List[Edge]] = {i: [] for i in self.ids}
        self.virtual: List[Tuple[str, str]] = []
        self.entry_connectors: List[Node] = []  # unmatched in-connectors (flow entries)
        self.exit_connectors: List[Node] = []  # unmatched out-connectors (flow exits)
        self.remote_entries: List[Node] = []  # ... of which legitimately cross-page
        self.remote_exits: List[Node] = []
        self._collect_edges()
        self.indeg = {i: len(self.in_edges[i]) for i in self.ids}
        self.outdeg = {i: len(self.out_edges[i]) for i in self.ids}
        self._pair_connectors()
        self.graph = FlowGraph(self.ids)
        for edge in self.flow_edges:
            self.graph.add(edge.source, edge.target)
        for source, target in self.virtual:
            self.graph.add(source, target)

    def nodes_of(self, *types: str) -> List[Node]:
        return [n for n in self.flow_nodes if n.type in types]

    def _collect_edges(self) -> None:
        program = self.fc.chart_type == "program"
        seen: Counter = Counter()
        for edge in self.fc.edges:
            if edge.source == edge.target:
                self.findings.append(finding(
                    "FLW-07", "error",
                    f"Flowline {edge.ref()} connects '{edge.source}' to itself: an "
                    "unconditional self-loop never ends.", nodes=[edge.source], edges=[edge.ref()]))
                continue
            touched = [x for x in (edge.source, edge.target) if x in self.annotation_ids]
            if touched:
                if edge.kind == "dashed":
                    self.attached_annotations.update(touched)
                else:
                    self.findings.append(finding(
                        "TXT-08", "error",
                        f"Flowline {edge.ref()} puts Annotation {_fmt(touched)} on the flow "
                        "path; an Annotation is attached with a dashed line only.",
                        nodes=touched, edges=[edge.ref()]))
                continue
            key = (edge.source, edge.target, edge.kind, norm_label(edge.label))
            seen[key] += 1
            if seen[key] > 1:
                if seen[key] == 2:
                    self.findings.append(finding(
                        "FLW-09", "warning", f"Flowline {edge.ref()} is drawn more than once.",
                        nodes=[edge.source, edge.target], edges=[edge.ref()]))
                continue
            if edge.kind == "dashed":
                continue  # alternative relationship: not part of the flow
            if program and edge.kind in ("communication_link", "control_transfer"):
                self.findings.append(finding(
                    "FLW-08", "warning",
                    f"Flowline {edge.ref()} is a {edge.kind.replace('_', ' ')}; program "
                    "flowcharts use ordinary flowlines.", edges=[edge.ref()]))
            self.flow_edges.append(edge)
            self.out_edges[edge.source].append(edge)
            self.in_edges[edge.target].append(edge)

    def _pair_connectors(self) -> None:
        ins: Dict[str, List[Node]] = defaultdict(list)
        outs: Dict[str, List[Node]] = defaultdict(list)
        for node in self.nodes_of(*kb.CONNECTOR_TYPES):
            i, o = self.indeg[node.id], self.outdeg[node.id]
            if i == 0 and o == 0:
                self.findings.append(finding(
                    "CON-01", "error", f"{node.describe()} is not attached to any flowline.",
                    nodes=[node.id]))
                continue
            if i > 0 and o > 0:
                self.findings.append(finding(
                    "CON-01", "error",
                    f"{node.describe()} has both incoming and outgoing flowlines; a connector "
                    "is either an exit (out-connector) or an entry (in-connector).",
                    nodes=[node.id]))
                continue
            if o > 1:
                self.findings.append(finding(
                    "CON-01", "error",
                    f"In-connector '{node.id}' has {o} outgoing flowlines; it continues exactly "
                    "one line.", nodes=[node.id]))
            identifier = node.text.strip()
            if not identifier:
                continue  # reported by TXT-07
            limit = OFF_PAGE_ID_LIMIT if node.off_page else CONNECTOR_ID_LIMIT
            if len(identifier.replace(" ", "")) > limit:
                self.findings.append(finding(
                    "CON-03", "warning",
                    f"{node.describe()} identifier '{identifier}' is longer than {limit} "
                    "characters.", nodes=[node.id]))
            (ins if i == 0 else outs)[identifier.casefold()].append(node)

        for key in sorted(set(ins) | set(outs)):
            entry, exits = ins.get(key, []), outs.get(key, [])
            label = (entry or exits)[0].text.strip()
            if len(entry) > 1:
                self.findings.append(finding(
                    "CON-02", "error",
                    f"Identifier '{label}' marks {len(entry)} in-connectors "
                    f"({_fmt(_ids(entry))}); an identifier must lead to exactly one place.",
                    nodes=_ids(entry)))
            if exits and not entry:
                local = [c for c in exits if not c.off_page]
                remote = [c for c in exits if c.off_page]
                if local:
                    self.findings.append(finding(
                        "CON-02", "error",
                        f"Out-connector(s) {_fmt(_ids(local))} with identifier '{label}' have no "
                        "matching in-connector.", nodes=_ids(local)))
                if remote:
                    self.findings.append(finding(
                        "CON-02", "info",
                        f"Connector(s) {_fmt(_ids(remote))} with identifier '{label}' continue on "
                        "another page; make sure that page has the in-connector.",
                        nodes=_ids(remote)))
                self.exit_connectors.extend(exits)
                self.remote_exits.extend(remote)
            if entry and not exits:
                local = [c for c in entry if not c.off_page]
                remote = [c for c in entry if c.off_page]
                if local:
                    self.findings.append(finding(
                        "CON-02", "error",
                        f"In-connector(s) {_fmt(_ids(local))} with identifier '{label}' are never "
                        "reached: no out-connector has this identifier.", nodes=_ids(local)))
                if remote:
                    self.findings.append(finding(
                        "CON-02", "info",
                        f"Connector(s) {_fmt(_ids(remote))} with identifier '{label}' are entered "
                        "from another page; make sure that page has the out-connector.",
                        nodes=_ids(remote)))
                self.entry_connectors.extend(entry)
                self.remote_entries.extend(remote)
            if entry and exits:
                for out_connector in exits:
                    self.virtual.append((out_connector.id, entry[0].id))
                if len({c.type for c in entry + exits}) > 1:
                    self.findings.append(finding(
                        "CON-04", "warning",
                        f"Identifier '{label}' pairs a circle connector with an ANSI off-page "
                        "connector; use one connector convention.", nodes=_ids(entry + exits)))


def validate(fc: Flowchart, strict: bool = True,
             extra_findings: Iterable[Dict[str, object]] = ()) -> Dict[str, object]:
    """Check a normalized flowchart against the rule base; return a report.

    ``extra_findings`` (e.g. outline findings from the Mermaid parser) join the report.
    """
    ctx = FlowContext(fc)
    out: List[Dict[str, object]] = list(fc.findings) + list(extra_findings) + list(ctx.findings)
    chart = fc.chart_type
    program = chart == "program"
    flow_chart = chart in ("program", "data", "system")

    if fc.nodes:
        _check_annotations(fc, ctx, out)
        _check_text(ctx, out)
        _check_symbols(fc, ctx, out, strict)
        terminal_starts, terminal_ends = _check_terminators(ctx, out)
        _check_decisions(ctx, out)
        if program:
            _check_branching(ctx, out)
        _check_parallel_and_loops(ctx, out)
        if flow_chart:
            _check_structure(fc, ctx, out, terminal_starts, terminal_ends)
        if chart == "data":
            _check_data_alternation(ctx, out)
        _check_layout(fc, ctx, out)

    findings = sort_findings(out)
    counts = count_findings(findings)
    report: Dict[str, object] = {
        "standard": kb.STANDARD,
        "valid": counts["errors"] == 0,
        "strict": strict,
        "chart_type": chart,
        "title": fc.title,
        "summary": dict(counts, symbols=len(ctx.flow_nodes),
                        annotations=len(ctx.annotation_ids), flowlines=len(ctx.flow_edges)),
        "findings": findings,
    }
    if fc.alias_resolutions:
        report["alias_resolutions"] = fc.alias_resolutions
    return report


# ----------------------------------------------------------------- checks


def _check_annotations(fc: Flowchart, ctx: FlowContext, out: List[Dict[str, object]]) -> None:
    for node in fc.nodes:
        if node.type != "annotation":
            continue
        for ref in node.annotates:
            target = fc.by_id.get(ref)
            if target is None:
                out.append(finding(
                    "MOD-02", "error", f"Annotation '{node.id}' annotates unknown symbol '{ref}'.",
                    nodes=[node.id]))
            elif target.type == "annotation":
                out.append(finding(
                    "TXT-08", "warning",
                    f"Annotation '{node.id}' annotates another annotation ('{ref}').",
                    nodes=[node.id, ref], fix="Attach annotations to symbols or lines."))
            else:
                ctx.attached_annotations.add(node.id)
        if node.id not in ctx.attached_annotations:
            out.append(finding(
                "TXT-08", "warning", f"Annotation '{node.id}' is not attached to any symbol.",
                nodes=[node.id], fix="Set 'annotates' to the id(s) of the symbols it explains."))
        if not node.text:
            out.append(finding("TXT-07", "warning", f"Annotation '{node.id}' has no text.",
                               nodes=[node.id]))


def _check_text(ctx: FlowContext, out: List[Dict[str, object]]) -> None:
    for node in ctx.flow_nodes:
        text = node.text
        if node.type not in TEXT_OPTIONAL and not text:
            severity = "error" if node.type in ("decision",) + kb.CONNECTOR_TYPES else "warning"
            what = "identifier" if node.type in kb.CONNECTOR_TYPES else "text"
            out.append(finding("TXT-07", severity, f"{node.describe()} has no {what}.",
                               nodes=[node.id]))
        limit = DECISION_TEXT_LIMIT if node.type == "decision" else TEXT_LIMIT
        if node.type not in kb.CONNECTOR_TYPES and len(text) > limit:
            out.append(finding(
                "TXT-01", "warning",
                f"{node.describe()} holds {len(text)} characters of text (guide: {limit}).",
                nodes=[node.id]))
        if node.type in ("process", "predefined_process", "manual_operation", "preparation") \
                and text.endswith("?"):
            out.append(finding(
                "TXT-05", "warning",
                f"{node.describe()} is phrased as a question ('{text}'); a question in a process "
                "symbol hides a Decision.", nodes=[node.id]))
        if node.type == "decision" and text and not looks_like_condition(text):
            out.append(finding(
                "TXT-06", "info",
                f"Decision '{node.id}' text '{text}' does not read as a condition; phrase it as "
                "a closed question or comparison.", nodes=[node.id]))


def _check_symbols(fc: Flowchart, ctx: FlowContext, out: List[Dict[str, object]],
                   strict: bool) -> None:
    chart = fc.chart_type
    for node in ctx.flow_nodes:
        if node.striped:
            if node.type not in STRIPABLE:
                out.append(finding(
                    "SYM-04", "error",
                    f"{node.describe()} is striped, but only process and data symbols carry a "
                    "detailed-representation stripe.", nodes=[node.id]))
            elif not node.detail_ref:
                out.append(finding(
                    "SYM-04", "warning",
                    f"{node.describe()} is striped but names no detailed representation.",
                    nodes=[node.id], fix="Set detail_ref to the identifier of the detailed chart."))
            elif node.type == "predefined_process":
                out.append(finding(
                    "SYM-05", "info",
                    f"{node.describe()} is striped; a Predefined process already states that its "
                    "steps are specified elsewhere.", nodes=[node.id]))
        if node.multiple and node.type not in kb.DATA_FAMILY:
            out.append(finding(
                "SYM-07", "warning",
                f"{node.describe()} uses the multiple-symbol convention, which applies to data "
                "symbols only.", nodes=[node.id]))

    if strict:
        if chart == "program":
            misplaced = ctx.nodes_of(*kb.PROGRAM_CHART_DISCOURAGED)
            if misplaced:
                listing = ", ".join(f"{n.type} '{n.id}'" for n in misplaced[:8])
                out.append(finding(
                    "SYM-06", "warning",
                    "Media-specific or manual symbols in a program flowchart: " + listing
                    + ". Program flowcharts show control flow; use the basic Data symbol or set "
                      "chart_type to 'system'.", nodes=_ids(misplaced)))
        elif chart in ("program_network", "system_resources"):
            misplaced = ctx.nodes_of(*kb.STRUCTURE_CHART_DISCOURAGED)
            if misplaced:
                out.append(finding(
                    "SYM-06", "warning",
                    f"{kb.CHART_TYPES[chart]['name']}s show structure, not decision logic: "
                    + _fmt(_ids(misplaced)) + ".", nodes=_ids(misplaced)))
        legacy = ctx.nodes_of("off_page_connector")
        if legacy:
            out.append(finding(
                "CON-04", "warning",
                f"Off-page connector(s) {_fmt(_ids(legacy))} use the ANSI X3.5-1970 pentagon, "
                "which ISO 5807 does not define.", nodes=_ids(legacy)))

    ellipses = ctx.nodes_of("ellipsis")
    if ellipses and chart == "program":
        out.append(finding(
            "SYM-12", "info",
            f"Ellipsis {_fmt(_ids(ellipses))} omits symbols; make sure no decision logic or "
            "error handling is hidden.", nodes=_ids(ellipses)))


def _check_terminators(ctx: FlowContext,
                       out: List[Dict[str, object]]) -> Tuple[List[Node], List[Node]]:
    starts: List[Node] = []
    ends: List[Node] = []
    for node in ctx.nodes_of("terminator"):
        i, o = ctx.indeg[node.id], ctx.outdeg[node.id]
        if i == 0 and o == 0:
            out.append(finding("SYM-08", "error",
                               f"Terminator '{node.id}' is not connected to the flow.",
                               nodes=[node.id]))
        elif i > 0 and o > 0:
            out.append(finding(
                "SYM-08", "error",
                f"Terminator '{node.id}' has both incoming and outgoing flowlines; a Terminator "
                "is either a start or an end.", nodes=[node.id]))
        else:
            if o > 1:
                out.append(finding(
                    "SYM-08", "error",
                    f"Start Terminator '{node.id}' has {o} outgoing flowlines; it has exactly one.",
                    nodes=[node.id]))
            (starts if i == 0 else ends).append(node)
    return starts, ends


def _check_decisions(ctx: FlowContext, out: List[Dict[str, object]]) -> None:
    for node in ctx.nodes_of("decision"):
        exits = ctx.out_edges[node.id]
        if len(exits) < 2:
            out.append(finding(
                "SYM-09", "error",
                f"Decision '{node.id}' has {len(exits)} exit(s); a Decision has at least two "
                "alternative exits.", nodes=[node.id]))
        unlabeled = [e for e in exits if not e.label]
        if unlabeled:
            out.append(finding(
                "TXT-03", "error",
                f"Decision '{node.id}' has {len(unlabeled)} unlabelled exit(s).",
                nodes=[node.id], edges=[e.ref() for e in unlabeled]))
        labels = [norm_label(e.label) for e in exits if e.label]
        duplicates = sorted(lbl for lbl, count in Counter(labels).items() if count > 1)
        if duplicates:
            out.append(finding(
                "TXT-03", "error",
                f"Decision '{node.id}' uses the same outcome label more than once: "
                + ", ".join(repr(d) for d in duplicates) + ".", nodes=[node.id]))
        if len(exits) >= 2 and len({e.target for e in exits}) == 1:
            out.append(finding(
                "STR-07", "warning",
                f"Every exit of Decision '{node.id}' leads to '{exits[0].target}'; the decision "
                "has no effect.", nodes=[node.id]))
        if len(exits) >= 2 and not unlabeled and not duplicates:
            if len(exits) == 2:
                first, second = exits[0].label, exits[1].label
                if not complementary(first, second):
                    out.append(finding(
                        "STR-06", "info",
                        f"Check that the exits of Decision '{node.id}' ('{first}' / '{second}') "
                        "are mutually exclusive and cover every outcome.", nodes=[node.id]))
            elif not any(is_default_label(e.label) for e in exits):
                out.append(finding(
                    "STR-06", "warning",
                    f"Multi-way Decision '{node.id}' has {len(exits)} exits but no "
                    "'otherwise' exit for unexpected values.", nodes=[node.id],
                    fix="Add an exit labelled 'Otherwise' that handles every other value."))


def _check_branching(ctx: FlowContext, out: List[Dict[str, object]]) -> None:
    exempt = ("decision", "parallel_mode", "terminator") + kb.CONNECTOR_TYPES
    for node in ctx.flow_nodes:
        if node.type in exempt:
            continue
        exits = ctx.out_edges[node.id]
        if len(exits) > 1:
            out.append(finding(
                "FLW-06", "error",
                f"{node.describe()} has {len(exits)} outgoing flowlines; only Decisions and "
                "Parallel mode may branch.", nodes=[node.id], edges=[e.ref() for e in exits]))
    for edge in ctx.flow_edges:
        source = ctx.by_id[edge.source]
        if source.type != "decision" and edge.label and is_outcome_label(edge.label):
            out.append(finding(
                "FLW-06", "info",
                f"Flowline {edge.ref()} leaves a non-Decision symbol with outcome label "
                f"'{edge.label}'; a condition is being tested without a Decision.",
                nodes=[edge.source], edges=[edge.ref()],
                fix="Insert a Decision that states the condition."))


def _check_parallel_and_loops(ctx: FlowContext, out: List[Dict[str, object]]) -> None:
    for node in ctx.nodes_of("parallel_mode"):
        if ctx.indeg[node.id] < 2 and ctx.outdeg[node.id] < 2:
            out.append(finding(
                "SYM-10", "warning",
                f"Parallel mode '{node.id}' has a single entry and a single exit; it "
                "synchronizes nothing.", nodes=[node.id]))

    groups: Dict[str, List[Node]] = defaultdict(list)
    for node in ctx.nodes_of("loop_limit"):
        if not node.loop_id:
            out.append(finding(
                "SYM-11", "error", f"Loop limit '{node.id}' has no loop identifier (loop_id).",
                nodes=[node.id]))
            continue
        groups[node.loop_id.casefold()].append(node)
    for members in groups.values():
        name = members[0].loop_id
        if len(members) == 1:
            out.append(finding(
                "SYM-11", "error",
                f"Loop limit '{members[0].id}' (loop '{name}') has no matching "
                f"{'end' if members[0].role != 'end' else 'beginning'} part.",
                nodes=_ids(members)))
            continue
        if len(members) > 2:
            out.append(finding(
                "SYM-11", "error",
                f"Loop identifier '{name}' is used by {len(members)} loop limit symbols; a loop "
                "has exactly two parts.", nodes=_ids(members)))
            continue
        first, second = members
        if first.role == second.role:
            out.append(finding(
                "SYM-11", "error",
                f"Both parts of loop '{name}' have role '{first.role}'.", nodes=_ids(members)))
            continue
        begin, end = (first, second) if first.role == "begin" else (second, first)
        if begin.role_inferred or end.role_inferred:
            out.append(finding(
                "SYM-11", "info",
                f"Loop '{name}': roles inferred as begin='{begin.id}', end='{end.id}'.",
                nodes=[begin.id, end.id], fix="State role 'begin'/'end' explicitly."))
        if end.id not in reachable([begin.id], ctx.graph.succ):
            out.append(finding(
                "SYM-11", "error",
                f"The end part '{end.id}' of loop '{name}' cannot be reached from its beginning "
                f"part '{begin.id}'.", nodes=[begin.id, end.id]))


def _check_structure(fc: Flowchart, ctx: FlowContext, out: List[Dict[str, object]],
                     starts: List[Node], ends: List[Node]) -> None:
    program = fc.chart_type == "program"
    boundary = {"terminator", "ellipsis"} | set(kb.CONNECTOR_TYPES)
    if not program:
        boundary |= set(kb.DATA_FAMILY)
    for node in ctx.flow_nodes:
        if node.type in boundary:
            continue
        i, o = ctx.indeg[node.id], ctx.outdeg[node.id]
        if i == 0 and o == 0:
            out.append(finding(
                "STR-01", "error", f"{node.describe()} is not connected to any flowline.",
                nodes=[node.id]))
        elif i == 0:
            out.append(finding(
                "STR-01", "error",
                f"Flow starts at {node.describe()} without a start Terminator (nothing leads "
                "into it).", nodes=[node.id]))
        elif o == 0:
            out.append(finding(
                "STR-01", "error",
                f"Flow stops at {node.describe()}: it has no outgoing flowline and is not an end "
                "Terminator or out-connector.", nodes=[node.id]))
    if program:
        if not starts and not ctx.remote_entries:
            out.append(finding("STR-01", "error",
                               "The program flowchart has no start Terminator.",
                               fix="Add a Terminator 'Start' with one outgoing flowline."))
        if not ends and not ctx.remote_exits:
            out.append(finding("STR-01", "error",
                               "The program flowchart has no end Terminator.",
                               fix="Add a Terminator 'End' that every path reaches."))
        if len(starts) > 1:
            out.append(finding(
                "STR-02", "warning",
                f"The program flowchart has {len(starts)} start Terminators "
                f"({_fmt(_ids(starts))}).", nodes=_ids(starts)))

    graph = ctx.graph
    severity = "error" if program else "warning"
    reach = reachable(graph.sources(), graph.succ)
    unreachable = [i for i in ctx.ids if i not in reach]
    if unreachable:
        out.append(finding(
            "STR-03", "error",
            f"{len(unreachable)} symbol(s) cannot be reached from any entry point: "
            f"{_fmt(unreachable)}.", nodes=unreachable))

    trapped: Set[str] = set()
    for component in strongly_connected_components(ctx.ids, graph.succ):
        if len(component) < 2:
            continue
        members = set(component)
        leaves = any(t not in members for s in component for t in graph.succ[s])
        if leaves:
            continue
        ordered = [i for i in ctx.ids if i in members]
        has_decision = any(ctx.by_id[i].type == "decision" for i in ordered)
        reason = ("none of its Decisions has an exit that leaves the loop" if has_decision
                  else "it contains no Decision")
        out.append(finding(
            "STR-05", severity, f"Closed loop {_fmt(ordered)} can never be left: {reason}.",
            nodes=ordered))
        trapped |= members

    can_finish = reachable(graph.sinks(), graph.pred)
    stuck = [i for i in ctx.ids if i not in can_finish and i not in trapped and i in reach]
    if stuck:
        out.append(finding(
            "STR-04", severity,
            f"No path from {_fmt(stuck)} reaches an end: these symbols lead only into a closed "
            "loop.", nodes=stuck))


def _neighbors_through_connectors(ctx: FlowContext, start: str, forward: bool) -> List[Node]:
    adjacency = ctx.graph.succ if forward else ctx.graph.pred
    result: List[Node] = []
    seen = {start}
    stack = list(adjacency[start])
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        node = ctx.by_id[current]
        if node.type in kb.CONNECTOR_TYPES or node.type == "ellipsis":
            stack.extend(adjacency[current])
        else:
            result.append(node)
    return result


def _check_data_alternation(ctx: FlowContext, out: List[Dict[str, object]]) -> None:
    for node in ctx.nodes_of("process", "predefined_process", "manual_operation"):
        inputs = _neighbors_through_connectors(ctx, node.id, forward=False)
        outputs = _neighbors_through_connectors(ctx, node.id, forward=True)
        missing = []
        if not any(n.type in kb.DATA_FAMILY for n in inputs):
            missing.append("input")
        if not any(n.type in kb.DATA_FAMILY for n in outputs):
            missing.append("output")
        if missing:
            out.append(finding(
                "STR-09", "warning",
                f"{node.describe()} has no data symbol on its {' or '.join(missing)} side.",
                nodes=[node.id]))


def _check_layout(fc: Flowchart, ctx: FlowContext, out: List[Dict[str, object]]) -> None:
    if fc.direction in ("BT", "RL"):
        out.append(finding(
            "FLW-01", "warning",
            f"Direction {fc.direction} reverses the normal flow (top-to-bottom, left-to-right).",
            fix="Use direction TB or LR."))
    pages: Dict[str, List[str]] = defaultdict(list)
    for node in ctx.flow_nodes:
        pages[node.page or ""].append(node.id)
    for page, members in sorted(pages.items()):
        if len(members) > PAGE_SYMBOL_LIMIT:
            where = f"Page '{page}'" if page else "The chart"
            out.append(finding(
                "LAY-01", "warning",
                f"{where} holds {len(members)} symbols (guide: {PAGE_SYMBOL_LIMIT} per page).",
                nodes=members[:5]))
    if not fc.title:
        out.append(finding("LAY-05", "info", "The chart has no title."))
