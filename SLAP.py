"""SLAP Reference Parser (Structural Line Algorithm Path)

Deterministic, linear state & context deserialization.
"""

import json
from typing import Any, Dict, List, Optional, Tuple


class SLAPParser:

  def __init__(self):
    self.node_stack: List[str] = []
    self.attr_stack: List[Dict[str, str]] = []
    # Fast path-indexed lookup to mutate owner nodes retroactively
    self.node_lookup: Dict[str, Dict[str, Any]] = {}
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
    self.attr_stack = []
    self.nodes = []
    self.node_lookup = {}

    lines = text.splitlines()

    for raw_line in lines:
      token = self._parse_line(raw_line)
      if not token:
        continue

      token_type, depth, payload = token

      if token_type == "node":
        # Unwind the stack to match the target depth of this node
        while len(self.node_stack) >= depth:
          self.node_stack.pop()
          self.attr_stack.pop()

        self.node_stack.append(payload)

        # 1. Inherit all currently active attributes from ancestor scopes (0 to depth-1)
        inherited_attrs: Dict[str, str] = {}
        for level_attrs in self.attr_stack:
          inherited_attrs.update(level_attrs)

        # 2. Allocate an attribute scope for this current level
        self.attr_stack.append({})

        # Construct canonical hierarchical paths
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
        self.node_lookup[current_path] = node_record

      elif token_type == "attr":
        if ":" not in payload:
          continue
        key, value = payload.split(":", 1)
        key, value = key.strip(), value.strip()

        target_level = depth - 1

        # Unwind deeper closed sibling branches back to this attribute's level
        while len(self.node_stack) > depth:
          self.node_stack.pop()
          self.attr_stack.pop()

        if 0 <= target_level < len(self.attr_stack):
          # Arm the attribute for subsequent nodes at or below this depth
          self.attr_stack[target_level][key] = value

          # Apply the attribute retroactively to the owner node at this depth
          current_path = "/" + "/".join(self.node_stack[:depth])
          if current_path in self.node_lookup:
            self.node_lookup[current_path]["attributes"][key] = value

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
    """
  print(json.dumps(parse_slap(test_slap_input), indent=2))
  
