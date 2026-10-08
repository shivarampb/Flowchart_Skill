"""Finding records shared by the validator and the model loader."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .knowledge import RULES_BY_ID

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def finding(rule_id: str, severity: str, message: str, nodes: Iterable[str] = (),
            edges: Iterable[str] = (), fix: Optional[str] = None) -> Dict[str, object]:
    """Build one finding tied to a rule of the knowledge base."""
    rule = RULES_BY_ID[rule_id]
    if severity not in SEVERITY_ORDER:
        raise ValueError(f"unknown severity {severity!r}")
    item: Dict[str, object] = {
        "rule_id": rule_id,
        "severity": severity,
        "title": rule["title"],
        "basis": rule["basis"],
        "message": message,
    }
    node_list = list(dict.fromkeys(nodes))
    if node_list:
        item["nodes"] = node_list
    edge_list = list(edges)
    if edge_list:
        item["edges"] = edge_list
    item["fix"] = fix or rule["fix"]
    return item


def sort_findings(items: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Errors first, then warnings, then info; stable within a severity."""
    return sorted(items, key=lambda f: SEVERITY_ORDER[str(f["severity"])])


def count_findings(items: Iterable[Dict[str, object]]) -> Dict[str, int]:
    counts = {"errors": 0, "warnings": 0, "info": 0}
    for item in items:
        severity = item["severity"]
        if severity == "error":
            counts["errors"] += 1
        elif severity == "warning":
            counts["warnings"] += 1
        else:
            counts["info"] += 1
    return counts
