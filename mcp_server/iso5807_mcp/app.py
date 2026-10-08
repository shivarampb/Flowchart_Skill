"""The ISO 5807 MCP server: tools, resources and prompts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from . import knowledge as kb
from .analyzer import analyze
from .examples import EXAMPLES
from .mermaid import (MIN_CLASSIC_VERSION, MIN_EXTENDED_VERSION, MermaidParseError, generate,
                      parse_mermaid)
from .model import (FLOWCHART_SCHEMA, Flowchart, FlowchartInputError, load_flowchart,
                    normalize_chart_type)
from .protocol import (Content, McpServer, Prompt, Resource, ResourceTemplate, Tool, ToolError,
                       text_content)
from .validator import validate

SERVER_NAME = "iso5807-flowchart"
SERVER_TITLE = "ANSI/ISO 5807:1985 Flowchart Server"
GUIDE_FILENAME = "ANSI-ISO-5807-Flowchart-Guide.md"

INSTRUCTIONS = """\
Flowchart tools that follow ANSI/ISO 5807:1985.
Workflow for any flowchart you draw or review:
1. Model the chart as JSON: nodes {id, type (ISO symbol), text}, edges {from, to, label}.
   Label every Decision exit; give loop_limit pairs one loop_id; attach annotations with
   'annotates'. Choose chart_type (program, data, system, program_network, system_resources).
2. Call validate_flowchart and fix every error (warnings: fix or justify).
3. Call analyze_flowchart to surface loops, redundancy, bottlenecks and missing failure states.
4. Call generate_mermaid and present its Mermaid code (extended syntax needs Mermaid >= 11.3;
   pass syntax='classic' for older renderers).
