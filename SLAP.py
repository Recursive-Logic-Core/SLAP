"""SLAP Reference Parser (Structural Line Algorithm Path)

Deterministic, causal tree-state deserialization.
Fully aligned with SLAP Gateway v2.5 specifications.
"""

from typing import Any, Dict, List, Optional, Set, Tuple
import json


class SLAPParser:

    def __init__(self):
        self.node_stack: List[str] = []
        self.scope_attrs: List[Dict[str, str]] = []
        self.nodes: List[Dict[str, Any]] = []
        self._last_was_node = False
        self._block_levels: Set[int] = set()

    def _count_prefix(self, line: str, char: str) -> int:
        count = 0
        for c in line:
            if c == char:
                count += 1
            else:
                break
        return count

    def _parse_line(self, raw_line: str) -> Optional[Tuple[str, int, str]]:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            return None

        if line.startswith("-"):
            depth = self._count_prefix(line, "-")
            return ("node", depth, line[depth:].strip())

        elif line.startswith("."):
            depth = self._count_prefix(line, ".")
            return ("attr", depth, line[depth:].strip())

        return None

    def parse(self, text: str) -> List[Dict[str, Any]]:
        self.node_stack = []
        self.scope_attrs = []
        self.nodes = []
        self._last_was_node = False
        self._block_levels = set()

        lines = text.splitlines()

        for raw_line in lines:
            token = self._parse_line(raw_line)
            if not token:
                continue

            token_type, depth, payload = token

            if token_type == "node":
                # Wurzel-Knoten: Nur Register überleben, die unmittelbar davor deklariert wurden
                if depth == 1:
                    self.scope_attrs = [
                        reg if i in self._block_levels else {}
                        for i, reg in enumerate(self.scope_attrs)
                    ]

                # 1. Stack abwickeln
                while len(self.node_stack) >= depth:
                    self.node_stack.pop()
                if len(self.scope_attrs) > depth:
                    self.scope_attrs = self.scope_attrs[:depth]

                self.node_stack.append(payload)

                # 2. Vererbung bis zur Tiefe
                inherited_attrs: Dict[str, str] = {}
                for level_register in self.scope_attrs[:depth]:
                    inherited_attrs.update(level_register)

                current_path = "/" + "/".join(self.node_stack)
                parent_path = (
                    "/" + "/".join(self.node_stack[:-1])
                    if len(self.node_stack) > 1
                    else None
                )

                # 3. Knoten speichern
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

                # Gateway-Kompatibilität: Reiner Register-Reset (z.B. "..")
                if payload == "":
                    self.scope_attrs = self.scope_attrs[:target_level]
                    self._last_was_node = False
                    continue

                if ":" not in payload:
                    continue

                key, value = payload.split(":", 1)
                key, value = key.strip(), value.strip()

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


def parse_slap(slap_data: str) -> List[Dict[str, Any]]:
    return SLAPParser().parse(slap_data)
    
