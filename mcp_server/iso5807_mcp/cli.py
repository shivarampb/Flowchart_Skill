"""Command line: run the MCP server, or use the checks directly (skills, CI, scripts)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Dict, List, Optional

from . import __version__
from . import knowledge as kb
from .analyzer import analyze
from .app import create_server
from .mermaid import (MIN_CLASSIC_VERSION, MIN_EXTENDED_VERSION, MermaidParseError, generate,
                      parse_mermaid)
from .model import Flowchart, FlowchartInputError, load_flowchart
from .transport import serve_http, serve_stdio
from .validator import validate

COMMANDS = ("check", "validate", "analyze", "mermaid", "check-mermaid")


def _serve_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="iso5807-mcp",
        description="ANSI/ISO 5807:1985 flowchart MCP server. Serves stdio by default.",
        epilog="Checks without a client: iso5807-mcp {check,validate,analyze,mermaid,"
               "check-mermaid} FILE (use '-' for stdin; see 'iso5807-mcp check --help').")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--http", action="store_true",
                        default=os.environ.get("ISO5807_MCP_TRANSPORT", "").lower() == "http",
                        help="serve Streamable HTTP instead of stdio")
    parser.add_argument("--host", default=os.environ.get("ISO5807_MCP_HOST", "127.0.0.1"),
                        help="HTTP bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("ISO5807_MCP_PORT", "8765")),
                        help="HTTP port (default 8765)")
    parser.add_argument("--path", default=os.environ.get("ISO5807_MCP_PATH", "/mcp"),
                        help="HTTP endpoint path (default /mcp)")
    parser.add_argument("--allow-origin", action="append", default=[], metavar="ORIGIN",
                        help="extra browser Origin allowed (localhost is always allowed)")
    parser.add_argument("--auth-token", default=os.environ.get("ISO5807_MCP_TOKEN"),
                        help="require 'Authorization: Bearer TOKEN' on HTTP requests "
                             "(env ISO5807_MCP_TOKEN)")
    parser.add_argument("--log-level", default=os.environ.get("ISO5807_MCP_LOG_LEVEL", "WARNING"),
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def _tool_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iso5807-mcp",
                                     description="ANSI/ISO 5807:1985 flowchart checks.")
    sub = parser.add_subparsers(dest="command", required=True)
    chart_types = list(kb.CHART_TYPES)

    cmd = sub.add_parser("check", help="validate, analyze and render a flowchart JSON or "
                                       "Mermaid file in one go (human-readable report)")
    cmd.add_argument("file", help="flowchart JSON or Mermaid file, or '-' for stdin")
    cmd.add_argument("--chart-type", choices=chart_types,
                     help="chart type (Mermaid input defaults to program; overrides JSON)")
    cmd.add_argument("--classic", action="store_true",
                     help=f"classic Mermaid syntax (Mermaid >= {MIN_CLASSIC_VERSION})")
    cmd.add_argument("--lenient", action="store_true",
                     help="accept ANSI X3.5 legacy symbols and chart-type mixing")
    cmd.add_argument("--out", metavar="FILE.mmd",
                     help="also write the Mermaid code to FILE.mmd (.mmd or .mermaid)")
    cmd.add_argument("--json", action="store_true", help="print the full JSON results instead")

    for name, help_text in (("validate", "validate a flowchart JSON file (JSON report)"),
                            ("analyze", "analyze a flowchart JSON file (JSON report)")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("file", help="flowchart JSON file, or '-' for stdin")
        if name == "validate":
            cmd.add_argument("--lenient", action="store_true",
                             help="accept ANSI X3.5 legacy symbols and chart-type mixing")
    cmd = sub.add_parser("mermaid", help="render a flowchart JSON file as Mermaid")
    cmd.add_argument("file")
    cmd.add_argument("--classic", action="store_true", help="classic syntax for old Mermaid")
    cmd.add_argument("--no-title", action="store_true")
    cmd.add_argument("--out", metavar="FILE.mmd",
                     help="write the Mermaid code to FILE.mmd as well (.mmd or .mermaid)")
    cmd = sub.add_parser("check-mermaid", help="validate a Mermaid flowchart file (JSON report)")
    cmd.add_argument("file")
    cmd.add_argument("--chart-type", default="program", choices=chart_types)
    cmd.add_argument("--lenient", action="store_true")
    return parser


def _utf8_output() -> None:
    """Pipes on Windows default to a legacy code page; labels may hold any character."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8-sig") as handle:
        return handle.read()


MERMAID_SUFFIXES = (".mmd", ".mermaid")


