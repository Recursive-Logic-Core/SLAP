"""SLAP Reference Parser (Structural Line Algorithm Path)

Deterministic, causal tree-state deserialization.
"""

import json
from typing import Any, Dict, List, Optional, Tuple


class SLAPParser:

    def __init__(self):
        self.node_stack: List[str] = []
        # Multi-level state register: Index 0 = Depth 1 ('.'), Index 1 = Depth 2 ('..'), etc.
        self.scope_attrs: List[Dict[str, str]] = []
        self.nodes: List[Dict[str, Any]] = []
        self._last_was_node = False

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

        lines = text.splitlines()

        for raw_line in lines:
            token = self._parse_line(raw_line)
            if not token:
                continue

            token_type, depth, payload = token

            if token_type == "node":
                # 1. Unwind stack to match incoming depth
                while len(self.node_stack) >= depth:
                    self.node_stack.pop()
                    if len(self.scope_attrs) > len(self.node_stack):
                        self.scope_attrs.pop()

                self.node_stack.append(payload)

                # 2. Inherit all active attributes up to this node's level
                inherited_attrs: Dict[str, str] = {}
                for level_register in self.scope_attrs[:depth]:
                    inherited_attrs.update(level_register)

                current_path = "/" + "/".join(self.node_stack)
                parent_path = (
                    "/" + "/".join(self.node_stack[:-1])
                    if len(self.node_stack) > 1
                    else None
                )

                # 3. Create immutable node record with current inherited state
                node_record = {
                    "id": payload,
                    "depth": depth,
                    "path": current_path,
                    "parent": parent_path,
                    "attributes": inherited_attrs,
                }
                self.nodes.append(node_record)
                self._last_was_node = True

            elif token_type == "attr":
                if ":" not in payload:
                    continue
                
                # Split strictly on the first colon
                key, value = payload.split(":", 1)
                key, value = key.strip(), value.strip()

                target_level = depth - 1

                # If nodes intervened, declare a new scope: wipe target level and all deeper registers
                if self._last_was_node:
                    self.scope_attrs = self.scope_attrs[:target_level]
                    self._last_was_node = False

                # Ensure registers exist up to target_level
                while len(self.scope_attrs) <= target_level:
                    self.scope_attrs.append({})

                # Assign attribute to its target level register
                self.scope_attrs[target_level][key] = value

        return self.nodes


def parse_slap(slap_data: str) -> List[Dict[str, Any]]:
    parser = SLAPParser()
    return parser.parse(slap_data)


if __name__ == "__main__":
    test_slap_input = """
    .A:true
    --a
    --b
    ..B:true
    ---c
    .B:true
    --d
    --e
    """
    print(json.dumps(parse_slap(test_slap_input), indent=2))
  
