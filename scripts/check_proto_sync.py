#!/usr/bin/env python3
"""Check that protobuf files across Java, Python, and Visualization directories remain in sync."""

from pathlib import Path
import sys
import re

def normalize_proto(content: str) -> list[str]:
    """Normalize proto content by stripping comments and blank lines for field comparison."""
    lines = []
    for line in content.splitlines():
        line = re.sub(r"//.*$", "", line).strip()
        if line:
            lines.append(line)
    return lines

def main() -> int:
    root = Path(__file__).resolve().parent.parent
    canonical_proto = root / "src" / "main" / "proto" / "sim_bridge.proto"
    python_proto = root / "physical_engine" / "protos" / "sim_bridge.proto"
    viz_proto = root / "visualization" / "sim_bridge.proto"

    if not canonical_proto.exists():
        print(f"ERROR: Canonical proto not found: {canonical_proto}", file=sys.stderr)
        return 1

    canonical_norm = normalize_proto(canonical_proto.read_text(encoding="utf-8"))

    mismatches = 0
    for target in [python_proto, viz_proto]:
        if not target.exists():
            print(f"ERROR: Target proto not found: {target}", file=sys.stderr)
            mismatches += 1
            continue
        
        target_norm = normalize_proto(target.read_text(encoding="utf-8"))
        if canonical_norm != target_norm:
            print(f"ERROR: Protobuf mismatch between {canonical_proto} and {target}", file=sys.stderr)
            mismatches += 1
        else:
            print(f"✓ In sync: {target.relative_to(root)}")

    if mismatches > 0:
        print(f"\nProto sync check failed with {mismatches} mismatch(es).", file=sys.stderr)
        return 1

    print("\nAll protobuf definitions are in sync!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
