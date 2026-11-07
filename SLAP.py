"""SLAP Reference Parser (Structural Line Algorithm Path)

Deterministic, causal tree-state deserialization.
Reference implementation complying with strict forward causality
and level-isolated scope resets.
"""

from typing import Any, Dict, List, Optional, Tuple
import json


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
                # 1. Stack auf die Tiefe des Knotens abwickeln
                while len(self.node_stack) >= depth:
                    self.node_stack.pop()
                    if len(self.scope_attrs) > len(self.node_stack):
                        self.scope_attrs.pop()

                self.node_stack.append(payload)

                # 2. Alle aktiven Attribute bis zur Tiefe dieses Knotens erben
                inherited_attrs: Dict[str, str] = {}
                for level_register in self.scope_attrs[:depth]:
                    inherited_attrs.update(level_register)

                current_path = "/" + "/".join(self.node_stack)
                parent_path = (
                    "/" + "/".join(self.node_stack[:-1])
                    if len(self.node_stack) > 1
                    else None
                )

                # 3. Unveränderlichen Knoten-Datensatz erzeugen
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

                # Strikt am ersten Doppelpunkt trennen (für URLs, Zeitstempel etc.)
                key, value = payload.split(":", 1)
                key, value = key.strip(), value.strip()

                target_level = depth - 1  # 0-basierter Index (. = 0, .. = 1)

                # REGEL 1: Wenn zuvor Knoten deklariert wurden, leeren wir die Ebene target_level
                # und alle tieferen Ebenen komplett ab, um State-Bleed zu verhindern.
                if self._last_was_node:
                    self.scope_attrs = self.scope_attrs[:target_level]
                    self._last_was_node = False
                else:
                    # REGEL 2: Auch wenn direkt Attribute aufeinander folgen,
                    # schneidet ein Attribut auf Ebene N alle Register tiefer als N gnadenlos ab!
                    if len(self.scope_attrs) > target_level + 1:
                        self.scope_attrs = self.scope_attrs[:target_level + 1]

                # Sicherstellen, dass das Register bis target_level existiert
                while len(self.scope_attrs) <= target_level:
                    self.scope_attrs.append({})

                # Attribut im Register der Zielebene eintragen
                self.scope_attrs[target_level][key] = value

        return self.nodes


def parse_slap(slap_data: str) -> List[Dict[str, Any]]:
    parser = SLAPParser()
    return parser.parse(slap_data)


if __name__ == "__main__":
    # Testfall exakt nach deiner Logik:
    test_slap = """
    .blaA_c:true
    .blaA_d:true
    --blaC
    ..blaC_a:true
    ..blaC_b:true
    ---blaD
    .blaA_f:true
    """
    print(json.dumps(parse_slap(test_slap), indent=2))
    
