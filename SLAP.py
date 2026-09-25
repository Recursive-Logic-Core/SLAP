"""SLAP Reference Parser (Structural Line Algorithm Path)

Deterministic, causal linear state & context deserialization.
"""

import json
from typing import Any, Dict, List, Optional, Tuple


class SLAPParser:

    def __init__(self):
        self.node_stack: List[str] = []
        # Multi-level state register: Index 0 = Depth 1 ('.'), Index 1 = Depth 2 ('..'), etc.
        self.scope_attrs: List[Dict[str, str]] = []
        self.nodes: List[Dict[str, Any]] = []

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
                    self.scope_attrs.pop()

                self.node_stack.append(payload)

                # 2. Additive Stacking: Inherit all active attributes from levels 0 to depth-1
                inherited_attrs: Dict[str, str] = {}
                for level_register in self.scope_attrs:
                    inherited_attrs.update(level_register)

                # 3. Allocate a fresh, isolated attribute register for this new node level
                self.scope_attrs.append({})

                current_path = "/" + "/".join(self.node_stack)
                parent_path = (
                    "/" + "/".join(self.node_stack[:-1])
                    if len(self.node_stack) > 1
                    else None
                )

                # 4. Freeze immutable node record with current inherited state
                node_record = {
                    "id": payload,
                    "depth": depth,
                    "path": current_path,
                    "parent": parent_path,
                    "attributes": inherited_attrs,
                }
                self.nodes.append(node_record)

            elif token_type == "attr":
                if ":" not in payload:
                    continue
                # Split strictly on first colon (colon-handling rule)
                key, value = payload.split(":", 1)
                key, value = key.strip(), value.strip()

                target_level = depth - 1

                # If an attribute is declared before its node depth exists, extend registers
                while len(self.scope_attrs) <= target_level:
                    self.scope_attrs.append({})

                # Arm the register strictly forward for subsequent children/siblings
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
    .B:true
    --d
    --e
    .C:true
    --c
    """
    print(json.dumps(parse_slap(test_slap_input), indent=2))
  
