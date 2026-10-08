"""Mermaid.js output and input for ISO 5807 flowcharts.

``extended`` syntax (default) uses the shape catalogue of Mermaid >= 11.3
(``id@{ shape: ..., label: "..." }``), which covers almost every ISO 5807
symbol. ``classic`` syntax uses the bracket shapes every Mermaid version
understands and marks approximated symbols with ``iso_*`` classes.

The ``iso_*`` classes also make the output parseable again, so a chart
round-trips through ``generate`` and ``parse_mermaid``.
"""

from __future__ import annotations

import html
import json
import re
from collections import OrderedDict, defaultdict
from typing import Dict, List, NamedTuple, Optional, Tuple

from . import knowledge as kb
from .model import Flowchart, Node
from .report import finding

MIN_EXTENDED_VERSION = "11.3.0"  # verified with 11.3.0, 11.12.0 and 12.1.0
MIN_CLASSIC_VERSION = "10.4.0"  # verified with 10.4.0, 10.9.1, 11.x and 12.1.0

EXTENDED_SHAPES: Dict[str, str] = {
    "terminator": "stadium",
    "process": "rect",
    "predefined_process": "fr-rect",
    "manual_operation": "trap-t",
    "preparation": "hex",
    "decision": "diam",
    "parallel_mode": "fork",
    "loop_limit": "notch-pent",
    "data": "lean-r",
    "stored_data": "bow-rect",
    "internal_storage": "win-pane",
    "sequential_access_storage": "dbl-circ",
    "direct_access_storage": "h-cyl",
    "document": "doc",
    "manual_input": "sl-rect",
    "card": "notch-rect",
    "punched_tape": "flag",
    "display": "curv-trap",
    "connector": "circle",
    "off_page_connector": "odd",
    "annotation": "brace",
    "ellipsis": "text",
    "unknown": "rect",
}

CLASSIC_SHAPES: Dict[str, Tuple[str, str]] = {
    "terminator": ("([", "])"),
    "process": ("[", "]"),
    "predefined_process": ("[[", "]]"),
    "manual_operation": ("[\\", "/]"),
    "preparation": ("{{", "}}"),
    "decision": ("{", "}"),
    "parallel_mode": ("[", "]"),
    "loop_limit": ("[/", "\\]"),
    "data": ("[/", "/]"),
    "stored_data": ("[(", ")]"),
    "internal_storage": ("[", "]"),
    "sequential_access_storage": ("(((", ")))"),
    "direct_access_storage": ("[(", ")]"),
    "document": ("[", "]"),
    "manual_input": ("[", "]"),
    "card": ("[", "]"),
    "punched_tape": ("[", "]"),
    "display": ("[", "]"),
    "connector": ("((", "))"),
    "off_page_connector": (">", "]"),
    "annotation": ("[", "]"),
    "ellipsis": ("[", "]"),
    "unknown": ("[", "]"),
}
LOOP_END_CLASSIC = ("[\\", "/]")

# Types whose shape alone identifies them when the chart is parsed again.
EXTENDED_UNIQUE = set(kb.NODE_TYPES) - {"sequential_access_storage", "ellipsis"}
CLASSIC_UNIQUE = {"terminator", "process", "predefined_process", "manual_operation",
                  "preparation", "decision", "data", "connector"}

CLASS_STYLES = {
    "iso_annotation": "fill:none,stroke-dasharray:4 3",
    "iso_ellipsis": "fill:none,stroke:none",
    "iso_parallel_mode": "stroke-width:4px",
}

RESERVED_IDS = {"end", "graph", "flowchart", "subgraph", "style", "classdef", "class", "click",
                "linkstyle", "direction", "default", "call", "href", "callback"}
LEXER_KEYWORDS = RESERVED_IDS | {"interpolate", "flowchart-elk"}

_ELLIPSIS_LABELS = {"...", "…", "⋯", "···"}


# ------------------------------------------------------------------ output


