#!/usr/bin/env python
"""
scripts/score_credentials.py - CLI for temporal credential risk scoring.

Reads a CloudTrail log file (or inline JSON), extracts temporal hints,
scores each credential edge for exploitation risk, and outputs results
as JSON, NDJSON, CSV, or a human-readable summary table.

Usage
-----
    python scripts/score_credentials.py --input path/to/cloudtrail.json
    python scripts/score_credentials.py --input log.json --format csv --out report.csv
    python scripts/score_credentials.py --input log.json --top 10 --format table
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is importable when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arf_rt.temporal.cloudtrail_parser import extract_hints_from_log
from arf_rt.temporal.credential_scorer import CredentialScorer, ScoringConfig
from arf_rt.temporal.temporal_exporter import TemporalExporter


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="score_credentials",
        description="Score cloud credential edges for temporal exploitation risk.",
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        metavar="PATH",
        help="Path to a CloudTrail log file (JSON array of event records).",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["json", "ndjson", "csv", "table"],
        default="table",
        help="Output format (default: table).",
    )
    parser.add_argument(
        "--out", "-o",
        metavar="PATH",
        default=None,
        help="Write output to a file instead of stdout.",
    )
    parser.add_argument(
        "--top", "-n",
        type=int,
        default=0,
        metavar="N",
        help="Only output the top-N highest-risk edges (0 = all).",
    )
    parser.add_argument(
        "--ttl-ref",
        type=float,
        default=3600.0,
        metavar="SECONDS",
        help="Reference TTL in seconds for expiry scoring (default: 3600).",
    )
    parser.add_argument(
        "--stale-ref",
        type=float,
        default=86400.0,
        metavar="SECONDS",
        help="Reference staleness window in seconds (default: 86400).",
    )
    parser.add_argument(
        "--expiry-weight",
        type=float,
        default=0.50,
        help="Weight for expiry factor in composite score (default: 0.50).",
    )
    parser.add_argument(
        "--stale-weight",
        type=float,
        default=0.30,
        help="Weight for staleness factor in composite score (default: 0.30).",
    )
    return parser


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_table(scores) -> str:
    """Render a human-readable risk score table."""
    col_widths = [30, 8, 10, 13, 15, 18]
    headers = [
        "Edge ID", "Score", "Tier",
        "Expiry Factor", "Stale Factor", "Short-Lived Bonus",
    ]
    sep = "  ".join("-" * w for w in col_widths)
    header_row = "  ".join(h.ljust(w) for h, w in zip(headers, col_widths))

    lines = [header_row, sep]
    for s in scores:
        row = [
            s.edge_id[:30].ljust(col_widths[0]),
            f"{s.score:.4f}".ljust(col_widths[1]),
            s.label.ljust(col_widths[2]),
            f"{s.expiry_factor:.4f}".ljust(col_widths[3]),
            f"{s.staleness_factor:.4f}".ljust(col_widths[4]),
            f"{s.short_lived_bonus:.4f}".ljust(col_widths[5]),
        ]
        lines.append("  ".join(row))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Load CloudTrail log
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[error] Input file not found: {input_path}", file=sys.stderr)
        return 1

    try:
        raw = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[error] Failed to parse JSON: {exc}", file=sys.stderr)
        return 1

    # Support both plain arrays and CloudTrail envelope format
    if isinstance(raw, dict) and "Records" in raw:
        events = raw["Records"]
    elif isinstance(raw, list):
        events = raw
    else:
        print("[error] Unexpected JSON structure. Expected array or {Records: [...]}.", file=sys.stderr)
        return 1

    # Extract hints
    hints = extract_hints_from_log(events)
    if not hints:
        print("[warn] No temporal hints extracted from log.", file=sys.stderr)
        return 0

    # Build scorer
    config = ScoringConfig(
        reference_ttl_seconds=args.ttl_ref,
        reference_stale_seconds=args.stale_ref,
        expiry_weight=args.expiry_weight,
        staleness_weight=args.stale_weight,
    )
    scorer = CredentialScorer(config=config, reference_time=datetime.now(tz=timezone.utc))
    scores = scorer.score_all(list(hints.values()))

    # Apply top-N filter
    if args.top and args.top > 0:
        scores = scores[:args.top]

    # Render output
    exporter = TemporalExporter()
    fmt = args.format
    if fmt == "json":
        output = exporter.scores_to_json(scores)
    elif fmt == "ndjson":
        output = exporter.scores_to_ndjson(scores)
    elif fmt == "csv":
        output = exporter.scores_to_csv(scores)
    else:  # table
        output = _render_table(scores)

    # Write output
    if args.out:
        out_path = Path(args.out)
        out_path.write_text(output, encoding="utf-8")
        print(f"[info] Wrote {len(scores)} scored edges to {out_path}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