def _write(path: str, text: str) -> None:
    # The skill pre-approves this script, so it may only ever write Mermaid files.
    if not path.lower().endswith(MERMAID_SUFFIXES):
        raise OSError(f"--out must name a .mmd or .mermaid file, got {path!r}")
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _format_check(fc: Flowchart, report: Dict[str, object], analysis: Dict[str, object],
                  code: str, syntax: str, fidelity: List[str], notes: List[str],
                  out_path: Optional[str]) -> str:
    summary = report["summary"]  # type: ignore[index]
    status = "conformant" if report["valid"] else "NOT conformant: fix every ERROR"
    title = f' "{fc.title}"' if fc.title else ""
    lines = [
        f"ISO 5807 validation: {_plural(summary['errors'], 'error')}, "
        f"{_plural(summary['warnings'], 'warning')}, {summary['info']} info ({status})",
        f"Chart: {kb.CHART_TYPES[fc.chart_type]['name']}{title}; {summary['symbols']} symbols, "
        f"{summary['flowlines']} flowlines",
    ]
    for item in report["findings"]:  # type: ignore[union-attr]
        where = f" [{', '.join(item['nodes'])}]" if item.get("nodes") else ""
        lines.append(f"  {item['severity'].upper():<8}{item['rule_id']}{where}: {item['message']}")
        if item["severity"] != "info":
            lines.append(f"          fix: {item['fix']}")
    metrics = analysis["metrics"]  # type: ignore[index]
    lines += ["", f"Analysis: {_plural(metrics['decisions'], 'decision')}, cyclomatic complexity "
                  f"{metrics['cyclomatic_complexity']} (basis paths to test), "
                  f"{metrics['end_to_end_paths']} end-to-end paths, longest path "
                  f"{metrics['longest_path_symbols']} symbols"]
    for insight in analysis["insights"]:  # type: ignore[union-attr]
        rule = f" {insight['rule_id']}" if insight.get("rule_id") else ""
        lines.append(f"  {insight['severity'].upper():<9}{insight['category']}{rule}: "
                     f"{insight['message']}")
    if notes:
        lines += ["", "Read from Mermaid:"] + [f"  - {note}" for note in notes]
    version = MIN_EXTENDED_VERSION if syntax == "extended" else MIN_CLASSIC_VERSION
    saved = f", saved to {out_path}" if out_path else ""
    lines += ["", f"Mermaid ({syntax} syntax, needs Mermaid >= {version}{saved}):",
              "```mermaid", code.rstrip("\n"), "```"]
    if fidelity:
        lines += ["Fidelity notes:"] + [f"  - {note}" for note in fidelity]
    return "\n".join(lines)


def _check(args: argparse.Namespace) -> int:
    text = _read(args.file)
    notes: List[str] = []
    outline_findings: List[Dict[str, object]] = []
    if text.lstrip().startswith("{"):
        fc = load_flowchart(text, chart_type=args.chart_type)
    else:
        parsed = parse_mermaid(text, chart_type=args.chart_type or "program")
        notes, outline_findings = parsed.notes, parsed.findings
        fc = load_flowchart(parsed.model)
    report = validate(fc, strict=not args.lenient, extra_findings=outline_findings)
    analysis = analyze(fc)
    syntax = "classic" if args.classic else "extended"
    code, fidelity = generate(fc, syntax)
    if args.out:
        _write(args.out, code)
    if args.json:
        _print_json({"validation": report, "analysis": analysis, "mermaid": code,
                     "fidelity_notes": fidelity, "parse_notes": notes})
    else:
        print(_format_check(fc, report, analysis, code, syntax, fidelity, notes, args.out))
    return 0 if report["valid"] else 1


def _run_command(argv: List[str]) -> int:
    _utf8_output()
    args = _tool_parser().parse_args(argv)
    try:
        if args.command == "check":
            return _check(args)
        if args.command == "check-mermaid":
            parsed = parse_mermaid(_read(args.file), chart_type=args.chart_type)
            report = validate(load_flowchart(parsed.model), strict=not args.lenient,
                              extra_findings=parsed.findings)
            _print_json({"parse_notes": parsed.notes, "validation": report})
            return 0 if report["valid"] else 1
        fc = load_flowchart(_read(args.file))
        if args.command == "validate":
            report = validate(fc, strict=not args.lenient)
            _print_json(report)
            return 0 if report["valid"] else 1
        if args.command == "analyze":
            _print_json(analyze(fc))
            return 0
        code, notes = generate(fc, "classic" if args.classic else "extended", not args.no_title)
        if args.out:
            _write(args.out, code)
        sys.stdout.write(code)
        report = validate(fc)
        for note in notes:
            print(f"note: {note}", file=sys.stderr)
        for item in report["findings"]:  # type: ignore[union-attr]
            if item["severity"] != "info":
                print(f"{item['severity']}: {item['rule_id']} {item['message']}", file=sys.stderr)
        return 0 if report["valid"] else 1
    except (OSError, UnicodeDecodeError, FlowchartInputError, MermaidParseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def main(argv: Optional[List[str]] = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in COMMANDS:
        return _run_command(arguments)
    if arguments and arguments[0] == "serve":
        arguments = arguments[1:]
    args = _serve_parser().parse_args(arguments)
    logging.basicConfig(stream=sys.stderr, level=getattr(logging, args.log_level),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    server = create_server()
    if args.http:
        serve_http(server, args.host, args.port, args.path, args.allow_origin, args.auth_token)
    else:
        try:
            serve_stdio(server)
        except KeyboardInterrupt:
            pass
    return 0
