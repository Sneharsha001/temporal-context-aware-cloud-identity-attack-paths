#!/usr/bin/env python3
"""
scripts/generate_synthetic_cloudtrail.py - CLI tool to generate synthetic CloudTrail logs.

Generates AWS CloudTrail JSON exports for benchmarking temporal post-filters and
testing anomaly detection pipelines under controlled conditions.

Usage::

    python scripts/generate_synthetic_cloudtrail.py --nodes UserA,RoleB,RoleC --out events.json
    python scripts/generate_synthetic_cloudtrail.py --nodes UserA,RoleB,RoleC --anomaly causal_inversion
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arf_rt.temporal.synthetic_generator import (
    CloudTrailSyntheticGenerator,
    SyntheticGeneratorConfig,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate synthetic CloudTrail AssumeRole logs for benchmarking."
    )
    parser.add_argument(
        "--nodes",
        type=str,
        required=True,
        help="Comma-separated chain of IAM principals and roles (e.g. 'UserA,RoleB,TargetRole').",
    )
    parser.add_argument(
        "--anomaly",
        type=str,
        choices=["causal_inversion", "session_expired", "concurrency"],
        default=None,
        help="Inject a specific temporal anomaly into the generated stream.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Interval between hops in seconds (default: 60).",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=3600,
        help="STS session duration in seconds (default: 3600).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON file path (prints to stdout if omitted).",
    )

    args = parser.parse_args()

    nodes = [n.strip() for n in args.nodes.split(",") if n.strip()]
    if len(nodes) < 2:
        print("Error: Must specify at least two nodes to generate hops.", file=sys.stderr)
        return 1

    config = SyntheticGeneratorConfig(
        hop_interval_seconds=args.interval,
        session_duration_seconds=args.duration,
    )
    generator = CloudTrailSyntheticGenerator(config=config)
    events = generator.generate_path_events(nodes, inject_anomaly=args.anomaly)

    payload = {"Records": events}
    rendered = json.dumps(payload, indent=2)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
        print(f"Generated {len(events)} CloudTrail events -> {args.out}")
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    sys.exit(main())
