"""Command line: run the MCP server, or use the checks directly (CI, scripts)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import List, Optional

from . import __version__
from .analyzer import analyze
from .app import create_server
from .mermaid import MermaidParseError, generate, parse_mermaid
from .model import FlowchartInputError, load_flowchart
from .transport import serve_http, serve_stdio
from .validator import validate

COMMANDS = ("validate", "analyze", "mermaid", "check-mermaid")


def _serve_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="iso5807-mcp",
        description="ANSI/ISO 5807:1985 flowchart MCP server. Serves stdio by default.",
        epilog="Checks without a client: iso5807-mcp {validate,analyze,mermaid,check-mermaid} "
               "FILE (use '-' for stdin; see 'iso5807-mcp validate --help').")
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
    for name, help_text in (("validate", "validate a flowchart JSON file"),
                            ("analyze", "analyze a flowchart JSON file")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("file", help="flowchart JSON file, or '-' for stdin")
        if name == "validate":
            cmd.add_argument("--lenient", action="store_true",
                             help="accept ANSI X3.5 legacy symbols and chart-type mixing")
    cmd = sub.add_parser("mermaid", help="render a flowchart JSON file as Mermaid")
    cmd.add_argument("file")
    cmd.add_argument("--classic", action="store_true", help="classic syntax for old Mermaid")
    cmd.add_argument("--no-title", action="store_true")
    cmd = sub.add_parser("check-mermaid", help="validate a Mermaid flowchart file")
    cmd.add_argument("file")
    cmd.add_argument("--chart-type", default="program")
    cmd.add_argument("--lenient", action="store_true")
    return parser


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _run_command(argv: List[str]) -> int:
    args = _tool_parser().parse_args(argv)
    try:
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
        sys.stdout.write(code)
        report = validate(fc)
        for note in notes:
            print(f"note: {note}", file=sys.stderr)
        for item in report["findings"]:  # type: ignore[union-attr]
            if item["severity"] != "info":
                print(f"{item['severity']}: {item['rule_id']} {item['message']}", file=sys.stderr)
        return 0 if report["valid"] else 1
    except (OSError, FlowchartInputError, MermaidParseError) as exc:
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