def _mermaid_id(raw: str, used: set, syntax: str = "extended") -> str:
    candidate = re.sub(r"[^A-Za-z0-9_]", "_", raw)
    if syntax == "classic":
        # Mermaid 9/10 lexers read a keyword after '_' (e.g. 'loop_end') as the keyword;
        # capitalised keywords are safe.
        candidate = "_".join(part.capitalize() if part.lower() in LEXER_KEYWORDS else part
                             for part in candidate.split("_"))
    lowered = candidate.lower()
    if not candidate or candidate[0].isdigit() or lowered in RESERVED_IDS \
            or lowered.startswith("end"):
        candidate = "n_" + candidate
    base, counter = candidate, 2
    while candidate in used:
        candidate = f"{base}_{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def mermaid_ids(fc: Flowchart, syntax: str = "extended") -> Dict[str, str]:
    """The Mermaid node id used for each symbol id (sanitized, unique)."""
    used: set = set()
    return {node.id: _mermaid_id(node.id, used, syntax) for node in fc.nodes}


def _escape(text: str) -> str:
    """Escape text for a double-quoted Mermaid label (entity codes, <br> line breaks)."""
    value = text.replace("\r\n", "\n").replace("#", "#35;").replace('"', "#34;")
    value = value.replace("<", "#60;").replace(">", "#62;")
    return value.replace("\n", "<br>")


def _escape_edge(text: str) -> str:
    return _escape(text).replace("|", "#124;")


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _label(node: Node) -> str:
    text = node.text
    if node.type == "loop_limit" and node.loop_id:
        text = f"{node.loop_id}: {text}" if text else node.loop_id
    if node.type == "ellipsis" and not text:
        text = "..."
    if node.striped and node.detail_ref:
        text = f"{node.detail_ref}\n{text}" if text else node.detail_ref
    return text


def _classes(node: Node, syntax: str) -> List[str]:
    classes: List[str] = []
    unique = EXTENDED_UNIQUE if syntax == "extended" else CLASSIC_UNIQUE
    if node.type not in unique and node.type != "unknown":
        if not (node.type == "ellipsis" and syntax == "extended"
                and _label(node) in _ELLIPSIS_LABELS):
            classes.append(f"iso_{node.type}")
    if node.type == "loop_limit" and node.role in ("begin", "end"):
        classes.append(f"iso_loop{node.role}")
    if node.striped:
        classes.append("iso_striped")
    if node.multiple and not (syntax == "extended" and node.type in ("document", "process")):
        classes.append("iso_multiple")
    if node.off_page and node.type == "connector":
        classes.append("iso_off_page")
    return classes


def _extended_shape(node: Node) -> str:
    if node.striped and node.type == "process":
        return "div-rect"
    if node.multiple and node.type == "document":
        return "docs"
    if node.multiple and node.type == "process":
        return "st-rect"
    return EXTENDED_SHAPES.get(node.type, "rect")


