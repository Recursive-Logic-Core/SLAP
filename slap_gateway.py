"""
SLAP Gateway (Structural Line Algorithm Path), v2.5
Reference Implementation & Codec for Python 3.10+
MIT License

Bidirectional in-memory gateway between JSON-compatible trees and
token-efficient SLAP line streams. Single-pass, O(N) decoding.

Conventions beyond the written spec:
* Scalars inside a dict are attributes of that dict's node, declared BEFORE it.
* A scalar that is a node on its own (list item, top-level value) is stored
  under the reserved attribute key "_".
* Lists become a node with children named "0", "1", ... On rebuild, children
  named exactly "0".."n-1" become a list again.
* Register reset: a line of dots only (e.g. "..") flushes that depth and all
  deeper registers. It is the only way to say "no own attributes" after a
  sibling that had some.
* Streams hold strings only. Types come back only with coerce=True (lossy:
  the string "true" then becomes True).

Normalization (intentional, context-optimizer behavior): leading/trailing
whitespace of values is stripped, whitespace inside identifiers becomes "_",
':' inside attribute keys becomes "_".

Known ambiguities of the rebuild: [] becomes a dict (holding only inherited
attributes), a dict with keys "0","1",...
becomes a list, and children carry the attributes of their parents (cascade).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

SCALAR_KEY = "_"
_LINEBREAK = re.compile(r"[\r\n\v\f\x1c-\x1e\x85\u2028\u2029]")
_WS = re.compile(r"\s+")
_INT = re.compile(r"^-?(0|[1-9]\d*)$")
_FLOAT = re.compile(r"^-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?$")  # checked after _INT


# ============================================================
# 1. EXCEPTIONS
# ============================================================

class SLAPError(ValueError):
    """Base exception for all SLAP-related failures."""


class SLAPSyntaxError(SLAPError):
    """Grammar violations: prefixes, delimiters, illegal characters."""


class SLAPStructureError(SLAPError):
    """Hierarchy violations: depth jumps, wrong top-level type, forbidden resets."""


# ============================================================
# 2. SCALARS
# ============================================================

def scalar_to_str(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return value
    raise SLAPError(f"Unsupported value type for SLAP stream: {type(value).__name__}")


def coerce_scalar(text: str) -> Any:
    """Best-effort inverse of scalar_to_str (lossy for strings like 'true')."""
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


# ============================================================
# 3. CODEC
# ============================================================

class SLAPCodec:
    """
    strict=True (default):
      decode rejects depth jumps, attributes without ':', unknown prefixes,
      comments, leading whitespace and whitespace in identifiers;
      encode rejects line breaks in values and identifiers starting with
      '-', '.', '#' instead of normalizing them.
    allow_reset=False:
      encode raises instead of emitting a register-reset line.
    hoist=True:
      encode writes a sibling's attributes only if the register does not
      already hold exactly that set (consecutive siblings share one block).
      Only complete, identical attribute sets can be shared: a new block
      flushes the whole register.
    group=True (implies hoist):
      additionally groups the children of a dict by identical attribute sets.
      This does NOT preserve the key order of dicts; list order is always kept.
    """

    def __init__(self, strict: bool = True, allow_reset: bool = True,
                 hoist: bool = False, group: bool = False):
        self.strict = strict
        self.allow_reset = allow_reset
        self.group = group
        self.hoist = hoist or group
        self.node_stack: List[str] = []
        self.scope_attrs: List[Dict[str, str]] = []
        self.nodes: List[Dict[str, Any]] = []
        self._last_was_node = False

    # ---------------------------------------------------- decode helpers

    @staticmethod
    def _count_prefix(line: str, char: str) -> int:
        count = 0
        for c in line:
            if c != char:
                break
            count += 1
        return count

    @staticmethod
    def _fail_syntax(lineno: int, msg: str) -> None:
        raise SLAPSyntaxError(f"Line {lineno}: {msg}")

    @staticmethod
    def _fail_structure(lineno: int, msg: str) -> None:
        raise SLAPStructureError(f"Line {lineno}: {msg}")

    def _parse_line(self, raw: str, lineno: int) -> Optional[Tuple[str, int, str]]:
        if not raw.strip():
            return None

        if self.strict:
            if raw[0] in " \t":
                self._fail_syntax(lineno, "depth must be declared at index 0 (leading whitespace)")
            line = raw.rstrip()
        else:
            line = raw.strip()
            if line.startswith("#"):
                return None

        if line[0] == "-":
            depth = self._count_prefix(line, "-")
            name = line[depth:].strip()
            if self.strict:
                if not name:
                    self._fail_syntax(lineno, "node identifier cannot be empty")
                if _WS.search(name):
                    self._fail_syntax(lineno, f"node identifier contains whitespace: {name!r}")
            return ("node", depth, name)

        if line[0] == ".":
            depth = self._count_prefix(line, ".")
            return ("attr", depth, line[depth:].strip())

        if self.strict:
            self._fail_syntax(lineno, f"unknown structural prefix: {line[0]!r}")
        return None

    # ---------------------------------------------------- decode

    def decode(self, text: str) -> List[Dict[str, Any]]:
        """Parse a SLAP stream into a flat list of node records with resolved
        (inherited) attributes. Single pass, no lookahead."""
        self.node_stack = []
        self.scope_attrs = []
        self.nodes = []
        self._last_was_node = False
        block_levels: Set[int] = set()  # registers declared since the last node

        for lineno, raw in enumerate(text.splitlines(), start=1):
            token = self._parse_line(raw, lineno)
            if token is None:
                continue
            kind, depth, payload = token

            if kind == "node":
                if self.strict and depth > len(self.node_stack) + 1:
                    self._fail_structure(
                        lineno,
                        f"illegal depth jump to {depth} (current depth is {len(self.node_stack)})",
                    )

                if depth == 1:
                    # New root: only registers declared directly before it survive.
                    self.scope_attrs = [
                        reg if i in block_levels else {}
                        for i, reg in enumerate(self.scope_attrs)
                    ]

                while len(self.node_stack) >= depth:
                    self.node_stack.pop()
                if len(self.scope_attrs) > depth:
                    self.scope_attrs = self.scope_attrs[:depth]

                self.node_stack.append(payload)

                inherited: Dict[str, str] = {}
                for register in self.scope_attrs[:depth]:
                    inherited.update(register)

                self.nodes.append({
                    "id": payload,
                    "depth": depth,
                    "path": "/" + "/".join(self.node_stack),
                    "parent": "/" + "/".join(self.node_stack[:-1]) if len(self.node_stack) > 1 else None,
                    "attributes": inherited,
                })
                self._last_was_node = True
                block_levels = set()
                continue

            # attribute line
            level = depth - 1
            if self.strict and depth > len(self.node_stack) + 1:
                self._fail_structure(
                    lineno,
                    f"attribute depth {depth} is deeper than any possible node "
                    f"(current depth is {len(self.node_stack)})",
                )

            if payload == "":  # register reset
                self.scope_attrs = self.scope_attrs[:level]
                self._last_was_node = False
                continue

            if ":" not in payload:
                if self.strict:
                    self._fail_syntax(lineno, f"attribute line missing ':': {payload!r}")
                continue

            key, value = payload.split(":", 1)  # first ':' only
            key, value = key.strip(), value.strip()
            if self.strict:
                if not key:
                    self._fail_syntax(lineno, "attribute key cannot be empty")
                if _WS.search(key):
                    self._fail_syntax(lineno, f"attribute key contains whitespace: {key!r}")

            if self._last_was_node:
                self.scope_attrs = self.scope_attrs[:level]
                self._last_was_node = False
            elif len(self.scope_attrs) > level + 1:
                self.scope_attrs = self.scope_attrs[:level + 1]

            while len(self.scope_attrs) <= level:
                self.scope_attrs.append({})
            self.scope_attrs[level][key] = value
            block_levels.add(level)

        return self.nodes

    # ---------------------------------------------------- encode

    def _ident(self, text: Any, what: str) -> str:
        s = _WS.sub("_", str(text).strip())
        if what == "key":
            s = s.replace(":", "_")
        if not s or s[0] in "-.#":
            if self.strict:
                raise SLAPSyntaxError(f"Cannot use {text!r} as {what} identifier")
            s = "_" + s
        return s

    def _value(self, value: Any) -> str:
        s = scalar_to_str(value)
        if _LINEBREAK.search(s):
            if self.strict:
                raise SLAPSyntaxError(f"Line break in value would break the stream: {s!r}")
            s = re.sub(r"\s*" + _LINEBREAK.pattern + r"+\s*", " ", s)
        return s.strip()

    def _own_attrs(self, val: Any) -> List[Tuple[str, str]]:
        if isinstance(val, dict):
            out: List[Tuple[str, str]] = []
            for k, v in val.items():
                if isinstance(v, (dict, list)):
                    continue
                key = self._ident(k, "key")
                if key == SCALAR_KEY:
                    raise SLAPError(f"Key {SCALAR_KEY!r} is reserved for scalar nodes")
                out.append((key, self._value(v)))
            return out
        if isinstance(val, list):
            return []
        return [(SCALAR_KEY, self._value(val))]

    @staticmethod
    def _children(val: Any) -> List[Tuple[Any, Any]]:
        if isinstance(val, dict):
            return [(k, v) for k, v in val.items() if isinstance(v, (dict, list))]
        if isinstance(val, list):
            return [(str(i), v) for i, v in enumerate(val)]
        return []

    def _emit(self, lines: List[str], items: List[Tuple[Any, Any]], depth: int,
              reorderable: bool = False) -> None:
        entries = [(k, v, tuple(self._own_attrs(v))) for k, v in items]
        if self.group and reorderable and depth > 1:
            first: Dict[Tuple[Tuple[str, str], ...], int] = {}
            for _, _, own in entries:
                first.setdefault(own, len(first))
            entries.sort(key=lambda e: first[e[2]])  # stable
        active: Tuple[Tuple[str, str], ...] = ()  # attributes the register of this depth holds
        for key, val, own in entries:
            if self.hoist and depth > 1 and own and own == active:
                pass  # register already holds exactly these attributes
            elif own:
                lines.extend(f"{'.' * depth}{k}:{v}" for k, v in own)
                active = own
            elif active and depth > 1:  # roots reset the context themselves
                if not self.allow_reset:
                    raise SLAPStructureError(
                        f"Node {key!r} has no own attributes but would inherit them from its "
                        "previous sibling; a register reset is required but forbidden"
                    )
                lines.append("." * depth)
                active = ()
            lines.append("-" * depth + self._ident(key, "node"))
            self._emit(lines, self._children(val), depth + 1, isinstance(val, dict))

    def encode(self, data: Dict[str, Any]) -> str:
        """Top-level keys become roots. Wrap top-level lists/scalars in a dict."""
        if not isinstance(data, dict):
            raise SLAPStructureError("Top-level payload must be a dict")
        lines: List[str] = []
        self._emit(lines, list(data.items()), 1)
        return "\n".join(lines)


# ============================================================
# 4. TREE RECONSTRUCTION
# ============================================================

def nodes_to_tree(nodes: List[Dict[str, Any]], coerce: bool = False) -> Dict[str, Any]:
    """Rebuild nested structures from decoded nodes. Attributes are the
    effective (inherited) ones, i.e. children contain their parents' attributes."""
    conv = coerce_scalar if coerce else (lambda s: s)

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


