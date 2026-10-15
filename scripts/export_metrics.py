#!/usr/bin/env python3
"""
export_metrics.py - Export ARF-RT research metrics to CSV, JSON, and Markdown formats.
"""

import argparse
import csv
import json
import sys
from pathlib import Path


def export_to_csv(data: dict, output_file: Path):
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Metric", "Value"])
        for k, v in data.items():
            writer.writerow([k, v])
    print(f"Exported metrics to CSV: {output_file}")


def export_to_markdown(data: dict, output_file: Path):
    lines = ["# ARF-RT Evaluation Metrics Summary\n", "| Metric | Value |", "|---|---|"]
    for k, v in data.items():
        lines.append(f"| `{k}` | {v} |")
    output_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"Exported metrics to Markdown: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Export research evaluation metrics")
    parser.add_argument("--input", type=Path, default=Path("verification/execution_summary.json"), help="Source metrics JSON")
    parser.add_argument("--format", choices=["csv", "md", "all"], default="all", help="Output format")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/metrics"), help="Destination directory")
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Input file not found: {args.input}")
        sys.exit(1)

    data = json.loads(args.input.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.format in ("csv", "all"):
        export_to_csv(data, args.output_dir / "metrics_summary.csv")
    if args.format in ("md", "all"):
        export_to_markdown(data, args.output_dir / "metrics_summary.md")


if __name__ == "__main__":
    main()