def generate(fc: Flowchart, syntax: str = "extended",
             include_title: bool = True) -> Tuple[str, List[str]]:
    """Render a normalized flowchart as Mermaid code; return (code, fidelity notes)."""
    if syntax not in ("extended", "classic"):
        raise ValueError("syntax must be 'extended' or 'classic'")
    lines: List[str] = []
    title = _one_line(fc.title)
    if include_title and title and syntax == "extended":
        lines += ["---", f"title: {json.dumps(title, ensure_ascii=False)}", "---"]
    lines.append(f"flowchart {fc.direction}")
    chart_name = kb.CHART_TYPES[fc.chart_type]["name"]
    lines.append(f"    %% {kb.STANDARD} {chart_name.lower()} (generated by iso5807-flowchart)")
    if include_title and title:
        if syntax == "classic":
            lines.append(f"    %% Title: {title}")
        else:
            lines.append(f"    accTitle: {title}")
            lines.append(f"    accDescr: {chart_name} drawn with {kb.STANDARD} symbols")

    ids = mermaid_ids(fc, syntax)
    class_members: Dict[str, List[str]] = defaultdict(list)
    for node in fc.nodes:
        mid = ids[node.id]
        label = _escape(_label(node))
        if syntax == "extended":
            lines.append(f'    {mid}@{{ shape: {_extended_shape(node)}, label: "{label}" }}')
        else:
            opener, closer = CLASSIC_SHAPES.get(node.type, ("[", "]"))
            if node.type == "loop_limit" and node.role == "end":
                opener, closer = LOOP_END_CLASSIC
            lines.append(f'    {mid}{opener}"{label}"{closer}')
        for cls in _classes(node, syntax):
            class_members[cls].append(mid)

    for edge in fc.edges:
        source, target = ids[edge.source], ids[edge.target]
        label = edge.label
        if edge.kind == "dashed":
            arrow = "-.-"
        elif edge.kind == "communication_link":
            arrow = "-.->"
            label = f"⚡ {label}" if label else "⚡"
        elif edge.kind == "control_transfer":
            arrow = "==>"
        else:
            arrow = "-->"
        if label:
            lines.append(f"    {source} {arrow}|{_escape_edge(label)}| {target}")
        else:
            lines.append(f"    {source} {arrow} {target}")
    for node in fc.nodes:
        if node.type == "annotation":
            for ref in node.annotates:
                if ref in ids:
                    lines.append(f"    {ids[ref]} -.- {ids[node.id]}")

    for cls in sorted(class_members):
        if cls in CLASS_STYLES:
            lines.append(f"    classDef {cls} {CLASS_STYLES[cls]}")
    for cls in sorted(class_members):
        lines.append(f"    class {','.join(class_members[cls])} {cls}")

    return "\n".join(lines) + "\n", _fidelity_notes(fc, syntax)


def _fidelity_notes(fc: Flowchart, syntax: str) -> List[str]:
    notes: List[str] = []
    used_types = OrderedDict((n.type, None) for n in fc.nodes)
    if syntax == "extended":
        notes.append(f"Extended shapes need Mermaid >= {MIN_EXTENDED_VERSION}; use "
                     "syntax='classic' for older renderers.")
        for node_type in used_types:
            symbol = kb.SYMBOLS_BY_ID.get(node_type)
            if symbol and symbol["mermaid"].get("fidelity") == "approximate":  # type: ignore[union-attr]
                note = symbol["mermaid"].get("note")  # type: ignore[union-attr]
                if note:
                    notes.append(f"{symbol['name']}: {note}")
    else:
        notes.append(f"Classic syntax renders in Mermaid >= {MIN_CLASSIC_VERSION} (Mermaid "
                     "9.4-10.3 only when edge labels are plain ASCII without | \" # < >).")
        approximated = [t for t in used_types if t not in CLASSIC_UNIQUE and t != "unknown"]
        if approximated:
            notes.append("Classic syntax has no ISO outline for: " + ", ".join(approximated)
                         + ". They are drawn with the nearest bracket shape and tagged with "
                           "iso_* classes.")
    if any(n.striped for n in fc.nodes):
        notes.append("Striped symbols: the detail reference is the first label line (Mermaid "
                     "cannot write text inside the stripe).")
    kinds = {e.kind for e in fc.edges}
    if "communication_link" in kinds:
        notes.append("Communication link: drawn as a dotted arrow labelled with ⚡ (Mermaid "
                     "has no zigzag line).")
    if "control_transfer" in kinds:
        notes.append("Control transfer: drawn as a thick arrow; parsing the code back yields an "
                     "ordinary flowline.")
    if any(n.type == "annotation" for n in fc.nodes):
        notes.append("Annotations are attached with dotted lines (ISO: dashed line).")
    return notes


# ------------------------------------------------------------------- input

_HEADER = re.compile(r"^(flowchart(?:-elk)?|graph)(?:\s+(TB|TD|BT|RL|LR))?\s*;?\s*(.*)$",
                     re.IGNORECASE)
_ID = re.compile(r"\w+", re.UNICODE)
_TEXT_LINK = re.compile(
    r"(?P<open>--|-\.|==)\s+(?P<text>[^|]+?)\s+"
    r"(?P<close>-{2,}>|-{3,}|\.-+>|\.-+|={2,}>|={3,}|--[xo](?=\s|$))")