For existing Mermaid code call validate_mermaid. Look symbols up with iso5807_symbol_reference
and rules with iso5807_rules. Cite rule IDs (e.g. TXT-03) when explaining fixes.
"""

FLOWCHART_ARG = dict(FLOWCHART_SCHEMA)
FLOWCHART_ARG["description"] = (
    "The flowchart as an object (or a JSON string): {title, chart_type, direction, nodes: "
    "[{id, type, text, ...}], edges: [{from, to, label, kind}]}.")


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def _bool(args: Dict[str, Any], key: str, default: bool) -> bool:
    value = args.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise ToolError(f"'{key}' must be true or false")


def _chart_type(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    resolved = normalize_chart_type(value)
    if resolved is None:
        raise ToolError(f"Unknown chart_type {value!r}; use one of: " + ", ".join(kb.CHART_TYPES))
    return resolved


def _load(args: Dict[str, Any]) -> Flowchart:
    source = args.get("flowchart")
    if source is None and "nodes" in args:
        source = args  # the caller passed the flowchart itself as the arguments
    if source is None:
        raise ToolError("Missing required argument 'flowchart'")
    try:
        return load_flowchart(source)
    except FlowchartInputError as exc:
        raise ToolError(str(exc)) from exc


# ------------------------------------------------------------------ tools


def tool_symbol_reference(args: Dict[str, Any]) -> Content:
    family = args.get("family") or None
    if family is not None and family not in ("process", "data", "line", "special", "legacy"):
        raise ToolError("family must be one of: process, data, line, special, legacy")
    symbol = args.get("symbol") or None
    try:
        data = kb.symbol_reference(symbol, family, _chart_type(args.get("chart_type")))
    except KeyError as exc:
        known = ", ".join(sorted(kb.SYMBOLS_BY_ID))
        raise ToolError(f"Unknown symbol {symbol!r}. Known symbols: {known}") from exc
    return [text_content(_json(data))]


def tool_rules(args: Dict[str, Any]) -> Content:
    category = args.get("category") or None
    if category is not None and category not in kb.RULE_CATEGORIES:
        raise ToolError("category must be one of: " + ", ".join(kb.RULE_CATEGORIES))
    basis = args.get("basis") or None
    rule_id = args.get("rule_id") or None
    try:
        data = kb.rules_reference(category, rule_id, basis)
    except KeyError as exc:
        raise ToolError(f"Unknown rule id {rule_id!r}") from exc
    return [text_content(_json(data))]


def tool_validate(args: Dict[str, Any]) -> Content:
    report = validate(_load(args), strict=_bool(args, "strict", True))
    return [text_content(_json(report))]


def tool_analyze(args: Dict[str, Any]) -> Content:
    return [text_content(_json(analyze(_load(args))))]


def tool_generate_mermaid(args: Dict[str, Any]) -> Content:
    syntax = args.get("syntax") or "extended"
    if syntax not in ("extended", "classic"):
        raise ToolError("syntax must be 'extended' or 'classic'")
    fc = _load(args)
    code, notes = generate(fc, syntax=syntax, include_title=_bool(args, "include_title", True))
    report = validate(fc, strict=_bool(args, "strict", True))
    summary = {
        "standard": kb.STANDARD,
        "syntax": syntax,
        "min_mermaid_version": (MIN_EXTENDED_VERSION if syntax == "extended"
                                else MIN_CLASSIC_VERSION),
        "valid": report["valid"],
        "summary": report["summary"],
        "findings": [f for f in report["findings"] if f["severity"] != "info"],  # type: ignore[index]
        "fidelity_notes": notes,
    }
    header = "Mermaid flowchart" + ("" if report["valid"] else
                                    " (NOT conformant: fix the errors listed below)")
    return [text_content(f"{header}:\n\n```mermaid\n{code}```"), text_content(_json(summary))]


def tool_validate_mermaid(args: Dict[str, Any]) -> Content:
    code = args.get("mermaid")
    if not isinstance(code, str) or not code.strip():
        raise ToolError("Missing required argument 'mermaid' (Mermaid flowchart source)")
    chart_type = _chart_type(args.get("chart_type")) or "program"
    try:
        parsed = parse_mermaid(code, chart_type=chart_type)
    except MermaidParseError as exc:
        raise ToolError(str(exc)) from exc
    report = validate(load_flowchart(parsed.model), strict=_bool(args, "strict", True),
                      extra_findings=parsed.findings)
    return [text_content(_json({"parse_notes": parsed.notes, "validation": report,
                                "flowchart": parsed.model}))]


def _tools() -> List[Tool]:
    strict_arg = {"type": "boolean", "default": True,
                  "description": "Strict ISO 5807 (true) or also accept ANSI X3.5 legacy "
                                 "symbols and chart-type mixing (false)."}
    return [
        Tool(
            "iso5807_symbol_reference", "ISO 5807 symbol reference",
            "Look up ANSI/ISO 5807:1985 flowchart symbols: precise geometry, meaning, when to "
            "use and not use each one, text and flow conventions, and the Mermaid shape. Omit "
            "'symbol' to list all symbols (optionally filtered by family or chart type).",
            {"type": "object", "properties": {
                "symbol": {"type": "string", "description": "Symbol id or alias, e.g. "
                           "'decision', 'predefined_process', 'off-page connector'."},
                "family": {"type": "string",
                           "enum": ["process", "data", "line", "special", "legacy"]},
                "chart_type": {"type": "string", "enum": list(kb.CHART_TYPES),
                               "description": "Only list symbols suited to this chart type."},
            }},
            tool_symbol_reference),
        Tool(
            "iso5807_rules", "ISO 5807 rule book",
            "List the flowcharting rules (symbols, flowlines, connectors, text, structure, "
            "layout) with rule IDs, basis (ISO 5807 provision or professional practice), "
            "severity, rationale and fix. Filter by category, rule_id or basis.",
            {"type": "object", "properties": {
                "category": {"type": "string", "enum": list(kb.RULE_CATEGORIES)},
                "rule_id": {"type": "string", "description": "e.g. 'CON-02'"},
                "basis": {"type": "string", "enum": ["ISO 5807", "Practice", "Schema"]},
            }},
            tool_rules),
        Tool(
            "validate_flowchart", "Validate flowchart against ISO 5807",
            "Check a flowchart model against ANSI/ISO 5807:1985 and flow-integrity rules. "
            "Returns valid=true/false and findings (rule_id, severity, message, nodes, fix). "
            "Fix every error before presenting a flowchart.",
            {"type": "object", "properties": {"flowchart": FLOWCHART_ARG, "strict": strict_arg},
             "required": ["flowchart"]},
            tool_validate),
        Tool(
            "analyze_flowchart", "Analyze flowchart logic",
            "Systemic analysis of a flowchart model: loops and their exits, redundant steps "
            "and conditions, bottlenecks and single points of failure, missing failure states, "
            "abstraction-level drift, plus metrics (cyclomatic complexity = basis paths to "
            "test, end-to-end paths, fan-in/out).",
            {"type": "object", "properties": {"flowchart": FLOWCHART_ARG},
             "required": ["flowchart"]},
            tool_analyze),
        Tool(
            "generate_mermaid", "Generate Mermaid flowchart",
            "Render a flowchart model as Mermaid code using ISO 5807 shapes. 'extended' "
            f"(default) uses Mermaid >= {MIN_EXTENDED_VERSION} shapes that match the ISO "
            f"outlines; 'classic' works in Mermaid >= {MIN_CLASSIC_VERSION}. Also returns the "
            "validation "
            "summary and notes on approximated symbols.",
            {"type": "object", "properties": {
                "flowchart": FLOWCHART_ARG,
                "syntax": {"type": "string", "enum": ["extended", "classic"],
                           "default": "extended"},
                "include_title": {"type": "boolean", "default": True},
                "strict": strict_arg,
            }, "required": ["flowchart"]},
            tool_generate_mermaid),
        Tool(
            "validate_mermaid", "Validate Mermaid flowchart against ISO 5807",
            "Parse existing Mermaid flowchart code (classic or extended shape syntax), map its "
            "shapes to ISO 5807 symbols and validate it. Returns parse notes, the validation "
            "report and the parsed flowchart model (reusable with the other tools).",
            {"type": "object", "properties": {
                "mermaid": {"type": "string", "description": "Mermaid source starting with "
                            "'flowchart' or 'graph'."},
                "chart_type": {"type": "string", "enum": list(kb.CHART_TYPES),
                               "default": "program"},
                "strict": strict_arg,
            }, "required": ["mermaid"]},
            tool_validate_mermaid),
    ]


# -------------------------------------------------------------- resources


def guide_path() -> Optional[Path]:
    candidates = []
    if os.environ.get("ISO5807_GUIDE_PATH"):
        candidates.append(Path(os.environ["ISO5807_GUIDE_PATH"]))
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        candidates.append(Path(os.environ["CLAUDE_PROJECT_DIR"]) / "docs" / GUIDE_FILENAME)
    candidates.append(Path(__file__).resolve().parents[2] / "docs" / GUIDE_FILENAME)
    for path in candidates:
        if path.is_file():
            return path
    return None


def rules_markdown() -> str:
    """Compact Markdown rule book, used when the full guide file is not available."""
    lines = [f"# {kb.STANDARD} flowchart rules", "", f"_{kb.STANDARD_TITLE}_", ""]
    for category, description in kb.RULE_CATEGORIES.items():
        lines += [f"## {description}", ""]
        for rule in kb.RULES:
            if rule["category"] == category:
                lines.append(f"- **{rule['id']}** ({rule['basis']}, {rule['severity']}) "
                             f"{rule['title']}: {rule['rule']}")
        lines.append("")
    lines += ["## Symbols", ""]
    for symbol in kb.SYMBOLS:
        lines.append(f"- **{symbol['name']}** (`{symbol['id']}`): {symbol['geometry']} "
                     f"{symbol['meaning']}")
    return "\n".join(lines) + "\n"


def read_guide() -> str:
    path = guide_path()
    if path is not None:
        return path.read_text(encoding="utf-8")
    return rules_markdown()


def _resources() -> List[Resource]:
    resources = [
        Resource("iso5807://guide", "guide", "ANSI/ISO 5807 flowchart guide",
                 "Rules, syntax and the analysis of the flowcharting skill (Markdown).",
                 "text/markdown", read_guide),
        Resource("iso5807://symbols", "symbols", "Symbol catalogue",
                 "All ISO 5807 symbols with geometry, meaning and Mermaid mapping (JSON).",
                 "application/json", lambda: _json(kb.symbol_reference())),
        Resource("iso5807://rules", "rules", "Rule book",
                 "All rules with IDs, basis, severity, rationale and fix (JSON).",
                 "application/json", lambda: _json(kb.rules_reference())),
        Resource("iso5807://chart-types", "chart-types", "Chart types",
                 "The five ISO 5807 chart types (JSON).",
                 "application/json", lambda: _json(kb.CHART_TYPES)),
        Resource("iso5807://schema/flowchart", "flowchart-schema", "Flowchart JSON schema",
                 "JSON schema of the flowchart model accepted by the tools.",
                 "application/schema+json", lambda: _json(FLOWCHART_SCHEMA)),
    ]
    for name, example in EXAMPLES.items():
        resources.append(Resource(
            f"iso5807://examples/{name}", f"example-{name}", f"Example: {example['title']}",
            "Example flowchart model (JSON).", "application/json",
            lambda example=example: _json(example)))
    return resources


def _read_symbol(value: str) -> Optional[str]:
    try:
        return _json(kb.symbol_reference(value))
    except KeyError:
        return None


def _read_rule(value: str) -> Optional[str]:
    try:
        return _json(kb.rules_reference(rule_id=value))
    except KeyError:
        return None


def _templates() -> List[ResourceTemplate]:
    return [
        ResourceTemplate("iso5807://symbols/{symbol_id}", "symbol", "One symbol",
                         "A single symbol by id or alias, e.g. iso5807://symbols/decision.",
                         "application/json", _read_symbol),
        ResourceTemplate("iso5807://rules/{rule_id}", "rule", "One rule",
                         "A single rule by id, e.g. iso5807://rules/CON-02.",
                         "application/json", _read_rule),
    ]


# ---------------------------------------------------------------- prompts


def _design_prompt(args: Dict[str, str]) -> str:
    chart_type = normalize_chart_type(args.get("chart_type") or "program") or "program"
    chart = kb.CHART_TYPES[chart_type]["name"]
    audience = args.get("audience") or "technical and business readers"
    return f"""Design an {kb.STANDARD} {chart.lower()} for the process below.