def expand_inheritance(value: Any, inherited: Optional[Dict[str, Any]] = None,
                       typed: bool = False) -> Any:
    """What decode + rebuild should return for `value` (cascade applied).
    Reference side of the roundtrip test."""
    conv = (lambda v: v) if typed else scalar_to_str
    inherited = inherited or {}
    if isinstance(value, dict):
        eff = dict(inherited)
        eff.update({k: conv(v) for k, v in value.items() if not isinstance(v, (dict, list))})
        out = dict(eff)
        for k, v in value.items():
            if isinstance(v, (dict, list)):
                out[k] = expand_inheritance(v, eff, typed)
        return out
    if isinstance(value, list):
        return [expand_inheritance(v, inherited, typed) for v in value] if value else dict(inherited)
    return conv(value)


# ============================================================
# 5. PUBLIC API
# ============================================================

def encode_to_slap(data: Dict[str, Any], **kw: Any) -> str:
    return SLAPCodec(**kw).encode(data)


def decode_to_nodes(slap_text: str, **kw: Any) -> List[Dict[str, Any]]:
    return SLAPCodec(**kw).decode(slap_text)


def decode_to_tree(slap_text: str, coerce: bool = False, **kw: Any) -> Dict[str, Any]:
    return nodes_to_tree(decode_to_nodes(slap_text, **kw), coerce=coerce)