_LINK = re.compile(
    r"(?P<head><|x|o)?(?P<body>-\.+-|-{2,}|={2,}|~{3,})(?P<tail>>|x(?=[\s|]|$)|o(?=[\s|]|$))?")
_PIPE_LABEL = re.compile(r"\s*\|(?P<label>[^|]*)\|")
_CLASS_SUFFIX = re.compile(r":::([\w-]+)")
_SKIP_KEYWORDS = ("classdef", "style", "linkstyle", "click", "direction", "end")

_CLASSIC_OPENERS: List[Tuple[str, List[Tuple[str, str]]]] = [
    ("(((", [(")))", "dbl-circ")]),
    ("([", [("])", "stadium")]),
    ("((", [("))", "circle")]),
    ("(", [(")", "rounded")]),
    ("[[", [("]]", "fr-rect")]),
    ("[(", [(")]", "cyl")]),
    ("[/", [("/]", "lean-r"), ("\\]", "trap-b")]),
    ("[\\", [("\\]", "lean-l"), ("/]", "trap-t")]),
    ("[", [("]", "rect")]),
    ("{{", [("}}", "hex")]),
    ("{", [("}", "diam")]),
    (">", [("]", "odd")]),
]

# Mermaid shape names (short names and aliases) -> ISO 5807 node type.
_SHAPE_TO_TYPE: Dict[str, str] = {}
for _names, _type in [
    (("stadium", "pill", "terminal"), "terminator"),
    (("rect", "proc", "process", "rectangle"), "process"),
    (("fr-rect", "framed-rectangle", "subproc", "subprocess", "subroutine"), "predefined_process"),
    (("trap-t", "inv-trapezoid", "manual", "trapezoid-top"), "manual_operation"),
    (("hex", "hexagon", "prepare"), "preparation"),
    (("diam", "decision", "diamond", "question"), "decision"),
    (("fork", "join"), "parallel_mode"),
    (("notch-pent", "loop-limit", "notched-pentagon"), "loop_limit"),
    (("lean-r", "in-out", "lean-right", "lean-l", "lean-left", "out-in"), "data"),
    (("bow-rect", "bow-tie-rectangle", "stored-data"), "stored_data"),
    (("win-pane", "internal-storage", "window-pane"), "internal_storage"),
    (("h-cyl", "das", "horizontal-cylinder", "cyl", "cylinder", "database", "db", "lin-cyl",
      "disk", "lined-cylinder"), "direct_access_storage"),
    (("doc", "document", "docs", "documents", "st-doc", "stacked-document", "lin-doc",
      "lined-document", "tag-doc", "tagged-document"), "document"),
    (("sl-rect", "manual-input", "sloped-rectangle"), "manual_input"),
    (("notch-rect", "card", "notched-rectangle"), "card"),
    (("flag", "paper-tape"), "punched_tape"),
    (("curv-trap", "curved-trapezoid", "display"), "display"),
    (("circle", "circ"), "connector"),
    (("dbl-circ", "double-circle", "sm-circ", "small-circle", "start", "fr-circ",
      "framed-circle", "stop"), "terminator"),
    (("odd",), "off_page_connector"),
    (("brace", "brace-l", "comment", "brace-r", "braces"), "annotation"),
    (("div-rect", "div-proc", "divided-process", "divided-rectangle", "lin-rect", "lin-proc",
      "lined-process", "lined-rectangle", "shaded-process", "st-rect", "processes", "procs",
      "stacked-rectangle", "tag-rect", "tag-proc", "tagged-process", "tagged-rectangle"),
     "process"),
]:
    for _name in _names:
        _SHAPE_TO_TYPE[_name] = _type

