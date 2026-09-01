"""
SLAP Reference Parser (Structural Line Algorithm Path)
Deterministic, linear state & context deserialization.
"""

from typing import List, Dict, Any, Tuple, Optional
import json


class SLAPParser:
    def __init__(self):
        self.node_stack: List[str] = []
        self.attr_stack: List[Dict[str, str]] = []
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
            payload = line[depth:].strip()
            return ("node", depth, payload)

        elif line.startswith("."):
            depth = self._count_prefix(line, ".")
            payload = line[depth:].strip()
            return ("attr", depth, payload)

        return None

    def parse(self, text: str) -> List[Dict[str, Any]]:
        self.node_stack = []
        self.attr_stack = []
        self.nodes = []

        lines = text.splitlines()

        for raw_line in lines:
            token = self._parse_line(raw_line)
            if not token:
                continue

            token_type, depth, payload = token

            if token_type == "node":
                # Stack auf aktuelle Tiefe anpassen (Knoten-Hierarchie)
                while len(self.node_stack) >= depth:
                    self.node_stack.pop()
                    self.attr_stack.pop()

                # Neuen Knoten auf den Stack legen
                self.node_stack.append(payload)

                # Geerbte Attribute von übergeordneten Ebenen sammeln
                inherited_attrs: Dict[str, str] = {}
                for attr_level in self.attr_stack:
                    inherited_attrs.update(attr_level)

                # Lokalen Attribut-Speicher für diese Ebene anlegen
                self.attr_stack.append({})

                # Pfad und Knoten-Objekt registrieren
                current_path = "/" + "/".join(self.node_stack)
                parent_path = "/" + "/".join(self.node_stack[:-1]) if len(self.node_stack) > 1 else None

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

                # Attribut auf der entsprechenden Stack-Ebene verankern
                target_level = depth - 1
                if 0 <= target_level < len(self.attr_stack):
                    self.attr_stack[target_level][key] = value

                    # Direkt im aktuellen Knoten der Ebene aktualisieren
                    if self.nodes and self.nodes[-1]["depth"] == depth:
                        self.nodes[-1]["attributes"][key] = value

        return self.nodes


def parse_slap(slap_data: str) -> List[Dict[str, Any]]:
    parser = SLAPParser()
    return parser.parse(slap_data)


if __name__ == "__main__":
    test_slap_input = """
    -alpha
    .status:active
    .mode:strict
    --beta
    --gamma
    ..role:worker
    -delta
    .status:idle
    --epsilon
    """

    parsed_result = parse_slap(test_slap_input)
    print(json.dumps(parsed_result, indent=2))