def json_to_slap(json_str: str, **kw: Any) -> str:
    """JSON string -> SLAP stream."""
    return encode_to_slap(json.loads(json_str), **kw)


def slap_to_json(slap_text: str, indent: int = 2, coerce: bool = False, **kw: Any) -> str:
    """SLAP stream -> JSON string of the rebuilt tree (not the flat node list)."""
    return json.dumps(decode_to_tree(slap_text, coerce=coerce, **kw),
                      indent=indent, ensure_ascii=False)


# ============================================================
# 6. SELF-TESTS
# ============================================================

def _raises(fn, exc_cls: type, *args: Any, **kw: Any) -> bool:
    """True only if exactly `exc_cls` (or a subclass) is raised; any other
    exception propagates, so a typo in a test cannot pass silently."""
    try:
        fn(*args, **kw)
    except exc_cls:
        return True
    return False


def _random_tree(rng: Any, depth: int = 0) -> Any:
    t = rng.random()
    if depth >= 4 or t < 0.35:
        return rng.choice(["a", "b", "", "x y", 1, 2.5, True, None])
    if t < 0.75:
        return {rng.choice(["k0", "k1", "k2", "k3"]): _random_tree(rng, depth + 1)
                for _ in range(rng.randint(0, 4))}
    return [_random_tree(rng, depth + 1) for _ in range(rng.randint(0, 4))]


