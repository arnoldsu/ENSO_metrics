#!/usr/bin/env python3
"""Create simple model-by-metric heatmaps from run_enso_gadi.py JSON output."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def numbers(value):
    if isinstance(value, dict):
        if "value" in value and isinstance(value["value"], (int, float)) and math.isfinite(value["value"]):
            yield float(value["value"])
        else:
            for child in value.values():
                yield from numbers(child)
    elif isinstance(value, list):
        for child in value:
            yield from numbers(child)


def metric_group(name: str) -> str | None:
    if name.startswith("Bias") or name.startswith("Seasonal"):
        return "eq_bias"
    if name.startswith("EnsoPrMap"):
        return "teleconnection"
    if name.startswith("EnsoFb") or name.startswith("Ensod"):
        return "feedback"
    if name.startswith("Enso"):
        return "enso"
    return None


def plot_heatmap(rows, metric_names, title, target):
    values = np.array([[row.get(metric, np.nan) for metric in metric_names] for _, row in rows])
    with np.errstate(invalid="ignore", divide="ignore"):
        spread = np.nanstd(values, axis=0)
        spread[spread == 0] = np.nan
        values = (values - np.nanmean(values, axis=0)) / spread
    fig, ax = plt.subplots(figsize=(max(10, len(metric_names) * 0.72), 3 + len(rows) * 0.42))
    image = ax.imshow(values, aspect="auto", cmap="RdBu_r", vmin=-2, vmax=2)
    ax.set_xticks(range(len(metric_names)), metric_names, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(rows)), [name for name, _ in rows], fontsize=8)
    ax.set_title(title)
    fig.colorbar(image, ax=ax, label="standardized value across model members")
    fig.tight_layout()
    fig.savefig(target, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("results_gadi/metrics"))
    parser.add_argument("--output", type=Path, default=Path("results_gadi/plots"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    for collection_dir in sorted(p for p in args.input.glob("ENSO_*") if p.is_dir()):
        rows = []
        for path in sorted(collection_dir.glob("*.json")):
            data = json.loads(path.read_text())
            metrics = data.get("result", {}).get("value", {})
            label = f"{data.get('model', path.stem)}_{data.get('member', '')}".rstrip("_")
            rows.append((label, {
                metric: (float(np.mean(vals)) if (vals := list(numbers(body.get("metric", {})))) else np.nan)
                for metric, body in metrics.items()
            }))
        if not rows:
            continue
        metric_names = sorted(set().union(*(row.keys() for _, row in rows)))
        values = np.array([[row.get(metric, np.nan) for metric in metric_names] for _, row in rows])
        # Column-wise z score makes different metric units comparable.
        with np.errstate(invalid="ignore", divide="ignore"):
            values = (values - np.nanmean(values, axis=0)) / np.nanstd(values, axis=0)
        fig, ax = plt.subplots(figsize=(max(12, len(metric_names) * 0.42), 2.5 + len(rows) * 0.55))
        image = ax.imshow(values, aspect="auto", cmap="RdBu_r", vmin=-2, vmax=2)
        ax.set_xticks(range(len(metric_names)), metric_names, rotation=90, fontsize=7)
        ax.set_yticks(range(len(rows)), [name for name, _ in rows])
        ax.set_title(f"{collection_dir.name}: standardized ENSO metric summary")
        fig.colorbar(image, ax=ax, label="standardized value across model members")
        fig.tight_layout()
        target = args.output / f"{collection_dir.name}_summary.png"
        fig.savefig(target, dpi=180)
        plt.close(fig)
        print(target)

    # Combine all collections, then produce complete thematic figures. A
    # metric repeated in more than one collection has the same definition;
    # the last finite result is retained for that model/member.
    combined = {}
    for collection_dir in sorted(p for p in args.input.glob("ENSO_*") if p.is_dir()):
        for path in sorted(collection_dir.glob("*.json")):
            data = json.loads(path.read_text())
            label = f"{data.get('model', path.stem)}_{data.get('member', '')}".rstrip("_")
            row = combined.setdefault(label, {})
            for metric, body in data.get("result", {}).get("value", {}).items():
                vals = list(numbers(body.get("metric", {})))
                if vals:
                    row[metric] = float(np.mean(vals))

    combined_rows = sorted(combined.items())
    all_metrics = sorted(set().union(*(row for _, row in combined_rows))) if combined_rows else []
    group_titles = {
        "eq_bias": "Equatorial bias and seasonal-cycle metrics",
        "enso": "ENSO performance metrics",
        "feedback": "ENSO feedback metrics",
        "teleconnection": "ENSO teleconnection metrics",
    }
    for group, title in group_titles.items():
        names = [name for name in all_metrics if metric_group(name) == group]
        if names:
            plot_heatmap(
                combined_rows,
                names,
                title,
                args.output / f"ENSO_{group}_all_metrics.png",
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