Process description:
{args['process_description']}

Audience: {audience}

Work in this order:
1. Boundaries: name the trigger (start Terminator) and every outcome (end Terminators), including failure outcomes.
2. Inventory: list the steps as verb + object at ONE level of abstraction; push finer detail into Predefined processes.
3. Decisions: turn every implicit condition ("if", "unless", "when", "approve", "valid") into a Decision with a testable question and complementary, labelled exits (multi-way: add 'Otherwise').
4. Failure states: after every operation that can fail (input/output, external call, validation, payment, approval) add an outcome Decision and model the failure path; give retry loops a counter or timeout.
5. Loops: show repetition with a Decision back-edge or a loop limit pair; every loop needs an exit.
6. Symbols: choose them with iso5807_symbol_reference (chart_type '{chart_type}'); in program flowcharts use the basic Data symbol for input/output.
7. Model: write the flowchart JSON and call validate_flowchart until it reports no errors; fix or justify warnings.
8. Analyse: call analyze_flowchart and resolve loops without exits, redundancy, bottlenecks and missing failure states.
9. Render: call generate_mermaid and present the Mermaid code, followed by the assumptions you made and the rule IDs you applied.
"""


def _review_prompt(args: Dict[str, str]) -> str:
    return f"""Review the flowchart below for conformance with {kb.STANDARD} and for logical soundness.