def run_selftests() -> None:
    def roundtrip(data: Dict[str, Any], typed: bool = False, **kw: Any) -> str:
        stream = encode_to_slap(data, **kw)
        got = decode_to_tree(stream, coerce=typed)
        want = {k: expand_inheritance(v, None, typed) for k, v in data.items()}
        assert got == want, f"\nstream:\n{stream}\n\ngot:  {got}\nwant: {want}"
        return stream

    def attrs_of(stream: str, **kw: Any) -> Dict[str, Dict[str, str]]:
        return {n["id"]: n["attributes"] for n in decode_to_nodes(stream, **kw)}

    # 1. Demo payload, exact stream
    demo = {"cluster_alpha": {
        "node_01": {"role": "worker", "status": "healthy"},
        "node_02": {"role": "backup", "maintenance": "true"}}}
    assert roundtrip(demo) == (
        "-cluster_alpha\n..role:worker\n..status:healthy\n--node_01\n"
        "..role:backup\n..maintenance:true\n--node_02")

    # 2. Nesting, lists of dicts/scalars/lists, empty nodes
    roundtrip({"cluster": {
        "zone": "eu", "node_01": {"role": "w"}, "node_02": {},
        "nodes": [{"id": "a", "x": "1"}, {"id": "b"}, "plain", ["in1", "in2"]]}})

    # 3. Register reset
    s = roundtrip({"c": {"n1": {"role": "x"}, "n2": {}}})
    assert "\n..\n" in s
    assert decode_to_nodes(s)[2]["attributes"] == {}
    assert _raises(encode_to_slap, SLAPStructureError,
                   {"c": {"n1": {"role": "x"}, "n2": {}}}, allow_reset=False)

    # 4. Colons and spaces in values
    roundtrip({"svc": {"url": "https://x.de:8080/a", "ts": "12:30:00", "note": "a b  c"}})

    # 5. Types only with coerce=True
    typed = {"a": 5, "b": {"k": 1, "f": 1.5, "ok": True, "n": None}, "c": [1, 2.5, False]}
    roundtrip(typed, typed=True)
    assert decode_to_tree(encode_to_slap({"a": {"ok": True}}))["a"]["ok"] == "true"
    assert decode_to_tree(encode_to_slap({"a": {"v": "007"}}))["a"]["v"] == "007"

    assert coerce_scalar("1e+20") == 1e20 and coerce_scalar("1.5e-07") == 1.5e-07
    assert coerce_scalar("1E5") == 1e5 and coerce_scalar("1e") == "1e"
    assert coerce_scalar("-0.5") == -0.5 and coerce_scalar("01.5") == "01.5"
    roundtrip({"n": {"big": 1e20, "tiny": 1.5e-07, "neg": -2.5e10}}, typed=True)
    assert decode_to_tree(encode_to_slap({"a": {"v": " hello "}}))["a"]["v"] == "hello"

    # 6. Root reset and forward causality
    assert attrs_of("-a\n.zone:eu\n-b\n-c") == {"a": {}, "b": {"zone": "eu"}, "c": {}}
    assert attrs_of(".zone:eu\n-a\n-b") == {"a": {"zone": "eu"}, "b": {}}
    assert attrs_of("-a\n.zone:eu\n--n1\n-b") == {"a": {}, "n1": {"zone": "eu"}, "b": {}}

    # 7. Strict decoder errors (exact classes)
    assert _raises(decode_to_nodes, SLAPStructureError, "-a\n---c")
    assert _raises(decode_to_nodes, SLAPStructureError, "--orphan")
    assert _raises(decode_to_nodes, SLAPSyntaxError, "-a\n..x")
    assert _raises(decode_to_nodes, SLAPSyntaxError, "foo")
    assert _raises(decode_to_nodes, SLAPSyntaxError, "kein_prefix:wert")
    assert _raises(decode_to_nodes, SLAPSyntaxError, " -a")
    assert _raises(decode_to_nodes, SLAPSyntaxError, "-a b")
    assert _raises(decode_to_nodes, SLAPSyntaxError, "-a\n# note")
    assert _raises(decode_to_nodes, SLAPSyntaxError, "-a\n.:x")
    assert _raises(decode_to_nodes, SLAPStructureError, "...ghost:value\n-root")
    assert _raises(decode_to_nodes, SLAPStructureError, "-a\n...ghost:v\n--b")
    assert _raises(decode_to_nodes, SLAPStructureError, "-a\n...")
    assert attrs_of("...ghost:value\n-root", strict=False) == {"root": {}}
    assert decode_to_nodes("-a\n# note\n..x", strict=False)[0]["id"] == "a"

    # 8. Encoder edge cases
    assert encode_to_slap({"my node": {"my key": "v"}}) == ".my_key:v\n-my_node"
    assert encode_to_slap({"a": {"k:x": "v"}}) == ".k_x:v\n-a"
    assert _raises(encode_to_slap, SLAPSyntaxError, {"a": {"k": "line1\nline2"}})
    assert _raises(encode_to_slap, SLAPSyntaxError, {"a": {"k": "x\u2028y"}})
    assert _raises(encode_to_slap, SLAPSyntaxError, {"-a": {"k": "v"}})
    assert encode_to_slap({"a": {"k": "line1\nline2"}}, strict=False) == ".k:line1 line2\n-a"
    assert _raises(encode_to_slap, SLAPError, {"a": {"_": "x"}})
    assert _raises(encode_to_slap, SLAPStructureError, [1, 2])
    assert _raises(encode_to_slap, SLAPError, {"a": {"k": object()}})

    # 9. JSON gateway
    raw = '{"server": {"port": 8080, "active": true, "stadt": "München"}, "tags": [1, 2]}'
    out = slap_to_json(json_to_slap(raw), coerce=True)
    assert "München" in out and "\\u" not in out
    back = json.loads(out)
    assert back["server"]["port"] == 8080 and back["server"]["active"] is True
    assert back["tags"] == [1, 2]
    assert json.loads(slap_to_json(json_to_slap(raw)))["server"]["port"] == "8080"

    # 10. Deterministic tree rebuild from a hand-written stream
    tree = decode_to_tree(
        ".zone:eu\n-cluster\n..role:worker\n--node1\n...val:100\n---metrics\n"
        "..role:master\n--node2", coerce=True)
    assert tree["cluster"]["zone"] == "eu"
    assert tree["cluster"]["node1"]["role"] == "worker"
    assert tree["cluster"]["node1"]["metrics"]["val"] == 100
    assert tree["cluster"]["node2"]["role"] == "master"

    # 11. Empty list under a node with attributes, then randomized roundtrip
    roundtrip({"c": {"zone": "eu", "l": [], "d": {}}})
    import random
    rng = random.Random(7)
    for _ in range(1000):
        roundtrip({rng.choice(["r0", "r1", "r2"]): _random_tree(rng, 1)
                   for _ in range(rng.randint(1, 3))})

    # 12. Hoisting / grouping (opt-in)
    three = {"c": {"n1": {"r": "w"}, "n2": {"r": "w"}, "n3": {"r": "b"}}}
    assert roundtrip(three, hoist=True) == "-c\n..r:w\n--n1\n--n2\n..r:b\n--n3"
    assert roundtrip(three) == "-c\n..r:w\n--n1\n..r:w\n--n2\n..r:b\n--n3"
    mixed = {"c": {"n1": {"r": "w"}, "n2": {"r": "b"}, "n3": {"r": "w"}}}
    assert roundtrip(mixed, group=True) == "-c\n..r:w\n--n1\n--n3\n..r:b\n--n2"
    lst = {"l": [{"r": "b"}, {"r": "a"}, {"r": "b"}, {"r": "b"}]}
    assert decode_to_tree(encode_to_slap(lst, group=True)) == {
        "l": [{"r": "b"}, {"r": "a"}, {"r": "b"}, {"r": "b"}]}  # list order kept
    roundtrip({"c": {"n1": {"r": "w"}, "n2": {}, "n3": {"r": "w"}, "n4": {"r": "w"}}}, hoist=True)
    big = {"cl": {f"n{i}": {"role": "w" if i % 3 else "b", "st": "ok"} for i in range(20)}}
    assert len(encode_to_slap(big, group=True)) < len(encode_to_slap(big, hoist=True)) \
        < len(encode_to_slap(big))
    for kw in ({"hoist": True}, {"group": True}):
        rng = random.Random(11)
        for _ in range(1000):
            roundtrip({rng.choice(["r0", "r1", "r2"]): _random_tree(rng, 1)
                       for _ in range(rng.randint(1, 3))}, **kw)

    print("Alle Selbsttests bestanden.")


