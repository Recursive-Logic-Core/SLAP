<div align="center">

![SLAP Banner](SLAP.jpg)

# SLAP
### Structural Line Algorithm Path

**Deterministic, low-token context serialization and tree-state protocol.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Format: SLAP](https://img.shields.io/badge/Protocol-SLAP--1.0-brightgreen.svg)]()
[![Architecture: Zero--Overhead](https://img.shields.io/badge/Architecture-Deterministic-purple.svg)]()

</div>

> **Deterministic Protocol Specification**  
> Designed and specified by Architect M.M.M. Python code provided as a standalone reference implementation artifact.
>
> **Operational Scope: Where SLAP Operates**  
> **SLAP is not a persistent storage engine or a replacement for binary transport protocols (such as Protocol Buffers or CBOR).**  
> It operates as an ephemeral, text-based micro-serialization gateway directly at the **compute and ingestion boundary of Large Language Models**. It transforms heavyweight, bracket-laden payloads into deterministic, token-efficient streams prior to inference without requiring any alterations to existing backend infrastructure (JSON/SQL).

---

## Abstract

Modern data serialization formats (JSON, YAML, XML) carry massive historical ballast: redundant quotation marks, nested closing brackets, fragile indentation rules, and zero native support for state inheritance. When injected into LLM context windows, this syntax overhead directly consumes valuable token budget and working memory.

**SLAP (Structural Line Algorithm Path)** is an ultra-minimalist, line-deterministic protocol designed for pure context efficiency. It maps hierarchical tree topologies and cascading context inheritance using single-character prefix vectors. No brackets, no commas, no syntax noise.

---

## Core Principles

1. **Zero Syntax Overhead:** Only semantic data and explicit prefix markers exist. Structural depth is declared strictly at index `0` of each line.
2. **Deterministic Single-Pass Parsing ($O(N)$):** Evaluated strictly line-by-line using a lightweight finite-state machine. No lookaheads, no backtrack buffers, and no recursion overhead.
3. **Cascading State Inheritance & Dynamic Scope:** Attributes defined at depth $N$ attach to the active node at that depth and automatically cascade down into all subsequent child nodes declared *after* them. Prior siblings remain unaffected.
4. **Visual Depth Indexing & Strict Identifiers:** Eliminates ambiguous whitespace within identifiers (using `_`), making structural misalignment immediately visible.
5. **Drop-in In-Memory Gateway:** Persistence layers remain standard (JSON/SQL). SLAP operates strictly in-memory prior to model ingestion to eliminate token bloat.

---

## Structural Determinism vs. JSON Fallibility

Comparing prefix-based hierarchies to bracketed formats often introduces false equivalencies regarding syntax errors. In practice, SLAP enforces significantly higher structural visibility and a lower error surface area than JSON:

* **Elimination of Invisible Structural Drift:**  
  In JSON, a misplaced closing bracket `}` silently shifts an entire branch into an incorrect parent scope while remaining 100% syntactically valid. The parser accepts it, introducing silent logical corruption that is difficult to locate across large files. In SLAP, depth is declared explicitly at index `0` of each line (`-`, `--`, `---`). Hierarchy is visually auditable at a glance.
* **Strict Whitespace Boundaries:**  
  By disallowing ambiguous whitespace within identifiers, malformed tokens and indentation slips stand out immediately. There are no trailing-comma syntax aborts, no unescaped quote errors, and no dangling delimiter states.
* **Symmetrical Structural Responsibility:**  
  No serialization format can correct an author who misunderstands their own data hierarchy. If an element is declared under the wrong parent node, both JSON and SLAP will faithfully parse that incorrect relationship. However, SLAP guarantees that this hierarchy is transmitted with **zero bracket-closure failure vectors** and **minimal token overhead** during automated state transitions.

---

## Syntax Specification

### 1. Entities & Objects (`-`, `--`, `---`)
* `-` declares a root entity (resets previous context).
* Each additional `-` increases the hierarchical depth level ($N+1$).
* Node identifiers use underscores for separation (`cluster_alpha`, `node_01`).

### 2. Attributes & States (`.`, `..`, `...`)
* **Prefix Depth Binding:** The dot count strictly targets that specific hierarchical scope (`.` = Depth 1, `..` = Depth 2, etc.).
* **Strict Forward Causality:** Attributes apply strictly to nodes declared downstream of their declaration. Prior sibling nodes remain completely immutable.
* **Scope Isolation & Transition:** Declaring a new attribute block at depth $N$ resets the active attribute register at that level. Sub-nodes inherit strictly the currently active state block, preventing accidental data bleed across disjoint sets.
* **Compound & Intersection Mapping:** Elements requiring intersecting states (A \cap B) must either be declared under an explicit compound attribute scope (e.g., `.C` representing both traits) or via hierarchical sub-cascading using deeper levels (`..`).
* **Key-Value Splitting:** Evaluated strictly on the first occurrence of `:`.

### 3. Delimiters, Scoping & Parser Contracts
* **Key-Value Splitting:** Parsers evaluate key-value pairs strictly on the first occurrence of `:`. Subsequent colons are preserved as literal string content, natively supporting timestamps, URLs, and encoded values without escape characters.
* **Discrete State Isolation (Scope Resets):** Attribute registers are level-isolated. When a new attribute block is declared at depth $N$, the register for that depth is cleanly replaced rather than accumulated. Deeper registers are managed through explicit hierarchical depth (`..`), ensuring clean mathematical boundaries between adjacent sibling groups.
* **Execution-Order Invariant:** SLAP is an execution-ordered stream, not an unordered associative map. Line order carries semantic causality and is an intentional architectural invariant.

---

## Orthogonal Simplicity & Edge-Case Topologies

SLAP deliberately rejects syntax bloat for exotic edge cases, adhering strictly to single-character prefixes and downstream causality:

* **No Specialized Syntax for Corner Cases:**  
  Complex, disjoint, or non-linear state requirements do not require new syntax operators. They are mapped using the existing primitives (`-`, `.`) through deliberate structural explicitness (e.g., branch isolation or localized redeclaration).
  
* **Graceful Structural Redundancy:**  
  In scenarios where strict state isolation requires breaking a shared cascade, authors simply introduce an explicit intermediate node or repeat an attribute. Even when intentionally redundant, SLAP's character payload and token density remain vastly superior to equivalent multi-level JSON/YAML envelopes.

* **Invariant Parser Contract:**  
  The reference engine (`SLAP.py`) evaluates strictly line-by-line in a single pass (O(N)). It requires zero lookahead buffers and does not negotiate data validity. Whether a tree is hyper-compressed or structurally explicit, the parsing behavior remains entirely deterministic.

---

## Protocol Comparison

### SLAP Representation (In-Memory Prompt Stream)
```text
-cluster_alpha
.zone:eu_central
.security:strict
--node_01
--node_02
..role:backup
.maintenance:true
--node_03
```

### Legacy JSON Representation
```json
{
  "cluster_alpha": {
    "zone": "eu_central",
    "security": "strict",
    "nodes": [
      { 
        "id": "node_01", 
        "zone": "eu_central", 
        "security": "strict" 
      },
      { 
        "id": "node_02", 
        "zone": "eu_central", 
        "security": "strict", 
        "role": "backup" 
      },
      { 
        "id": "node_03", 
        "zone": "eu_central", 
        "security": "strict", 
        "maintenance": "true" 
      }
    ]
  }
}
```

*Result: SLAP reduces character payload by over 50% while completely removing bracket-closure failure vectors.*

---

## Reference Implementation

The reference parser is provided in [`SLAP.py`](SLAP.py) as a standalone, zero-dependency engine:

```python
from SLAP import parse_slap

raw_slap_data = """
-alpha
.status:active
--beta
--gamma
..role:worker
.maintenance:true
--delta
"""

nodes = parse_slap(raw_slap_data)
for node in nodes:
  print(f"Path: {node['path']} | Attributes: {node['attributes']}")
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


## Contact & Architecture Core
Developed and maintained by **Architect M.M.M.**  
Direct contact: `arch_mmm@proton.me`
