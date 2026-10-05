#!/usr/bin/env python3
"""Generate the official PMP-style ENSO portrait plot for selected models."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path


COLLECTIONS = ["ENSO_perf", "ENSO_proc", "ENSO_tel"]


def convert_results(metrics_root: Path, output: Path) -> dict[str, str]:
    """Convert this project's per-run files to the PMP RESULTS/model schema."""
    converted = {}
    collection_models = {}
    json_dir = output / "pmp_json"
    json_dir.mkdir(parents=True, exist_ok=True)
    for collection in COLLECTIONS:
        models = {}
        for path in sorted((metrics_root / collection).glob("*.json")):
            data = json.loads(path.read_text())
            model = data["model"]
            member = data["member"]
            result = deepcopy(data["result"])
            valid_metrics = {
                name: body
                for name, body in result.get("value", {}).items()
                if body.get("metric")
            }
            if not valid_metrics:
                print(f"跳过 {collection} {model}：没有有效 metric 值")
                continue
            result["value"] = valid_metrics
            metadata = result.get("metadata", {}).get("metrics", {})
            result.get("metadata", {})["metrics"] = {
                name: body for name, body in metadata.items() if name in valid_metrics
            }
            models.setdefault(model, {})[member] = result
        collection_models[collection] = models

    available = [set(models) for models in collection_models.values() if models]
    common_models = set.intersection(*available) if available else set()
    if not common_models:
        return converted
    dropped = sorted(set().union(*available) - common_models)
    if dropped:
        print("完整三面板图排除缺少 collection 的模式: " + ", ".join(dropped))

    for collection in COLLECTIONS:
        models = collection_models.get(collection, {})
        if not models:
            print(f"跳过 {collection}：没有计算结果")
            continue
        models = {name: models[name] for name in sorted(common_models)}
        target = json_dir / f"selected_cmip6_historical_{collection}.json"
        target.write_text(json.dumps({"RESULTS": {"model": models}}, indent=2, default=str) + "\n")
        converted[collection] = str(target)
    return converted


def split_ensemble_rows(selected: dict[str, str], output: Path) -> dict[str, str]:
    """Represent each model/member pair as a separate PMP model row."""
    target_dir = output / "pmp_json_ensembles"
    target_dir.mkdir(parents=True, exist_ok=True)
    converted = {}
    for collection, source in selected.items():
        data = json.loads(Path(source).read_text())
        models = data["RESULTS"]["model"]
        rows = {}
        for model, members in models.items():
            for member, result in members.items():
                rows[f"{model}_{member}"] = {member: result}
        target = target_dir / f"selected_cmip6_historical_{collection}.json"
        target.write_text(json.dumps({"RESULTS": {"model": rows}}, indent=2, default=str) + "\n")
        converted[collection] = str(target)
    return converted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", type=Path, default=Path("results_gadi/metrics"))
    parser.add_argument("--output", type=Path, default=Path("results_gadi/plots"))
    parser.add_argument("--obs-json-root", type=Path, default=Path("share/EnsoMetrics"))
    parser.add_argument(
        "--reduced-set",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use PMP's reduced metric set (use --no-reduced-set for all metrics)",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    selected = convert_results(args.metrics, args.output)
    missing = [name for name in COLLECTIONS if name not in selected]
    if missing:
        raise SystemExit("缺少 collection 结果，不能生成完整 PMP portrait plot: " + ", ".join(missing))

    try:
        from pcmdi_metrics.enso.lib import enso_portrait_plot
    except ImportError as exc:
        raise SystemExit("缺少 pcmdi_metrics；请先运行 MODE=setup ./run_enso_gadi.sh") from exc

    obs_paths = {
        "ENSO_perf": args.obs_json_root / "obs2obs_historical_ENSO_perf_v20201231_allObservations.json",
        "ENSO_proc": args.obs_json_root / "obs2obs_historical_ENSO_proc_v20201231_allObservations.json",
        "ENSO_tel": args.obs_json_root / "obs2obs_historical_ENSO_tel_v20201231_allObservations.json",
    }
    paths = {
        "CMIP6": selected,
        "obs2obs": {name: str(path) for name, path in obs_paths.items()},
    }
    plot_suffix = "" if args.reduced_set else "_all_metrics"
    figure_name = str(args.output / f"ENSO_selected_models_PMP_portrait_plot{plot_suffix}.png")
    fig, reference_info = enso_portrait_plot(
        COLLECTIONS,
        ["CMIP6"],
        [],
        paths,
        figure_name=figure_name,
        reduced_set=args.reduced_set,
    )
    reference_path = args.output / f"ENSO_selected_models_PMP_reference_info{plot_suffix}.json"
    reference_path.write_text(json.dumps(reference_info, indent=2, default=str) + "\n")
    print(figure_name)
    print(reference_path)
    # Some PMP versions return an open Matplotlib figure.
    try:
        import matplotlib.pyplot as plt
        plt.close(fig)
    except Exception:
        pass

    # The official plot averages members into one model row.  Also produce a
    # diagnostic portrait where every ensemble member is visible separately.
    ensemble_paths = {
        "CMIP6": split_ensemble_rows(selected, args.output),
        "obs2obs": {name: str(path) for name, path in obs_paths.items()},
    }
    ensemble_figure_name = str(
        args.output / f"ENSO_selected_ensembles_PMP_portrait_plot{plot_suffix}.png"
    )
    ensemble_fig, ensemble_reference_info = enso_portrait_plot(
        COLLECTIONS,
        ["CMIP6"],
        [],
        ensemble_paths,
        figure_name=ensemble_figure_name,
        reduced_set=args.reduced_set,
    )
    ensemble_reference_path = (
        args.output / f"ENSO_selected_ensembles_PMP_reference_info{plot_suffix}.json"
    )
    ensemble_reference_path.write_text(json.dumps(ensemble_reference_info, indent=2, default=str) + "\n")
    print(ensemble_figure_name)
    print(ensemble_reference_path)
    try:
        plt.close(ensemble_fig)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
