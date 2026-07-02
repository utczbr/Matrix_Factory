#!/usr/bin/env python3
"""Generate one Phase 4 JaCaMo file containing multiple isolated runs.

This script parses the ASL source files and the JCM template to generate
a mega-JCM file with strict structural isolation for Single-JVM Fan-Out.
"""

from __future__ import annotations
import argparse
import re
import sys
import shutil
from pathlib import Path

# The strict list of canonical tokens that must be isolated per run.
CANONICAL_TOKENS = [
    "supervisor",
    "order_1", "order_2", "order_3", "order_4", "order_5",
    "station_1", "station_2", "station_3", "station_4", "station_5",
    "amr_1", "amr_2",
    "factory_ws",
    "factory_prosa_org", "factory_adacor_org"
]

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Phase 4 JCM and ASL.")
    parser.add_argument("--run-count", type=int, default=30)
    parser.add_argument("--template", default="factory.jcm.template")
    parser.add_argument("--output-jcm", default="build/phase4_jcm/factory_phase4.jcm")
    parser.add_argument("--output-asl-dir", default="build/phase4_asl")
    parser.add_argument("--source-asl-dir", default="src/agt")
    return parser.parse_args()

def rewrite_content(content: str, run_id: int) -> str:
    for token in CANONICAL_TOKENS:
        content = re.sub(rf'\b{token}\b', f"{token}_{run_id}", content)
    return content

def validate_asl(content: str, filename: str) -> None:
    for token in CANONICAL_TOKENS:
        if re.search(rf'\b{token}\b', content):
            print(f"VALIDATION FAILED: Found bare canonical token '{token}' in {filename} after rewrite.")
            sys.exit(1)

def validate_structural(jcm_content: str, asl_dir: Path) -> None:
    jcm_agents = set(re.findall(r'agent\s+([a-zA-Z0-9_]+)\s*:', jcm_content))
    
    for asl_file in asl_dir.rglob("*.asl"):
        content = asl_file.read_text(encoding="utf-8")
        send_targets = re.findall(r'\.send\(([^,]+),', content)
        for target in send_targets:
            target = target.strip()
            if target[0].isupper() or target.startswith('['):
                continue
            if target not in jcm_agents:
                print(f"STRUCTURAL VALIDATION FAILED: Agent target '{target}' in {asl_file} not found in JCM agents!")
                sys.exit(1)

def main() -> None:
    args = parse_args()
    template_path = Path(args.template)
    output_jcm_path = Path(args.output_jcm)
    output_asl_dir = Path(args.output_asl_dir)
    source_asl_dir = Path(args.source_asl_dir)

    template = template_path.read_text(encoding="utf-8")
    
    lines = template.splitlines()
    inner_lines = []
    for line in lines:
        if line.strip().startswith("mas factory_twin {") or line.strip() == "}":
            continue
        inner_lines.append(line)
    template_inner = "\n".join(inner_lines)

    output_jcm_path.parent.mkdir(parents=True, exist_ok=True)
    if output_asl_dir.exists():
        shutil.rmtree(output_asl_dir)
    output_asl_dir.mkdir(parents=True, exist_ok=True)

    mega_jcm_blocks = []
    mega_jcm_blocks.append("mas factory_twin_phase4 {")

    for run_id in range(args.run_count):
        run_asl_dir = output_asl_dir / f"run_{run_id}"
        run_asl_dir.mkdir(parents=True, exist_ok=True)
        for asl_file in source_asl_dir.glob("*.asl"):
            content = asl_file.read_text(encoding="utf-8")
            rewritten_content = rewrite_content(content, run_id)
            validate_asl(rewritten_content, str(asl_file))
            (run_asl_dir / asl_file.name).write_text(rewritten_content, encoding="utf-8")
        
        rendered_jcm = template_inner.replace("{{RUN_ID}}", str(run_id))
        rendered_jcm = rewrite_content(rendered_jcm, run_id)
        
        def inject_asl_path(match):
            agent_name = match.group(1)
            asl_file = match.group(2)
            return f"agent {agent_name} : {run_asl_dir}/{asl_file} {{"
            
        rendered_jcm = re.sub(r'agent\s+([a-zA-Z0-9_]+)\s*:\s*([a-zA-Z0-9_.]+\.asl)\s*\{', inject_asl_path, rendered_jcm)
        mega_jcm_blocks.append(rendered_jcm)

    mega_jcm_blocks.append("}")
    
    full_jcm_content = "\n".join(mega_jcm_blocks)
    output_jcm_path.write_text(full_jcm_content, encoding="utf-8")

    validate_structural(full_jcm_content, output_asl_dir)

    print(f"Generated mega JCM file successfully with {args.run_count} isolated runs.")

if __name__ == "__main__":
    main()