{args['flowchart']}

1. If it is Mermaid code call validate_mermaid; if it is a JSON model call validate_flowchart.
2. Call analyze_flowchart on the (parsed) model.
3. Report, citing symbol ids and rule IDs:
   a. Conformance errors and how to fix each one.
   b. Warnings worth fixing.
   c. Logic findings: loops, redundancy, bottlenecks, missing failure states, granularity.
4. Produce a corrected model, validate it, and show the corrected Mermaid code from generate_mermaid.
"""


def _prompts() -> List[Prompt]:
    return [
        Prompt("design_flowchart", "Design an ISO 5807 flowchart",
               "Step-by-step method that turns a process description into a validated "
               "ISO 5807 flowchart and Mermaid diagram.",
               [{"name": "process_description", "description": "The process to chart.",
                 "required": True},
                {"name": "chart_type", "description": "program (default), data, system, "
                 "program_network or system_resources.", "required": False},
                {"name": "audience", "description": "Who will read the chart.",
                 "required": False}],
               _design_prompt),
        Prompt("review_flowchart", "Review a flowchart against ISO 5807",
               "Validate and analyse an existing flowchart (Mermaid or JSON) and propose fixes.",
               [{"name": "flowchart", "description": "Mermaid code or flowchart JSON.",
                 "required": True}],
               _review_prompt),
    ]


def create_server() -> McpServer:
    return McpServer(
        name=SERVER_NAME,
        version=__version__,
        title=SERVER_TITLE,
        instructions=INSTRUCTIONS,
        tools=_tools(),
        resources=_resources(),
        templates=_templates(),
        prompts=_prompts(),
    )