# ============================================================
# 7. CLI ENTRYPOINT
# ============================================================

def cli_main() -> None:
    parser = argparse.ArgumentParser(
        description="SLAP Gateway: Bi-directional translation between JSON and SLAP streams."
    )
    parser.add_argument("input", nargs="?", default="-", help="Input file path or '-' for STDIN")
    parser.add_argument("-o", "--output", help="Output file path (default: STDOUT)")
    parser.add_argument("--to-json", action="store_true", help="Convert SLAP input to JSON output")
    parser.add_argument("--to-slap", action="store_true", help="Convert JSON input to SLAP output")
    parser.add_argument("--coerce", action="store_true", help="Coerce types when converting to JSON (bool, int, float)")
    parser.add_argument("--hoist", action="store_true", help="Hoist identical sibling attributes")
    parser.add_argument("--group", action="store_true", help="Group dictionary children by attributes")
    parser.add_argument("--lenient", action="store_true", help="Disable strict parsing")
    parser.add_argument("--test", action="store_true", help="Run full self-test suite and exit")

    args = parser.parse_args()

    if args.test:
        run_selftests()
        sys.exit(0)

    if args.input == "-":
        content = sys.stdin.read()
    else:
        with open(args.input, "r", encoding="utf-8") as f:
            content = f.read()

    to_json_mode = args.to_json
    if not args.to_json and not args.to_slap:
        first_char = content.strip()[:1]
        to_json_mode = first_char in ("-", ".")

    try:
        if to_json_mode:
            result = slap_to_json(content, coerce=args.coerce, strict=not args.lenient)
        else:
            result = json_to_slap(content, hoist=args.hoist, group=args.group, strict=not args.lenient)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result + ("\n" if not result.endswith("\n") else ""))
    else:
        sys.stdout.write(result + ("\n" if not result.endswith("\n") else ""))


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("=== SLAP GATEWAY v2.5 ===")
        run_selftests()
    else:
        cli_main()
