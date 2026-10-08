"""Systemic analysis: loops, redundancy, bottlenecks, failure states, granularity.

These are heuristics that support the skills described in Part 2 of the guide.
They complement - and never replace - the conformance checks of validator.py.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from typing import Dict, List, Optional

from . import knowledge as kb
from .graph import (condensation_paths, dominators, first_matching,
                    strongly_connected_components, weakly_connected_count)
from .model import Flowchart
from .validator import NEGATIVE_LABELS, FlowContext, norm_label

STEP_TYPES = ("process", "predefined_process", "manual_operation", "data", "manual_input")
# Verbs of operations whose failure changes the outcome. Pure output steps (write a
# notice, print, notify) are deliberately absent: they rarely need their own branch.
RISKY_VERBS = re.compile(
    r"^(read|load|fetch|get|retrieve|download|upload|send|transmit|receive|call|invoke|"
    r"request|query|connect|open|parse|import|sync|validate|verify|check|authenticate|"
    r"authori[sz]e|charge|pay|debit|credit|refund|transfer|submit|approve|scan|lock|"
    r"reserve|book|allocate|deploy|install|save|store|update|delete|insert|commit|search|"
    r"find|match)(s|es|ed|ing)?$", re.IGNORECASE)
RISKY_PHRASES = re.compile(r"^(look(s|ed|ing)? up|log(s|ged|ging)? in|sign(s|ed|ing)? in)\b",
                           re.IGNORECASE)


RETRY = re.compile(r"\b(retry|retries|again|repeat|re-?send|resubmit|wait|poll|reconnect|"
                   r"re-?try|try again)\b", re.IGNORECASE)
GUARD = re.compile(r"\b(attempts?|count(er)?|limit|max(imum)?|timeout|time-?out|times|tries|"
                   r"deadline|expired?|n\s*[<>=]|retries\s*[<>=])", re.IGNORECASE)
COUNTER_WORD = re.compile(r"\b(attempts?|tries|retries|count(er)?|iterations?|index)\b",
                          re.IGNORECASE)
COUNTER_UPDATE = re.compile(r"(\b(add|increment|increase|decrement|decrease|subtract|bump|next)"
                            r"\b|\+\+|--|[+-]=|=\s*\w+\s*[+-]\s*1\b)", re.IGNORECASE)
COUNTER_INIT = re.compile(r"(\b(set|init|initiali[sz]e|reset|start)\b|:?=\s*0\b)", re.IGNORECASE)
CODE_LEVEL = re.compile(
    r"(:=|\+\+|--|[+\-*/%]=|==|!=|<=|>=|\b[A-Za-z_]\w*\s*=\s*\S|\b\w+\([^)]*\)|\w\[\w*\]|;\s*$)")
COMPOUND = re.compile(
    r"(\band then\b|\bthen\b|;|\band\s+(send|update|notify|print|save|calculate|create|check|"
    r"validate|write|read|e-?mail|log|close|open|store|display|compute|generate|delete|"
    r"approve|ship|charge|record|file|archive|post)\b)", re.IGNORECASE)


def risky_operation(node_type: str, text: str) -> str:
    """The failure-prone verb a step starts with (TXT-05: verb + object), or ''."""
    words = re.findall(r"[A-Za-z]+", text)
    phrase = RISKY_PHRASES.match(" ".join(words[:2]))
    if phrase:
        return phrase.group(0)
    # Manual operations are often written 'Actor verb object' ("Clerk checks form").
    for word in words[:2] if node_type == "manual_operation" else words[:1]:
        if RISKY_VERBS.match(word):
            return word
    return ""


def _counter_anatomy(component: List[str], leaving: list, by_id, ctx: FlowContext) -> str:
    """A loop whose exit test reads a counter needs the counter set before and updated inside."""
    exit_sources = {e.source if hasattr(e, "source") else e[0] for e in leaving}
    guards = [by_id[i] for i in component if i in exit_sources
              and by_id[i].type == "decision" and COUNTER_WORD.search(by_id[i].text)]
    if not guards:
        return ""
    members = set(component)
    updated = any(COUNTER_UPDATE.search(by_id[i].text) and COUNTER_WORD.search(by_id[i].text)
                  for i in component if by_id[i].type != "decision")
    initialized = any(COUNTER_WORD.search(n.text) and (n.type == "preparation"
                                                      or COUNTER_INIT.search(n.text))
                      for n in ctx.flow_nodes if n.id not in members)
    missing = []
    if not initialized:
        missing.append("nothing before the loop initializes it (add a Preparation such as "
                       "'Set attempts = 0')")
    if not updated:
        missing.append("nothing inside the loop updates it (add a Process such as "
                       "'Add 1 to attempts')")
    if not missing:
        return ""
    guard = guards[0]
    return (f"Loop guard '{guard.text}' ({guard.id}) tests a counter, but " + " and ".join(missing)
            + ": without both, the bound never takes effect.")


def _norm_text(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.casefold()).strip()


def _insight(category: str, severity: str, rule_id: Optional[str], message: str,
             nodes: List[str]) -> Dict[str, object]:
    item: Dict[str, object] = {"category": category, "severity": severity}
    if rule_id:
        item["rule_id"] = rule_id
    item.update({"message": message, "nodes": nodes})
    return item


def analyze(fc: Flowchart) -> Dict[str, object]:
    ctx = FlowContext(fc)
    graph = ctx.graph
    by_id = fc.by_id
    order = {n.id: n.index for n in fc.nodes}
    insights: List[Dict[str, object]] = []

    decisions = ctx.nodes_of("decision")
    loop_limits = ctx.nodes_of("loop_limit")
    loop_pairs = len({n.loop_id.casefold() for n in loop_limits if n.loop_id})
    entries = graph.sources()
    exits = graph.sinks()

    # ------------------------------------------------------------- loops
    components = [sorted(c, key=order.get) for c in
                  strongly_connected_components(ctx.ids, graph.succ) if len(c) > 1]
    loops = []
    for component in components:
        members = set(component)
        leaving = [e for s in component for e in ctx.out_edges[s] if e.target not in members]
        leaving += [(s, t) for s, t in ctx.virtual if s in members and t not in members]
        exit_refs = [e.ref() if hasattr(e, "ref") else f"{e[0]} -> {e[1]}" for e in leaving]
        loops.append({"symbols": component, "exits": exit_refs})
        path = " -> ".join(component)
        if not leaving:
            insights.append(_insight(
                "loop", "warning", "STR-05",
                f"Loop over {path} has no exit: it runs forever once entered.", component))
            continue
        insights.append(_insight(
            "loop", "advisory", "STR-05",
            f"Loop over {path}; leaves via {', '.join(exit_refs)}. Confirm the exit condition "
            "is eventually met (loop variant) and that the loop body is idempotent if retried.",
            component))
        texts = [by_id[i].text for i in component]
        if any(RETRY.search(t) for t in texts) and not any(GUARD.search(t) for t in texts) \
                and not any(by_id[i].type == "preparation" for i in component):
            insights.append(_insight(
                "failure_state", "warning", "STR-08",
                f"Retry loop over {path} has no attempt counter or timeout: a permanent failure "
                "makes it spin forever. Add a 'Attempts < max?' Decision and a failure exit.",
                component))
        counter_problem = _counter_anatomy(component, leaving, by_id, ctx)
        if counter_problem:
            insights.append(_insight("loop", "warning", "STR-05", counter_problem, component))

    # -------------------------------------------------------- redundancy
    groups: Dict[str, List[str]] = defaultdict(list)
    for node in ctx.nodes_of(*STEP_TYPES, "preparation"):
        key = _norm_text(node.text)
        if key:
            groups[key].append(node.id)
    for members in groups.values():
        if len(members) > 1:
            text = by_id[members[0]].text
            insights.append(_insight(
                "redundancy", "advisory", "LAY-03",
                f"Step '{text}' appears {len(members)} times ({', '.join(members)}); define it "
                "once as a Predefined process or merge the paths before it.", members))
    conditions: Dict[str, List[str]] = defaultdict(list)
    for node in decisions:
        key = _norm_text(node.text)
        if key:
            conditions[key].append(node.id)
    component_of = {n: i for i, c in enumerate(components) for n in c}
    for members in conditions.values():
        if len(members) > 1 and len({component_of.get(m, m) for m in members}) > 1:
            insights.append(_insight(
                "redundancy", "advisory", "LAY-03",
                f"Condition '{by_id[members[0]].text}' is tested {len(members)} times "
                f"({', '.join(members)}); test once and keep the result, or restructure.",
                members))
    sequences: Dict[tuple, List[str]] = defaultdict(list)
    for edge in ctx.flow_edges:
        a, b = by_id[edge.source], by_id[edge.target]
        if a.type in STEP_TYPES and b.type in STEP_TYPES and a.text and b.text:
            sequences[(_norm_text(a.text), _norm_text(b.text))].append(f"{a.id}->{b.id}")
    for (first, second), occurrences in sequences.items():
        if len(occurrences) > 1:
            insights.append(_insight(
                "redundancy", "advisory", "LAY-03",
                f"The sequence '{first}' -> '{second}' occurs {len(occurrences)} times "
                f"({', '.join(occurrences)}); factor it into a Predefined process.",
                [p.split("->")[0] for p in occurrences]))

    # -------------------------------------------------------- bottlenecks
    passive = ("terminator",) + kb.CONNECTOR_TYPES
    for node_id in ctx.ids:
        sources = set(graph.pred[node_id])
        if len(sources) >= 3 and by_id[node_id].type not in passive:
            insights.append(_insight(
                "bottleneck", "advisory", None,
                f"{len(sources)} paths converge on {by_id[node_id].describe()}: a delay or "
                "failure there affects all of them; check its capacity and error handling.",
                [node_id]))
    for node in ctx.nodes_of("parallel_mode"):
        if ctx.indeg[node.id] >= 2:
            insights.append(_insight(
                "bottleneck", "advisory", "SYM-10",
                f"Parallel mode '{node.id}' waits for {ctx.indeg[node.id]} concurrent paths: "
                "the slowest branch sets the pace, and a failed branch blocks the join.",
                [node.id]))
    if decisions or loop_limits:
        dom = dominators(entries, graph)
        reachable_exits = [x for x in exits if x in dom]
        if reachable_exits:
            common = set.intersection(*(dom[x] for x in reachable_exits))
            mandatory = [i for i in ctx.ids if i in common and by_id[i].type not in passive]
            if mandatory:
                insights.append(_insight(
                    "bottleneck", "advisory", None,
                    "Every execution path passes through: " + ", ".join(mandatory)
                    + ". These steps are single points of failure; give them explicit failure "
                      "handling and monitoring.", mandatory))
                manual = [i for i in mandatory if by_id[i].type == "manual_operation"]
                if manual:
                    insights.append(_insight(
                        "bottleneck", "warning", None,
                        "Manual operation(s) on every path: " + ", ".join(manual)
                        + ". Human steps on the critical path limit throughput.", manual))

    # ------------------------------------------------------ failure states
    def is_check(node_id: str) -> bool:
        return by_id[node_id].type in ("decision", "loop_limit")

    def is_transparent(node_id: str) -> bool:
        return by_id[node_id].type in kb.CONNECTOR_TYPES

    for node in ctx.nodes_of(*STEP_TYPES):
        verb = risky_operation(node.type, node.text)
        if verb and not first_matching(node.id, graph.succ, is_check, is_transparent, 2):
            insights.append(_insight(
                "failure_state", "warning", "STR-08",
                f"'{node.text}' ({node.id}) can fail ('{verb}'), but no Decision checks its "
                "outcome within the next two steps: the failure path is missing.",
                [node.id]))
    if fc.chart_type in ("program", "system"):
        for node in decisions:
            for edge in ctx.out_edges[node.id]:
                target = by_id[edge.target]
                if norm_label(edge.label) in NEGATIVE_LABELS and target.type == "terminator":
                    insights.append(_insight(
                        "failure_state", "advisory", "STR-08",
                        f"Outcome '{edge.label}' of '{node.text}' ends the flow at once: no "
                        "notification, logging or compensation is modelled.",
                        [node.id, target.id]))
    steps = ctx.nodes_of(*STEP_TYPES, "preparation")
    if fc.chart_type == "program" and len(steps) >= 3 and not decisions and not loop_limits:
        insights.append(_insight(
            "failure_state", "warning", "STR-08",
            f"The chart has {len(steps)} steps but no Decision: it models only the happy path.",
            [n.id for n in steps]))

    # -------------------------------------------------------- granularity
    code_level, business_level = [], []
    for node in ctx.nodes_of("process", "predefined_process", "manual_operation", "data"):
        if not node.text:
            continue
        if CODE_LEVEL.search(node.text):
            code_level.append(node)
        elif len(node.text.split()) >= 2:
            business_level.append(node)
    if code_level and business_level and len(code_level) + len(business_level) >= 3:
        insights.append(_insight(
            "granularity", "advisory", "LAY-02",
            f"Mixed abstraction levels: {len(code_level)} code-level step(s) (e.g. "
            f"'{code_level[0].text}') beside {len(business_level)} business-level step(s) (e.g. "
            f"'{business_level[0].text}'). Keep one level per chart; move code-level detail into "
            "a Predefined process or a lower-level chart.",
            [n.id for n in code_level + business_level]))
    for node in ctx.nodes_of("process", "manual_operation", "data"):
        if COMPOUND.search(node.text):
            insights.append(_insight(
                "granularity", "advisory", "LAY-02",
                f"'{node.text}' ({node.id}) combines several actions; split it, or name the "
                "combined action at one consistent level.", [node.id]))
    lengths = [len(n.text) for n in steps if n.text]
    if len(lengths) >= 4:
        median = statistics.median(lengths)
        longest = max(steps, key=lambda n: len(n.text))
        if len(longest.text) > 40 and len(longest.text) >= 3 * median:
            insights.append(_insight(
                "granularity", "advisory", "LAY-02",
                f"Uneven detail: '{longest.text}' ({len(longest.text)} characters) against a "
                f"median of {int(median)}; move the detail to an Annotation or a lower-level "
                "chart.",
                [longest.id]))
    if len(ctx.flow_nodes) > 30 and not ctx.nodes_of("predefined_process"):
        insights.append(_insight(
            "granularity", "advisory", "LAY-01",
            f"{len(ctx.flow_nodes)} symbols and no Predefined process: decompose the chart.",
            []))

    # ------------------------------------------------------------- metrics
    branching = sum(len(ctx.out_edges[n.id]) - 1 for n in decisions if ctx.out_edges[n.id])
    parts = weakly_connected_count(graph) if ctx.ids else 0
    complexity = branching + loop_pairs + parts
    path_count, capped, longest = condensation_paths(graph) if ctx.ids else (0, False, 0)
    by_type: Dict[str, int] = defaultdict(int)
    for node in fc.nodes:
        by_type[node.type] += 1
    fan_in = max(ctx.ids, key=lambda i: len(set(graph.pred[i])), default=None)
    fan_out = max(ctx.ids, key=lambda i: len(set(graph.succ[i])), default=None)
    process_like = len(ctx.nodes_of(*kb.PROCESS_FAMILY))
    metrics: Dict[str, object] = {
        "symbols": len(ctx.flow_nodes),
        "symbols_by_type": dict(sorted(by_type.items())),
        "flowlines": len(ctx.flow_edges),
        "decisions": len(decisions),
        "loops": {"cycles": len(components), "loop_limit_pairs": loop_pairs, "detail": loops},
        "entry_points": entries,
        "exit_points": exits,
        "cyclomatic_complexity": complexity,
        "basis_paths_to_test": complexity,
        "end_to_end_paths": f">={path_count}" if capped else path_count,
        "longest_path_symbols": longest,
        "max_fan_in": ({"symbol": fan_in, "paths": len(set(graph.pred[fan_in]))}
                       if fan_in else None),
        "max_fan_out": ({"symbol": fan_out, "paths": len(set(graph.succ[fan_out]))}
                        if fan_out else None),
        "decision_density": round(len(decisions) / process_like, 2) if process_like else 0.0,
        "abstraction_profile": {"code_level": len(code_level),
                                "business_level": len(business_level)},
    }

    severity_rank = {"warning": 0, "advisory": 1}
    insights.sort(key=lambda item: severity_rank[str(item["severity"])])
    return {
        "standard": kb.STANDARD,
        "title": fc.title,
        "chart_type": fc.chart_type,
        "metrics": metrics,
        "insights": insights,
        "summary": {
            "warnings": sum(1 for i in insights if i["severity"] == "warning"),
            "advisories": sum(1 for i in insights if i["severity"] == "advisory"),
        },
        "note": "Heuristic analysis of loops, redundancy, bottlenecks, failure states and "
                "granularity. Run validate_flowchart for ISO 5807 conformance.",
    }
