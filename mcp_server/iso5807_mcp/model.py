"""JSON flowchart model: schema, normalization and loading."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import knowledge as kb
from .report import finding


class FlowchartInputError(ValueError):
    """The input cannot be interpreted as a flowchart at all."""


@dataclass
class Node:
    id: str
    type: str  # canonical ISO type, or "unknown"
    text: str = ""
    raw_type: str = ""
    role: Optional[str] = None  # loop_limit only: "begin" | "end"
    role_inferred: bool = False
    loop_id: Optional[str] = None
    annotates: List[str] = field(default_factory=list)
    page: Optional[str] = None
    striped: bool = False
    detail_ref: str = ""
    multiple: bool = False
    off_page: bool = False
    index: int = 0

    @property
    def family(self) -> str:
        if self.type in kb.PROCESS_FAMILY:
            return "process"
        if self.type in kb.DATA_FAMILY:
            return "data"
        if self.type in kb.SPECIAL_FAMILY or self.type in kb.EXTENSION_TYPES:
            return "special"
        return "unknown"

    def describe(self) -> str:
        symbol = kb.SYMBOLS_BY_ID.get(self.type)
        name = str(symbol["name"]) if symbol else "Symbol"
        if self.type == "off_page_connector":
            name = "Off-page connector"
        return f"{name} '{self.id}'"


@dataclass
class Edge:
    source: str
    target: str
    label: str = ""
    kind: str = "flow"
    index: int = 0

    def ref(self) -> str:
        suffix = f" [{self.label}]" if self.label else ""
        return f"{self.source} -> {self.target}{suffix}"


@dataclass
class Flowchart:
    title: str
    chart_type: str
    direction: str
    nodes: List[Node]
    edges: List[Edge]
    findings: List[Dict[str, object]]
    alias_resolutions: Dict[str, str]
    by_id: Dict[str, Node]


NODE_TYPE_DOC = (
    "ISO 5807 symbol. Process family: process, predefined_process, manual_operation, "
    "preparation, decision, parallel_mode, loop_limit. Data family: data, stored_data, "
    "internal_storage, sequential_access_storage, direct_access_storage, document, "
    "manual_input, card, punched_tape, display. Special: terminator, connector, annotation, "
    "ellipsis. Legacy ANSI X3.5: off_page_connector. Common aliases (start, end, io, "
    "diamond, subroutine, ...) are accepted."
)

FLOWCHART_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "description": "A flowchart: symbols (nodes) joined by flowlines (edges).",
    "properties": {
        "title": {"type": "string", "description": "Chart title (LAY-05)."},
        "chart_type": {
            "type": "string",
            "enum": list(kb.CHART_TYPES),
            "default": "program",
            "description": "ISO 5807 chart type; selects which rules apply.",
        },
        "direction": {
            "type": "string",
            "enum": ["TB", "TD", "LR", "BT", "RL"],
            "default": "TB",
            "description": "Main flow direction. ISO 5807 normal flow is TB or LR.",
        },
        "nodes": {
            "type": "array",
            "description": "Symbols of the chart.",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Unique symbol id."},
                    "type": {"type": "string", "description": NODE_TYPE_DOC},
                    "text": {"type": "string", "description": "Text written in the symbol."},
                    "role": {
                        "type": "string",
                        "enum": ["begin", "end"],
                        "description": "loop_limit only: beginning or end part.",
                    },
                    "loop_id": {
                        "type": "string",
                        "description": "loop_limit only: identifier shared by both parts.",
                    },
                    "annotates": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "annotation only: ids of the symbols it explains.",
                    },
                    "page": {"type": "string", "description": "Page the symbol is drawn on."},
                    "detail_ref": {
                        "type": "string",
                        "description": "Striped symbol: identifier of the detailed "
                                       "representation elsewhere in the documentation.",
                    },
                    "multiple": {
                        "type": "boolean",
                        "description": "Data symbols only: several media/files of this kind.",
                    },
                    "off_page": {
                        "type": "boolean",
                        "description": "connector only: continuation on another page.",
                    },
                },
                "required": ["id", "type"],
            },
        },
        "edges": {
            "type": "array",
            "description": "Flowlines between symbols.",
            "items": {
                "type": "object",
                "properties": {
                    "from": {"type": "string", "description": "Source symbol id."},
                    "to": {"type": "string", "description": "Target symbol id."},
                    "label": {
                        "type": "string",
                        "description": "Outcome label; required on every Decision exit.",
                    },
                    "kind": {
                        "type": "string",
                        "enum": list(kb.EDGE_KINDS),
                        "default": "flow",
                        "description": "flow (solid line), dashed (alternative relationship "
                                       "/ annotation), communication_link, control_transfer.",
                    },
                },
                "required": ["from", "to"],
            },
        },
    },
    "required": ["nodes"],
}

_ROLE_ALIASES = {
    "begin": "begin", "beginning": "begin", "start": "begin", "open": "begin", "head": "begin",
    "top": "begin", "end": "end", "close": "end", "stop": "end", "tail": "end",
    "bottom": "end", "finish": "end",
}


def _first(mapping: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def coerce_flowchart(obj: Any) -> Dict[str, Any]:
    """Accept a dict or a JSON string; unwrap a {"flowchart": {...}} wrapper."""
    if isinstance(obj, (bytes, bytearray)):
        obj = obj.decode("utf-8")
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except json.JSONDecodeError as exc:
            raise FlowchartInputError(f"flowchart is not valid JSON: {exc}") from exc
    wrapped = obj.get("flowchart") if isinstance(obj, dict) else None
    if isinstance(wrapped, (dict, str)) and "nodes" not in obj:
        return coerce_flowchart(wrapped)
    if not isinstance(obj, dict):
        raise FlowchartInputError("flowchart must be a JSON object with a 'nodes' array")
    if not isinstance(obj.get("nodes"), list):
        raise FlowchartInputError("flowchart must contain a 'nodes' array (MOD-03)")
    edges = _first(obj, "edges", "flowlines", "links")
    if edges is not None and not isinstance(edges, list):
        raise FlowchartInputError("'edges' must be an array (MOD-03)")
    return obj


def normalize_chart_type(value: Any) -> Optional[str]:
    key = kb.normalize_key(value) if value is not None else "program"
    if key in kb.CHART_TYPES:
        return key
    return kb.CHART_TYPE_ALIASES.get(key)


def normalize_direction(value: Any) -> Optional[str]:
    key = kb.normalize_key(value).upper() if value is not None else "TB"
    return kb.DIRECTION_ALIASES.get(key)


def load_flowchart(obj: Any, chart_type: Optional[str] = None) -> Flowchart:
    """Normalize user input into a Flowchart. Raises FlowchartInputError if unusable."""
    data = coerce_flowchart(obj)
    findings: List[Dict[str, object]] = []
    aliases: Dict[str, str] = {}

    resolved_chart = normalize_chart_type(chart_type if chart_type else data.get("chart_type"))
    if resolved_chart is None:
        findings.append(finding(
            "MOD-03", "warning",
            f"Unknown chart_type {data.get('chart_type')!r}; using 'program'. Valid: "
            + ", ".join(kb.CHART_TYPES), fix="Use one of the five ISO 5807 chart types."))
        resolved_chart = "program"

    direction = normalize_direction(data.get("direction"))
    if direction is None:
        findings.append(finding(
            "MOD-03", "warning", f"Unknown direction {data.get('direction')!r}; using 'TB'.",
            fix="Use TB (top-to-bottom) or LR (left-to-right)."))
        direction = "TB"

    nodes: List[Node] = []
    by_id: Dict[str, Node] = {}
    for position, raw in enumerate(data["nodes"]):
        if not isinstance(raw, dict):
            findings.append(finding("MOD-03", "error", f"nodes[{position}] is not an object."))
            continue
        node_id = _text(_first(raw, "id", "key", "name"))
        if not node_id:
            findings.append(finding("MOD-01", "error", f"nodes[{position}] has no id."))
            continue
        if node_id in by_id:
            findings.append(finding(
                "MOD-01", "error", f"Duplicate symbol id '{node_id}' (nodes[{position}]); "
                "the later definition is ignored.", nodes=[node_id]))
            continue
        raw_type = _first(raw, "type", "symbol", "shape")
        canonical, implied_role = (None, None)
        if raw_type is None:
            findings.append(finding(
                "SYM-01", "error", f"Symbol '{node_id}' has no type.", nodes=[node_id],
                fix="Set 'type' to an ISO 5807 symbol, e.g. 'process' or 'decision'."))
        else:
            canonical, implied_role = kb.resolve_type(raw_type)
            if canonical is None:
                hints = kb.suggest_types(raw_type)
                hint = f" Did you mean: {', '.join(hints)}?" if hints else ""
                findings.append(finding(
                    "SYM-01", "error",
                    f"Symbol '{node_id}' has type {raw_type!r}, which is not an ISO 5807 "
                    f"symbol.{hint}", nodes=[node_id]))
            elif kb.normalize_key(raw_type) != canonical:
                aliases[str(raw_type)] = canonical
        node = Node(
            id=node_id,
            type=canonical or "unknown",
            text=_text(_first(raw, "text", "label", "title", "description")),
            raw_type=_text(raw_type),
            index=position,
        )
        role_value = _first(raw, "role", "part")
        if role_value is not None:
            node.role = _ROLE_ALIASES.get(kb.normalize_key(role_value))
            if node.role is None:
                findings.append(finding(
                    "SYM-11", "error", f"{node.describe()} has role {role_value!r}; use "
                    "'begin' or 'end'.", nodes=[node_id]))
        elif implied_role:
            node.role = implied_role
        loop_id = _first(raw, "loop_id", "loop", "identifier")
        node.loop_id = _text(loop_id) or None
        annotates = _first(raw, "annotates", "attached_to", "annotation_for")
        if isinstance(annotates, (list, tuple)):
            node.annotates = [_text(a) for a in annotates if _text(a)]
        elif annotates is not None and _text(annotates):
            node.annotates = [_text(annotates)]
        page = _first(raw, "page")
        node.page = _text(page) or None
        striped = _first(raw, "detail_ref", "striped", "detail")
        if isinstance(striped, bool):
            node.striped = striped
        elif striped is not None and _text(striped):
            node.striped, node.detail_ref = True, _text(striped)
        node.multiple = bool(_first(raw, "multiple", "stacked"))
        node.off_page = bool(_first(raw, "off_page", "offpage", "cross_page")) or (
            node.type == "off_page_connector")
        nodes.append(node)
        by_id[node_id] = node

    _infer_loop_roles(nodes)

    edges: List[Edge] = []
    for position, raw in enumerate(_first(data, "edges", "flowlines", "links") or []):
        if not isinstance(raw, dict):
            findings.append(finding("MOD-03", "error", f"edges[{position}] is not an object."))
            continue
        source = _text(_first(raw, "from", "source", "start"))
        target = _text(_first(raw, "to", "target", "end"))
        label = _text(_first(raw, "label", "text", "condition", "outcome"))
        if not source or not target:
            findings.append(finding(
                "MOD-02", "error", f"edges[{position}] needs both 'from' and 'to'."))
            continue
        missing = [x for x in (source, target) if x not in by_id]
        if missing:
            findings.append(finding(
                "MOD-02", "error",
                f"Flowline {source} -> {target} references unknown symbol(s): "
                + ", ".join(repr(m) for m in missing) + ".",
                edges=[f"{source} -> {target}"]))
            continue
        kind_raw = _first(raw, "kind", "type", "line")
        kind = kb.EDGE_KIND_ALIASES.get(kb.normalize_key(kind_raw) if kind_raw else "")
        if kind is None:
            findings.append(finding(
                "FLW-08", "error",
                f"Flowline {source} -> {target} has unknown line kind {kind_raw!r}; treated "
                "as an ordinary flowline.", edges=[f"{source} -> {target}"],
                fix="Use kind flow, dashed, communication_link or control_transfer."))
            kind = "flow"
        edges.append(Edge(source=source, target=target, label=label, kind=kind, index=position))

    if not nodes:
        findings.append(finding("MOD-03", "error", "The flowchart contains no symbols."))

    return Flowchart(
        title=_text(data.get("title")),
        chart_type=resolved_chart,
        direction=direction,
        nodes=nodes,
        edges=edges,
        findings=findings,
        alias_resolutions=aliases,
        by_id=by_id,
    )


def _infer_loop_roles(nodes: List[Node]) -> None:
    """Fill in missing begin/end roles of loop-limit pairs (declaration order)."""
    groups: Dict[str, List[Node]] = defaultdict(list)
    for node in nodes:
        if node.type == "loop_limit" and node.loop_id:
            groups[node.loop_id.casefold()].append(node)
    for members in groups.values():
        if len(members) != 2:
            continue
        first, second = members
        if first.role and second.role:
            continue
        if first.role and not second.role:
            second.role = "end" if first.role == "begin" else "begin"
            second.role_inferred = True
        elif second.role and not first.role:
            first.role = "end" if second.role == "begin" else "begin"
            first.role_inferred = True
        else:
            first.role, second.role = "begin", "end"
            first.role_inferred = second.role_inferred = True


def flowchart_to_dict(fc: Flowchart) -> Dict[str, Any]:
    """Serialize a normalized Flowchart back to the JSON model."""
    nodes: List[Dict[str, Any]] = []
    for node in fc.nodes:
        item: Dict[str, Any] = {"id": node.id, "type": node.type}
        if node.text:
            item["text"] = node.text
        if node.type == "loop_limit":
            if node.role:
                item["role"] = node.role
            if node.loop_id:
                item["loop_id"] = node.loop_id
        if node.annotates:
            item["annotates"] = list(node.annotates)
        if node.page:
            item["page"] = node.page
        if node.striped:
            item["detail_ref"] = node.detail_ref or True
        if node.multiple:
            item["multiple"] = True
        if node.off_page and node.type == "connector":
            item["off_page"] = True
        nodes.append(item)
    edges: List[Dict[str, Any]] = []
    for edge in fc.edges:
        item = {"from": edge.source, "to": edge.target}
        if edge.label:
            item["label"] = edge.label
        if edge.kind != "flow":
            item["kind"] = edge.kind
        edges.append(item)
    result: Dict[str, Any] = {}
    if fc.title:
        result["title"] = fc.title
    result.update({"chart_type": fc.chart_type, "direction": fc.direction,
                   "nodes": nodes, "edges": edges})
    return result
