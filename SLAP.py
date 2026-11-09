"""SLAP (Structural Line Algorithm Path) Reference Parser

Deterministic, single-pass O(N) parser and tree reconstructor.
Zero third-party dependencies.
"""

from __future__ import annotations

from pprint import pprint
import re
from typing import Any, Dict, List, Optional, Set, Tuple

SCALAR_KEY = "_"
_INT = re.compile(r"^-?(0|[1-9]\d*)$")
_FLOAT = re.compile(r"^-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?$")


def _coerce_scalar(text: str) -> Any:
    """Type resolution for scalar values."""
    if text == "true":
        return True
    if text == "false":
        return False
    if text == "null":
        return None
    if _INT.match(text):
        return int(text)
    if _FLOAT.match(text):
        return float(text)
    return text


class SLAPParser:
    """Deterministic, causal tree-state deserializer."""

    def __init__(self) -> None:
        self.node_stack: List[str] = []
        self.scope_attrs: List[Dict[str, str]] = []
        self.nodes: List[Dict[str, Any]] = []
        self._last_was_node: bool = False
        self._block_levels: Set[int] = set()

    @staticmethod
    def _count_prefix(line: str, char: str) -> int:
        count = 0
        for c in line:
            if c != char:
                break
            count += 1
        return count

    def _parse_line(self, raw_line: str) -> Optional[Tuple[str, int, str]]:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            return None

        if line.startswith("-"):
            depth = self._count_prefix(line, "-")
            return ("node", depth, line[depth:].strip())

        if line.startswith("."):
            depth = self._count_prefix(line, ".")
            return ("attr", depth, line[depth:].strip())

        return None

    def parse_nodes(self, text: str) -> List[Dict[str, Any]]:
        """Parses a SLAP stream into a flat sequence of immutable node records."""
        self.node_stack = []
        self.scope_attrs = []
        self.nodes = []
        self._last_was_node = False
        self._block_levels = set()

        for raw_line in text.splitlines():
            token = self._parse_line(raw_line)
            if not token:
                continue

            token_type, depth, payload = token

            if token_type == "node":
                # Root boundary isolation: Only registers declared directly prior survive
                if depth == 1:
                    self.scope_attrs = [
                        reg if i in self._block_levels else {}
                        for i, reg in enumerate(self.scope_attrs)
                    ]

                # 1. Unwind stack down to node depth
                while len(self.node_stack) >= depth:
                    self.node_stack.pop()
                if len(self.scope_attrs) > depth:
                    self.scope_attrs = self.scope_attrs[:depth]

                self.node_stack.append(payload)

                # 2. Inherit active attributes up to current depth
                inherited_attrs: Dict[str, str] = {}
                for level_register in self.scope_attrs[:depth]:
                    inherited_attrs.update(level_register)

                current_path = "/" + "/".join(self.node_stack)
                parent_path = (
                    "/" + "/".join(self.node_stack[:-1])
                    if len(self.node_stack) > 1
                    else None
                )

                # 3. Commit immutable node record
                self.nodes.append({
                    "id": payload,
                    "depth": depth,
                    "path": current_path,
                    "parent": parent_path,
                    "attributes": inherited_attrs,
                })
                self._last_was_node = True
                self._block_levels = set()

            elif token_type == "attr":
                target_level = depth - 1

                # Bare register reset (e.g. "..")
                if payload == "":
                    self.scope_attrs = self.scope_attrs[:target_level]
                    self._last_was_node = False
                    continue

                if ":" not in payload:
                    continue

                key, value = payload.split(":", 1)
                key, value = key.strip(), value.strip()

                # Flush deeper registers on scope transition
                if self._last_was_node:
                    self.scope_attrs = self.scope_attrs[:target_level]
                    self._last_was_node = False
                elif len(self.scope_attrs) > target_level + 1:
                    self.scope_attrs = self.scope_attrs[:target_level + 1]

                while len(self.scope_attrs) <= target_level:
                    self.scope_attrs.append({})

                self.scope_attrs[target_level][key] = value
                self._block_levels.add(target_level)

        return self.nodes


def nodes_to_tree(nodes: List[Dict[str, Any]], coerce: bool = True) -> Dict[str, Any]:
    """Reconstructs nested dictionary and list hierarchies from node records."""
    conv = _coerce_scalar if coerce else (lambda s: s)

    roots: List[Dict[str, Any]] = []
    stack: List[Dict[str, Any]] = []

    for n in nodes:
        rec = {"n": n, "kids": []}
        while len(stack) >= n["depth"]:
            stack.pop()
        (stack[-1]["kids"] if stack else roots).append(rec)
        stack.append(rec)

    def build(rec: Dict[str, Any]) -> Any:
        attrs, kids = rec["n"]["attributes"], rec["kids"]
        if not kids and SCALAR_KEY in attrs:
            return conv(attrs[SCALAR_KEY])
        if kids and [k["n"]["id"] for k in kids] == [str(i) for i in range(len(kids))]:
            return [build(k) for k in kids]
        out = {k: conv(v) for k, v in attrs.items() if k != SCALAR_KEY}
        for k in kids:
            out[k["n"]["id"]] = build(k)
        return out

    return {r["n"]["id"]: build(r) for r in roots}


def loads(slap_text: str, coerce: bool = True) -> Dict[str, Any]:
    """Standard entry point: Deserializes SLAP stream directly into a nested dict."""
    nodes = SLAPParser().parse_nodes(slap_text)
    return nodes_to_tree(nodes, coerce=coerce)


def parse_nodes(slap_text: str) -> List[Dict[str, Any]]:
    """Low-level inspection of immutable node records."""
    return SLAPParser().parse_nodes(slap_text)


if __name__ == "__main__":
    stream = """
    -cluster_alpha
    .zone:eu_central
    .security:strict
    --node_01
    ..role:backup
    --node_02
    ..maintenance:true
    --node_03
    """

    print("=== HIGH-LEVEL DICT (loads) ===")
    pprint(loads(stream))

    print("\n=== LOW-LEVEL NODES (parse_nodes) ===")
    pprint(parse_nodes(stream))

