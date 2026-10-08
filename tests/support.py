"""Shared test helpers: import path and small flowchart builders."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "mcp_server"
SERVER_SCRIPT = SERVER_DIR / "server.py"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from iso5807_mcp.model import load_flowchart  # noqa: E402
from iso5807_mcp.validator import validate  # noqa: E402


def node(node_id, node_type, text=None, **extra):
    item = {"id": node_id, "type": node_type, "text": node_id if text is None else text}
    item.update(extra)
    return item


def edge(source, target, label=None, **extra):
    item = {"from": source, "to": target}
    if label is not None:
        item["label"] = label
    item.update(extra)
    return item


def chart(nodes, edges, title="Test chart", **extra):
    data = {"title": title, "nodes": nodes, "edges": edges}
    data.update(extra)
    return data


def report(data, strict=True):
    return validate(load_flowchart(data), strict=strict)


def rule_ids(result, severity=None):
    return {f["rule_id"] for f in result["findings"]
            if severity is None or f["severity"] == severity}


def linear(*middle, start="s", end="e"):
    """Start -> middle... -> End as (nodes, edges); middle items are node dicts."""
    nodes = [node(start, "terminator", "Start")] + list(middle) + [node(end, "terminator", "End")]
    ids = [n["id"] for n in nodes]
    return nodes, [edge(a, b) for a, b in zip(ids, ids[1:])]
