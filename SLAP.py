"""SLAP Reference Parser (Structural Line Algorithm Path)

Deterministic, linear state & context deserialization.
"""

import json
from typing import Any, Dict, List, Optional, Tuple


class SLAPParser:

  def __init__(self):
    self.node_stack: List[str] = []
    # Scope stack tracking active attributes per depth level (Index 0 = Depth 1)
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
        # Unwind the stack to match or exceed the incoming node depth
        while len(self.node_stack) >= depth:
          self.node_stack.pop()
          self.scope_attrs.pop()

        self.node_stack.append(payload)

        # Inherit all active attributes from ancestor scopes (0 to depth-1)
        inherited_attrs: Dict[str, str] = {}
        for level in self.scope_attrs:
          inherited_attrs.update(level)

        # Allocate a dedicated attribute scope for this new node
        self.scope_attrs.append({})

        current_path = "/" + "/".join(self.node_stack)
        parent_path = (
            "/" + "/".join(self.node_stack[:-1])
            if len(self.node_stack) > 1
            else None
        )

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
        key, value = payload.split(":", 1)
        key, value = key.strip(), value.strip()

        # Target level derived from prefix dot count (depth 1 '.' -> Scope index 0)
        target_level = depth - 1

        if 0 <= target_level < len(self.scope_attrs):
          # 1. Arm the attribute for all subsequent sibling and child nodes in this scope
          self.scope_attrs[target_level][key] = value

          # 2. Attach directly to the immediate prior node ONLY if it matches this exact depth
          # Prior sibling branches remain immutable
          if self.nodes and self.nodes[-1]["depth"] == depth:
            self.nodes[-1]["attributes"][key] = value

    return self.nodes


def parse_slap(slap_data: str) -> List[Dict[str, Any]]:
  parser = SLAPParser()
  return parser.parse(slap_data)


if __name__ == "__main__":
  test_slap_input = """
    -alpha
    .Adjektiv1:true
    .Adjektiv2:true
    --betta
    --gamma
    .Adjektiv3:true
    --delta
    -omega
    """
  print(json.dumps(parse_slap(test_slap_input), indent=2))
  