# Non-ISO outlines whose role is still clear: (ISO type, outline drawn, ISO outline expected).
_APPROXIMATE_SHAPES: Dict[str, Tuple[str, str, str]] = {}
for _names, _entry in [
    (("lean-l", "lean-left", "out-in"),
     ("data", "a parallelogram leaning left", "a parallelogram leaning right")),
    (("cyl", "cylinder", "database", "db", "lin-cyl", "disk", "lined-cylinder"),
     ("direct_access_storage", "a vertical cylinder", "a horizontal cylinder")),
    (("dbl-circ", "double-circle", "sm-circ", "small-circle", "start", "fr-circ",
      "framed-circle", "stop"),
     ("terminator", "a circle", "a stadium")),
    (("lin-rect", "lin-proc", "lined-process", "lined-rectangle", "shaded-process", "tag-rect",
      "tag-proc", "tagged-process", "tagged-rectangle"),
     ("process", "a decorated rectangle", "a plain rectangle")),
    (("lin-doc", "lined-document", "tag-doc", "tagged-document"),
     ("document", "a decorated document", "a rectangle with a wavy bottom edge")),
]:
    for _name in _names:
        _APPROXIMATE_SHAPES[_name] = _entry
_MULTIPLE_SHAPES = {"docs", "documents", "st-doc", "stacked-document", "st-rect", "processes",
                    "procs", "stacked-rectangle"}
_STRIPED_SHAPES = {"div-rect", "div-proc", "divided-process", "divided-rectangle"}
_NON_ISO_SHAPES = {"trap-b", "priority", "trapezoid", "trapezoid-bottom", "tri", "extract",
                   "triangle", "flip-tri", "flipped-triangle", "manual-file", "hourglass",
                   "collate", "delay", "half-rounded-rectangle", "bolt", "com-link",
                   "lightning-bolt", "cross-circ", "summary", "crossed-circle", "cloud", "bang",
                   "f-circ", "filled-circle", "junction"}
_BOUNDARY_WORDS = re.compile(r"^\s*(start|begin|end|stop|exit|return|finish|done)\b",
                             re.IGNORECASE)


class MermaidParseError(ValueError):
    """The text is not a Mermaid flowchart."""


class MermaidParse(NamedTuple):
    model: Dict[str, object]  # the flowchart JSON model
    notes: List[str]  # how the text was read (skipped constructs, assumptions)
    findings: List[Dict[str, object]]  # symbol-outline findings to merge into validation


