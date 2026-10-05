#!/usr/bin/env python3
"""Generate ENSO Metrics dive-down figures from Gadi result JSON/NetCDF files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from EnsoPlots.EnsoMetricPlot import main_plotter


def values_for_plot(data: dict, metric: str, model: str, collection: str):
    value = data["value"][metric]
    diagnostic_values = {
        key: body.get("value") for key, body in value.get("diagnostic", {}).items()
    }
    metadata = data["metadata"]["metrics"][metric]
    diagnostic_units = metadata["diagnostic"].get("units", "")

    if collection == "ENSO_tel" and "Map" in metric:
        corr = metric.replace("Rmse", "Corr")
        rmse = metric.replace("Corr", "Rmse")
        if corr not in data["value"] or rmse not in data["value"]:
            raise KeyError(f"teleconnection pair is incomplete: {corr}, {rmse}")
        references = data["value"][corr]["metric"]
        metric_values = {}
        for reference in references:
            corr_value = data["value"][corr]["metric"][reference].get("value")
            rmse_value = data["value"][rmse]["metric"][reference].get("value")
            metric_values[reference] = {
                model: [None if corr_value is None else 1 - corr_value, rmse_value]
            }
        metric_units = [
            data["metadata"]["metrics"][corr]["metric"].get("units", ""),
            data["metadata"]["metrics"][rmse]["metric"].get("units", ""),
        ]
    else:
        metric_values = {
            reference: {model: body.get("value")}
            for reference, body in value.get("metric", {}).items()
        }
        metric_units = metadata["metric"].get("units", "")
    return diagnostic_values, diagnostic_units, metric_values, metric_units


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--collections", nargs="*", default=[])
    parser.add_argument("--models", nargs="*", default=[])
    parser.add_argument("--members", nargs="*", default=[])
    parser.add_argument("--metric-names", nargs="*", default=[])
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    failures = []
    plotted = 0
    collections = args.collections or ["ENSO_perf", "ENSO_proc", "ENSO_tel"]
    for collection in collections:
        for json_path in sorted((args.metrics / collection).glob("*.json")):
            wrapper = json.loads(json_path.read_text())
            model = wrapper["model"]
            member = wrapper["member"]
            if args.models and model not in args.models:
                continue
            if args.members and member not in args.members:
                continue
            data = wrapper["result"]
            names = sorted(data.get("value", {}))
            if args.metric_names:
                names = [name for name in names if name in args.metric_names]
            for metric in names:
                # Teleconnection Corr/Std values share the Map NetCDF and are
                # plotted together when processing the corresponding Rmse.
                if collection == "ENSO_tel" and "Map" in metric and not metric.endswith("Rmse"):
                    continue
                nc_metric = metric.replace("Rmse", "") if collection == "ENSO_tel" and "Map" in metric else metric
                nc_path = json_path.with_name(json_path.stem + f"_{nc_metric}.nc")
                if not nc_path.is_file():
                    failures.append(f"missing NetCDF: {nc_path}")
                    continue
                try:
                    plot_args = values_for_plot(data, metric, model, collection)
                    out_dir = args.output / collection / model / member / metric
                    out_dir.mkdir(parents=True, exist_ok=True)
                    prefix = f"CMIP6_historical_{collection}_{model}_{member}_{metric}"
                    main_plotter(
                        collection,
                        nc_metric,
                        model,
                        "historical",
                        str(nc_path),
                        *plot_args,
                        member=member,
                        path_png=str(out_dir),
                        name_png=prefix,
                    )
                    plotted += 1
                except Exception as exc:
                    failures.append(f"{collection} {model} {member} {metric}: {type(exc).__name__}: {exc}")
                    print("FAILED", failures[-1])

    report = args.output / "divedown_failures.txt"
    report.write_text("\n".join(failures) + ("\n" if failures else ""))
    print(f"Dive-down metrics plotted: {plotted}")
    print(f"Failures: {len(failures)} ({report})")
    return 0 if plotted else 1


if __name__ == "__main__":
    raise SystemExit(main())
