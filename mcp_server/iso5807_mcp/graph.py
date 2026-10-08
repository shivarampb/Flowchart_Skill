"""Small directed-graph toolkit (no third-party dependencies)."""

from __future__ import annotations

from collections import deque
from typing import Dict, Iterable, List, Optional, Set, Tuple

ROOT = "\x00root"


class FlowGraph:
    """Directed multigraph over symbol ids."""

    def __init__(self, nodes: Iterable[str]) -> None:
        self.nodes: List[str] = list(dict.fromkeys(nodes))
        self.succ: Dict[str, List[str]] = {n: [] for n in self.nodes}
        self.pred: Dict[str, List[str]] = {n: [] for n in self.nodes}

    def add(self, source: str, target: str) -> None:
        self.succ[source].append(target)
        self.pred[target].append(source)

    def sources(self) -> List[str]:
        return [n for n in self.nodes if not self.pred[n]]

    def sinks(self) -> List[str]:
        return [n for n in self.nodes if not self.succ[n]]


def reachable(starts: Iterable[str], adjacency: Dict[str, List[str]]) -> Set[str]:
    """All nodes reachable from ``starts`` (inclusive) following ``adjacency``."""
    seen: Set[str] = set()
    queue = deque(s for s in starts if s in adjacency)
    seen.update(queue)
    while queue:
        node = queue.popleft()
        for nxt in adjacency[node]:
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def strongly_connected_components(nodes: Iterable[str],
                                  succ: Dict[str, List[str]]) -> List[List[str]]:
    """Tarjan's algorithm, iterative so that large charts cannot hit the recursion limit."""
    index: Dict[str, int] = {}
    low: Dict[str, int] = {}
    on_stack: Set[str] = set()
    stack: List[str] = []
    components: List[List[str]] = []
    counter = 0
    for root in nodes:
        if root in index:
            continue
        work: List[Tuple[str, int]] = [(root, 0)]
        while work:
            node, position = work[-1]
            if position == 0 and node not in index:
                index[node] = low[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            successors = succ.get(node, [])
            if position < len(successors):
                work[-1] = (node, position + 1)
                nxt = successors[position]
                if nxt not in index:
                    work.append((nxt, 0))
                elif nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component: List[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                components.append(component)
    return components


def dominators(entries: Iterable[str], graph: FlowGraph) -> Dict[str, Set[str]]:
    """Dominator sets for every node reachable from ``entries``.

    A virtual root precedes all entries, so with several entries a node only
    dominates what every path from every entry must pass through.
    """
    entry_list = [e for e in entries if e in graph.succ]
    reach = reachable(entry_list, graph.succ)
    order = [n for n in graph.nodes if n in reach]
    preds: Dict[str, List[str]] = {n: [p for p in graph.pred[n] if p in reach] for n in order}
    for entry in entry_list:
        preds[entry].append(ROOT)
    universe = set(order) | {ROOT}
    dom: Dict[str, Set[str]] = {n: set(universe) for n in order}
    dom[ROOT] = {ROOT}
    changed = True
    while changed:
        changed = False
        for node in order:
            sets = [dom[p] for p in preds[node]]
            new = set.intersection(*sets) if sets else set()
            new = new | {node}
            if new != dom[node]:
                dom[node] = new
                changed = True
    return {n: dom[n] - {ROOT} for n in order}


def weakly_connected_count(graph: FlowGraph) -> int:
    parent: Dict[str, str] = {n: n for n in graph.nodes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for source, targets in graph.succ.items():
        for target in targets:
            ra, rb = find(source), find(target)
            if ra != rb:
                parent[ra] = rb
    return len({find(n) for n in graph.nodes})


def condensation_paths(graph: FlowGraph, cap: int = 100000) -> Tuple[int, bool, int]:
    """Count entry-to-exit paths and the longest path on the SCC condensation.

    Returns (path_count, capped, longest_path_in_symbols). Each loop is
    collapsed into one super-node, so the counts describe distinct routes
    through the chart rather than infinitely many loop iterations.
    """
    components = strongly_connected_components(graph.nodes, graph.succ)
    comp_of: Dict[str, int] = {}
    for i, component in enumerate(components):
        for node in component:
            comp_of[node] = i
    size = [len(c) for c in components]
    succ: Dict[int, Set[int]] = {i: set() for i in range(len(components))}
    indegree = [0] * len(components)
    for source, targets in graph.succ.items():
        for target in targets:
            a, b = comp_of[source], comp_of[target]
            if a != b and b not in succ[a]:
                succ[a].add(b)
                indegree[b] += 1
    order: List[int] = []
    queue = deque(i for i in range(len(components)) if indegree[i] == 0)
    remaining = list(indegree)
    while queue:
        current = queue.popleft()
        order.append(current)
        for nxt in succ[current]:
            remaining[nxt] -= 1
            if remaining[nxt] == 0:
                queue.append(nxt)
    paths = [0] * len(components)
    longest = [0] * len(components)
    capped = False
    for comp in reversed(order):
        if not succ[comp]:
            paths[comp] = 1
            longest[comp] = size[comp]
            continue
        total = sum(paths[n] for n in succ[comp])
        if total > cap:
            total = cap
            capped = True
        paths[comp] = total
        longest[comp] = size[comp] + max(longest[n] for n in succ[comp])
    sources = [i for i in range(len(components)) if indegree[i] == 0]
    total_paths = sum(paths[i] for i in sources)
    if total_paths > cap:
        total_paths, capped = cap, True
    max_len = max((longest[i] for i in sources), default=0)
    return total_paths, capped, max_len


def first_matching(start: str, adjacency: Dict[str, List[str]], is_target, is_transparent,
                   max_depth: int) -> Optional[str]:
    """Breadth-first search for a node satisfying ``is_target`` within ``max_depth``.

    Transparent nodes (connectors) are walked through without consuming depth.
    """
    seen = {start}
    queue = deque([(start, 0)])
    while queue:
        node, depth = queue.popleft()
        for nxt in adjacency.get(node, []):
            if nxt in seen:
                continue
            seen.add(nxt)
            if is_target(nxt):
                return nxt
            next_depth = depth if is_transparent(nxt) else depth + 1
            if next_depth < max_depth:
                queue.append((nxt, next_depth))
    return None