def _decode_label(raw: str) -> str:
    text = raw.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    if len(text) >= 2 and text[0] == "`" and text[-1] == "`":
        text = text[1:-1]
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)

    def entity(match: "re.Match[str]") -> str:
        code = match.group(1)
        if code.isdigit():
            return chr(int(code))
        return html.unescape(f"&{code};")

    text = re.sub(r"#(\w+);", entity, text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def _split_statements(line: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    quoted = False
    piped = False
    current: List[str] = []
    for char in line:
        if char == '"':
            quoted = not quoted
        elif not quoted:
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth = max(0, depth - 1)
            elif char == "|" and depth == 0:
                piped = not piped
            elif char == ";" and depth == 0 and not piped:
                parts.append("".join(current))
                current = []
                continue
        current.append(char)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


class _Declaration:
    def __init__(self) -> None:
        self.shape: Optional[str] = None
        self.label: Optional[str] = None
        self.classes: List[str] = []
        self.order = 0


class _Parser:
    def __init__(self) -> None:
        self.nodes: "OrderedDict[str, _Declaration]" = OrderedDict()
        self.links: List[Dict[str, object]] = []
        self.notes: List[str] = []

    def node(self, node_id: str) -> _Declaration:
        if node_id not in self.nodes:
            declaration = _Declaration()
            declaration.order = len(self.nodes)
            self.nodes[node_id] = declaration
        return self.nodes[node_id]

    # -- node references -------------------------------------------------
    def parse_node(self, text: str, pos: int) -> Tuple[Optional[str], int]:
        match = _ID.match(text, pos)
        if not match:
            return None, pos
        node_id = match.group(0)
        pos = match.end()
        declaration = self.node(node_id)
        if text.startswith("@{", pos):
            end = self._matching_brace(text, pos + 1)
            props = self._properties(text[pos + 2:end])
            if "shape" in props:
                declaration.shape = props["shape"].strip().lower()
            if "label" in props:
                declaration.label = _decode_label(props["label"])
            pos = end + 1
        else:
            pos = self._classic_shape(text, pos, declaration)
        class_match = _CLASS_SUFFIX.match(text, pos)
        if class_match:
            declaration.classes.append(class_match.group(1))
            pos = class_match.end()
        return node_id, pos

    @staticmethod
    def _matching_brace(text: str, start: int) -> int:
        depth = 0
        quoted = False
        for index in range(start, len(text)):
            char = text[index]
            if char == '"':
                quoted = not quoted
            elif not quoted:
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        return index
        raise MermaidParseError("unterminated '@{' shape definition")

    @staticmethod
    def _properties(body: str) -> Dict[str, str]:
        props: Dict[str, str] = {}
        for match in re.finditer(r'(\w+)\s*:\s*("(?:[^"\\]|\\.)*"|[^,}]+)', body):
            props[match.group(1).lower()] = match.group(2).strip()
        return props

    def _classic_shape(self, text: str, pos: int, declaration: _Declaration) -> int:
        for opener, closers in _CLASSIC_OPENERS:
            if not text.startswith(opener, pos):
                continue
            start = pos + len(opener)
            if text.startswith('"', start):
                quote_end = text.find('"', start + 1)
                if quote_end == -1:
                    continue
                after = quote_end + 1
                for closer, shape in closers:
                    if text.startswith(closer, after):
                        declaration.shape = shape
                        declaration.label = _decode_label(text[start:quote_end + 1])
                        return after + len(closer)
                continue
            best: Optional[Tuple[int, str, str]] = None
            for closer, shape in closers:
                found = text.find(closer, start)
                if found != -1 and (best is None or found < best[0]):
                    best = (found, closer, shape)
            if best is None:
                continue
            found, closer, shape = best
            declaration.shape = shape
            declaration.label = _decode_label(text[start:found])
            return found + len(closer)
        return pos

    # -- links -------------------------------------------------------------
    def parse_link(self, text: str, pos: int) -> Tuple[Optional[Dict[str, object]], int]:
        match = _TEXT_LINK.match(text, pos)
        if match:
            close = match.group("close")
            open_ = match.group("open")
            style = "dotted" if open_ == "-." else "thick" if open_ == "==" else "normal"
            return {"style": style, "arrow": close.endswith(">"),
                    "label": _decode_label(match.group("text"))}, match.end()
        match = _LINK.match(text, pos)
        if not match:
            return None, pos
        body = match.group("body")
        style = ("dotted" if "." in body else "thick" if body.startswith("=")
                 else "invisible" if body.startswith("~") else "normal")
        link: Dict[str, object] = {"style": style, "arrow": match.group("tail") == ">",
                                   "label": ""}
        if match.group("head") or match.group("tail") in ("x", "o"):
            self.notes.append("Bidirectional, cross and circle arrowheads have no ISO 5807 "
                              "meaning; read as ordinary flowlines.")
        pos = match.end()
        pipe = _PIPE_LABEL.match(text, pos)
        if pipe:
            link["label"] = _decode_label(pipe.group("label"))
            pos = pipe.end()
        return link, pos

    def parse_group(self, text: str, pos: int) -> Tuple[List[str], int]:
        members: List[str] = []
        while True:
            pos = _skip_space(text, pos)
            node_id, pos = self.parse_node(text, pos)
            if node_id is None:
                return members, pos
            members.append(node_id)
            after = _skip_space(text, pos)
            if text.startswith("&", after):
                pos = after + 1
                continue
            return members, pos

    def parse_statement(self, statement: str) -> None:
        lowered = statement.lower()
        keyword = lowered.split(None, 1)[0] if lowered.split() else ""
        if keyword == "class":
            parts = statement.split()
            if len(parts) >= 3:
                for node_id in parts[1].split(","):
                    if node_id:
                        self.node(node_id).classes.extend(parts[2].split(","))
            return
        if keyword in _SKIP_KEYWORDS or lowered.startswith(("acctitle", "accdescr")):
            return
        if keyword == "subgraph":
            self.notes.append("Subgraphs are not ISO 5807 constructs; their contents were read, "
                              "the grouping was ignored.")
            return
        pos = 0
        left, pos = self.parse_group(statement, pos)
        if not left:
            self.notes.append(f"Could not read statement: {statement!r}")
            return
        while True:
            pos = _skip_space(statement, pos)
            if pos >= len(statement):
                return
            link, new_pos = self.parse_link(statement, pos)
            if link is None:
                self.notes.append(f"Could not read the rest of statement {statement!r} from "
                                  f"{statement[pos:]!r}")
                return
            right, new_pos = self.parse_group(statement, new_pos)
            if not right:
                self.notes.append(f"Link without target in statement {statement!r}")
                return
            if link["style"] == "invisible":
                self.notes.append("Invisible links (~~~) were ignored.")
            else:
                for source in left:
                    for target in right:
                        self.links.append(dict(link, source=source, target=target))
            left, pos = right, new_pos


def _skip_space(text: str, pos: int) -> int:
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def parse_mermaid(code: str, chart_type: str = "program") -> MermaidParse:
    """Parse a Mermaid flowchart into the JSON flowchart model.

    Raises MermaidParseError if no flowchart header is found.
    """
    lines = code.replace("\r\n", "\n").split("\n")
    title = ""
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index < len(lines) and lines[index].strip() == "---":
        end = index + 1
        while end < len(lines) and lines[end].strip() != "---":
            match = re.match(r"\s*title\s*:\s*(.+?)\s*$", lines[end])
            if match:
                title = _decode_yaml_scalar(match.group(1))
            end += 1
        index = end + 1
    parser = _Parser()
    direction = "TB"
    header_found = False
    in_block = False
    for raw_line in lines[index:]:
        line = raw_line.strip()
        if not line or line.startswith("%%"):
            if line.lower().startswith("%% title:") and not title:
                title = line.split(":", 1)[1].strip()
            continue
        if in_block:
            in_block = "}" not in line
            continue
        if not header_found:
            match = _HEADER.match(line)
            if not match:
                raise MermaidParseError("not a Mermaid flowchart: the first statement must be "
                                        "'flowchart <direction>' or 'graph <direction>'")
            header_found = True
            direction = (match.group(2) or "TB").upper()
            line = match.group(3).strip()
            if not line:
                continue
        lowered = line.lower()
        if lowered.startswith("acctitle"):
            if not title:
                title = line.split(":", 1)[1].strip() if ":" in line else ""
            continue
        if lowered.startswith("accdescr"):
            in_block = "{" in line and "}" not in line
            continue
        for statement in _split_statements(line):
            parser.parse_statement(statement)
    if not header_found:
        raise MermaidParseError("not a Mermaid flowchart: no 'flowchart' or 'graph' header")
    return _to_model(parser, title, chart_type, "TB" if direction == "TD" else direction)


def _decode_yaml_scalar(value: str) -> str:
    value = value.strip()
    if value.startswith('"'):
        try:
            return str(json.loads(value))
        except json.JSONDecodeError:
            return value.strip('"')
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    return value


def _to_model(parser: _Parser, title: str, chart_type: str, direction: str) -> MermaidParse:
    notes = list(dict.fromkeys(parser.notes))
    nodes: List[Dict[str, object]] = []
    types: Dict[str, str] = {}
    findings: List[Dict[str, object]] = []
    for node_id, decl in parser.nodes.items():
        classes = [c for c in decl.classes if c.startswith("iso_")]
        label = decl.label if decl.label is not None else node_id
        shape = decl.shape or "rect"
        node: Dict[str, object] = {"id": node_id}
        node_type: Optional[str] = None
        for cls in classes:
            candidate = cls[len("iso_"):]
            if candidate in kb.NODE_TYPES:
                node_type = candidate
        if node_type is None:
            node_type = _resolve_shape(node_id, shape, label, findings)
            if decl.shape is None:
                notes.append(f"'{node_id}' is used without a shape; read as Process.")
        node["type"] = node_type
        text = label
        if "iso_striped" in classes or shape in _STRIPED_SHAPES:
            first, _, rest = label.partition("\n")
            node["detail_ref"] = first.strip() or True
            text = rest.strip()
        if node_type == "loop_limit":
            loop_id, separator, rest = text.partition(":")
            if separator and 0 < len(loop_id.strip()) <= 20:
                node["loop_id"] = loop_id.strip()
                text = rest.strip()
            elif text:
                node["loop_id"], text = text, ""
            if "iso_loopbegin" in classes or "iso_loop_begin" in classes:
                node["role"] = "begin"
            elif "iso_loopend" in classes or "iso_loop_end" in classes:
                node["role"] = "end"
        if node_type == "ellipsis" and text in _ELLIPSIS_LABELS:
            text = ""
        if text:
            node["text"] = text
        if "iso_multiple" in classes or shape in _MULTIPLE_SHAPES:
            node["multiple"] = True
        if "iso_off_page" in classes:
            node["off_page"] = True
        types[node_id] = node_type
        nodes.append(node)

    by_id = {str(n["id"]): n for n in nodes}
    edges: List[Dict[str, object]] = []
    for link in parser.links:
        source, target = str(link["source"]), str(link["target"])
        label = str(link["label"])
        style = link["style"]
        annotation_end = [x for x in (source, target) if types.get(x) == "annotation"]
        if style == "dotted" and annotation_end:
            note_id = annotation_end[0]
            other = target if note_id == source else source
            if other != note_id:
                refs = by_id[note_id].setdefault("annotates", [])
                if other not in refs:  # type: ignore[operator]
                    refs.append(other)  # type: ignore[union-attr]
                continue
        edge: Dict[str, object] = {"from": source, "to": target}
        if style == "dotted":
            if label.startswith("⚡"):
                edge["kind"] = "communication_link"
                label = label[1:].strip()
            else:
                edge["kind"] = "dashed"
        if label:
            edge["label"] = label
        edges.append(edge)

    model: Dict[str, object] = {}
    if title:
        model["title"] = title
    model.update({"chart_type": chart_type, "direction": direction, "nodes": nodes,
                  "edges": edges})
    return MermaidParse(model, list(dict.fromkeys(notes)), findings)


def _resolve_shape(node_id: str, shape: str, label: str,
                   findings: List[Dict[str, object]]) -> str:
    """Map a Mermaid shape to an ISO type, recording outline misuse as findings."""
    boundary = bool(_BOUNDARY_WORDS.match(label))
    if shape in ("circle", "circ") and boundary:
        findings.append(finding(
            "SYM-01", "error",
            f"'{node_id}' ('{label}') is drawn as a circle, which ISO 5807 reserves for the "
            "Connector; it was read as a Terminator.", nodes=[node_id],
            fix="Draw Terminators as a stadium: id([text]) or shape: stadium."))
        return "terminator"
    if shape in ("rounded", "event"):
        node_type = "terminator" if boundary else "process"
        expected = "a stadium" if boundary else "a plain rectangle"
        findings.append(finding(
            "SYM-03", "warning",
            f"'{node_id}' is drawn as a rounded rectangle, which is not an ISO 5807 outline; "
            f"it was read as a {kb.SYMBOLS_BY_ID[node_type]['name']} (drawn as {expected}).",
            nodes=[node_id]))
        return node_type
    if shape == "text":
        return "ellipsis" if label.strip() in _ELLIPSIS_LABELS else "annotation"
    if shape in _APPROXIMATE_SHAPES:
        node_type, drawn, expected = _APPROXIMATE_SHAPES[shape]
        findings.append(finding(
            "SYM-03", "warning",
            f"'{node_id}' is drawn as {drawn} ('{shape}'), which is not an ISO 5807 outline; it "
            f"was read as a {kb.SYMBOLS_BY_ID[node_type]['name']} (drawn as {expected}).",
            nodes=[node_id]))
        return node_type
    if shape in _NON_ISO_SHAPES or shape not in _SHAPE_TO_TYPE:
        return f"mermaid:{shape}"  # reported as SYM-01 when the model is loaded
    return _SHAPE_TO_TYPE[shape]
