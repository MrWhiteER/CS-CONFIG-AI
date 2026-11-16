"""Compare two overlay-probe JSONL files: HUD off first, HUD on second."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Iterable, Optional


def percent_difference(before: Optional[float], after: Optional[float]) -> Optional[float]:
    return (after - before) / before * 100 if before not in (None, 0) and after is not None else None


def summarise(rows: Iterable[dict]) -> dict:
    rows = list(rows)
    modes = Counter()
    histogram = Counter()
    frames = total_ms = 0
    for row in rows:
        modes.update(row.get("present_modes", {}))
        histogram.update({float(key): count for key, count in row.get("frame_time_histogram_ms", {}).items()})
        frames += row.get("frame_count", 0)
        total_ms += row.get("frame_time_sum_ms", 0)
    count = sum(histogram.values())
    rank, accumulated, p99 = math.ceil(count * 0.99), 0, None
    for value, frequency in sorted(histogram.items()):
        accumulated += frequency
        if accumulated >= rank:
            p99 = value
            break

    def mean(key):
        values = [row[key] for row in rows if row.get(key) is not None]
        return statistics.fmean(values) if values else None

    total_modes = sum(modes.values())
    return {
        "samples": len(rows), "frame_count": frames,
        "fps": 1000 * frames / total_ms if total_ms else None,
        "one_percent_low": 1000 / p99 if p99 else None,
        "overlay_cpu_percent": mean("overlay_cpu_percent"),
        "working_set_mb": mean("working_set_mb"),
        "peak_working_set_mb": max((row["working_set_mb"] for row in rows
                                    if row.get("working_set_mb") is not None), default=None),
        "present_mode_share": {mode: frequency / total_modes * 100 for mode, frequency in modes.items()},
        "statuses": dict(Counter(row.get("status", "unknown") for row in rows)),
    }


def compare(before: dict, after: dict) -> dict:
    return {key: percent_difference(before[key], after[key]) for key in (
        "fps", "one_percent_low", "overlay_cpu_percent", "working_set_mb", "peak_working_set_mb")}


def load(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as stream:
        return summarise(json.loads(line) for line in stream if line.strip())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hud_off", type=Path)
    parser.add_argument("hud_on", type=Path)
    args = parser.parse_args(argv)
    try:
        before, after = load(args.hud_off), load(args.hud_on)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    changes = compare(before, after)

    def number(value, suffix=""):
        return f"{value:.3f}{suffix}" if value is not None else "--"

    print(f"HUD off: {args.hud_off}\nHUD on:  {args.hud_on}")
    print(f"{'Metric':<28} {'HUD off':>12} {'HUD on':>12} {'Change':>12}")
    for key, label in (("fps", "Average FPS"), ("one_percent_low", "1% low FPS (run p99)"),
                       ("overlay_cpu_percent", "Overlay CPU % (total CPU)"),
                       ("working_set_mb", "Overlay RAM MB (mean)"),
                       ("peak_working_set_mb", "Overlay RAM MB (peak)")):
        print(f"{label:<28} {number(before[key]):>12} {number(after[key]):>12} {number(changes[key], '%'):>12}")
    print("PresentMode share (relative change; pp = percentage points):")
    for mode in sorted(before["present_mode_share"].keys() | after["present_mode_share"].keys()):
        left = before["present_mode_share"].get(mode, 0)
        right = after["present_mode_share"].get(mode, 0)
        print(f"  {mode}: {left:.2f}% -> {right:.2f}%  "
              f"({number(percent_difference(left, right), '%')}, {right - left:+.2f} pp)")
    for label, result in (("HUD off", before), ("HUD on", after)):
        print(f"{label}: {result['samples']} seconds sampled, {result['frame_count']} frames")
        for status, count in result["statuses"].items():
            print(f"  {status}: {count}")
    if not before["frame_count"] or not after["frame_count"]:
        print("No frame comparison available: both runs need CS2 frame data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
