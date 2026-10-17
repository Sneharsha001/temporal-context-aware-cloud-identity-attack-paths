#!/usr/bin/env python3
"""
scripts/simulate_probe_sequence.py - Simulates an interactive probe sequence trajectory.
"""

import argparse
import sys
from typing import List

# Ensure UTF-8 output on Windows terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def simulate(probes: List[str]):
    print("=" * 60)
    print(" ARF-RT Probe Sequence Replay Simulator")
    print("=" * 60)
    entropy = 0.560
    for idx, probe in enumerate(probes):
        delta = 0.180 if idx == 0 else 0.120
        new_entropy = max(0.0, entropy - delta)
        print(f"Step {idx + 1}: Probing edge '{probe}'")
        print(f"  Observed: ALLOW  |  Entropy: {entropy:.3f} -> {new_entropy:.3f} nats (-{delta:.3f})")
        entropy = new_entropy
    print("=" * 60)
    print(f"Final Entropy: {entropy:.3f} nats. Target state reached.")


def main():
    parser = argparse.ArgumentParser(description="Simulate probe sequence")
    parser.add_argument("--probes", nargs="+", default=["edge_e1", "edge_e3", "edge_e4"])
    args = parser.parse_args()

    simulate(args.probes)


if __name__ == "__main__":
    main()
