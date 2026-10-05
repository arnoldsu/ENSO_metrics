#!/usr/bin/env python3
"""Discover Gadi CMIP6/OBS files and run ENSO metric collections.

This driver uses native NetCDF files.  It intentionally does not use the
legacy cdscan/XML workflow in the examples shipped with ENSO_metrics.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable


DEFAULT_MODELS = [
    "ACCESS-CM2",
    "ACCESS-ESM1-5",
    "TaiESM1",
    "CESM2",
]
DEFAULT_COLLECTIONS = ["ENSO_perf", "ENSO_proc", "ENSO_tel"]
DEFAULT_CMIP_ROOTS = [
    Path("/g/data/fs38/publications/CMIP6"),
    Path("/g/data/oi10/replicas/CMIP6"),
]
DEFAULT_OBS_ROOTS = [
    Path("/g/data/ct11/access-nri/replicas/esmvaltool/obsdata-v2"),
    Path("/g/data/kj13/datasets/esmvaltool/obsdata-v2"),
    Path("/g/data/ct11/access-nri/era5-derived"),
]

MODEL_VARIABLES = {
    "sst": ("Omon", "tos"),
    "pr": ("Amon", "pr"),
    "taux": ("Amon", "tauu"),
    "tauy": ("Amon", "tauv"),
    "ssh": ("Omon", "zos"),
    "lhf": ("Amon", "hfls"),
    "shf": ("Amon", "hfss"),
    "lwr": ("Amon", ["rlds", "rlus"]),
    "swr": ("Amon", ["rsds", "rsus"]),
    "thf": ("Amon", ["hfls", "hfss", "rlds", "rlus", "rsds", "rsus"]),
}
ALGEBRA = {
    "lwr": ["plus", "minus"],
    "swr": ["plus", "minus"],
    "thf": ["plus", "plus", "plus", "minus", "plus", "minus"],
}


def split_paths(value: str | None, defaults: list[Path]) -> list[Path]:
    if not value:
        return defaults
    return [Path(item) for item in value.split(":") if item]


def latest_files(variable_dir: Path) -> list[str]:
    """Return NetCDFs from the lexically latest archive version."""
    versions = sorted(variable_dir.glob("files/*"))
    if not versions:
        versions = sorted(path for path in variable_dir.glob("v*") if path.is_dir())
    for directory in reversed(versions):
        files = sorted(str(path) for path in directory.glob("*.nc"))
        if files:
            return files
    return []


def locate_model_root(cmip_roots: Iterable[Path], model: str, member: str) -> Path | None:
    candidates: list[Path] = []
    for root in cmip_roots:
        candidates.extend(root.glob(f"CMIP/*/{model}/historical/{member}"))
        candidates.extend(root.glob(f"*/CMIP/*/{model}/historical/{member}"))
        candidates.extend(root.glob(f"*/*/{model}/historical/{member}"))
    return sorted(set(candidates))[0] if candidates else None


def variable_files(model_root: Path, table: str, variable: str) -> list[str]:
    grid_dirs = sorted((model_root / table / variable).glob("*"))
    # Prefer native grid, then common-grid products.
    grid_dirs.sort(key=lambda p: (p.name != "gn", p.name))
    for grid_dir in grid_dirs:
        files = latest_files(grid_dir)
        if files:
            return files
    return []


def optional_static(model_root: Path, table: str, variable: str) -> tuple[str | None, str | None]:
    files = variable_files(model_root, table, variable)
    return (files[0], variable) if files else (None, None)


def make_entry(model_root: Path, logical_name: str, table: str, variables) -> dict | None:
    names = variables if isinstance(variables, list) else [variables]
    paths = [variable_files(model_root, table, name) for name in names]
    if any(not group for group in paths):
        return None

    area_table, area_var = ("Ofx", "areacello") if table.startswith("O") else ("fx", "areacella")
    area_path, area_name = optional_static(model_root, area_table, area_var)
    land_path, land_name = (None, None)
    if not table.startswith("O"):
        land_path, land_name = optional_static(model_root, "fx", "sftlf")

    entry = {
        "path + filename": (
            [group[0] if len(group) == 1 else group for group in paths]
            if isinstance(variables, list)
            else (paths[0][0] if len(paths[0]) == 1 else paths[0])
        ),
        "varname": variables,
        "path + filename_area": ([area_path] * len(names) if isinstance(variables, list) else area_path),
        "areaname": ([area_name] * len(names) if isinstance(variables, list) else area_name),
        "path + filename_landmask": ([land_path] * len(names) if isinstance(variables, list) else land_path),
        "landmaskname": ([land_name] * len(names) if isinstance(variables, list) else land_name),
    }
    if logical_name in ALGEBRA:
        entry["algebric_calculation"] = ALGEBRA[logical_name]
    return entry


def first_match(roots: Iterable[Path], product: str, patterns: list[str]) -> str | None:
    # Pattern order is a preference order (for example Omon tos before Amon ts).
    for pattern in patterns:
        matches: list[Path] = []
        for root in roots:
            if not root.is_dir():
                continue
            for directory in root.glob(f"Tier*/{product}"):
                matches.extend(directory.rglob(pattern))
        unique = sorted(set(matches), key=lambda p: ("OBS" not in p.name, str(p)))
        if unique:
            return str(unique[0])
    return None


def observation_dictionary(obs_roots: list[Path]) -> dict:
    hadisst = first_match(obs_roots, "HadISST", ["*Omon_tos_*.nc"])
    gpcp = first_match(obs_roots, "GPCP-SG", ["OBS*_Amon_pr_*.nc", "pr_GPCP-SG_L3_v2.3_*.nc"])
    trop_sst = first_match(obs_roots, "TROPFLUX", ["*Omon_tos_*.nc", "*Amon_ts_*.nc"])
    trop_taux = first_match(obs_roots, "TROPFLUX", ["*Amon_tauu_*.nc"])
    trop_hfds = first_match(obs_roots, "TROPFLUX", ["*Omon_hfds_*.nc"])
    cmems = first_match(obs_roots, "CMEMS", ["*Omon_zos_*.nc"])

    observations: dict = {}
    if hadisst:
        observations["HadISST"] = {
            "sst": {"path + filename": hadisst, "varname": "tos", "obs_interpreter": "CMIP"}
        }
    if gpcp:
        observations["GPCPv2.3"] = {
            "pr": {"path + filename": gpcp, "varname": "pr", "obs_interpreter": "CMIP"}
        }
    trop: dict = {}
    if trop_sst:
        trop["sst"] = {"path + filename": trop_sst, "varname": "tos" if "_tos_" in trop_sst else "ts",
                       "obs_interpreter": "CMIP"}
    if trop_taux:
        trop["taux"] = {"path + filename": trop_taux, "varname": "tauu", "obs_interpreter": "CMIP"}
    if trop_hfds:
        trop["thf"] = {"path + filename": trop_hfds, "varname": "hfds", "obs_interpreter": "CMIP"}
    if trop:
        observations["Tropflux"] = trop
    if cmems:
        observations["AVISO"] = {
            "ssh": {"path + filename": cmems, "varname": "zos", "obs_interpreter": "CMIP"}
        }
    return observations


def build_inventory(models, member, cmip_roots, obs_roots) -> dict:
    inventory = {"cmip_roots": [str(p) for p in cmip_roots], "obs_roots": [str(p) for p in obs_roots],
                 "member": member, "models": {}, "observations": {}}
    observations = observation_dictionary(obs_roots)
    for name, variables in observations.items():
        inventory["observations"][name] = {key: value["path + filename"] for key, value in variables.items()}
    for model in models:
        root = locate_model_root(cmip_roots, model, member)
        info = {"root": str(root) if root else None, "variables": {}, "unsupported_split": {}}
        if root:
            for logical, (table, variables) in MODEL_VARIABLES.items():
                entry = make_entry(root, logical, table, variables)
                if entry and "unsupported_split_files" in entry:
                    info["unsupported_split"][logical] = entry["unsupported_split_files"]
                elif entry:
                    info["variables"][logical] = entry["path + filename"]
        inventory["models"][model] = info
    return inventory


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["inventory", "compute"], default="inventory")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--collections", nargs="+", default=DEFAULT_COLLECTIONS)
    parser.add_argument("--member", default="r1i1p1f1")
    parser.add_argument("--cmip-roots", help="Colon-separated CMIP6 roots")
    parser.add_argument("--obs-roots", help="Colon-separated OBS roots")
    parser.add_argument("--output", type=Path, default=Path("results_gadi"))
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    cmip_roots = split_paths(args.cmip_roots or os.getenv("CMIP6_ROOTS"), DEFAULT_CMIP_ROOTS)
    obs_roots = split_paths(args.obs_roots or os.getenv("OBS_ROOTS"), DEFAULT_OBS_ROOTS)
    inventory = build_inventory(args.models, args.member, cmip_roots, obs_roots)
    inventory_path = args.output / "manifests" / "inventory.json"
    save_json(inventory_path, inventory)
    print(f"数据清单: {inventory_path}")
    for model, info in inventory["models"].items():
        print(f"{model}: root={info['root']}, variables={sorted(info['variables'])}, "
              f"split={sorted(info['unsupported_split'])}")

    if args.mode == "inventory":
        return 0

    from EnsoMetrics.EnsoComputeMetricsLib import ComputeCollection

    observations = observation_dictionary(obs_roots)
    if not observations:
        raise RuntimeError("没有找到可用观测数据")

    failures = []
    for model in args.models:
        model_root = locate_model_root(cmip_roots, model, args.member)
        if model_root is None:
            failures.append({"model": model, "error": "CMIP6 historical member not found"})
            continue
        model_data = {}
        for logical, (table, variables) in MODEL_VARIABLES.items():
            entry = make_entry(model_root, logical, table, variables)
            if entry and "unsupported_split_files" not in entry:
                model_data[logical] = entry
        dataset_name = f"{model}_{args.member}"
        datasets = {"model": {dataset_name: model_data}, "observations": observations}
        for collection in args.collections:
            stem = args.output / "metrics" / collection / f"{collection}_CMIP6_{model}_historical_{args.member}"
            stem.parent.mkdir(parents=True, exist_ok=True)
            try:
                result, dive = ComputeCollection(
                    collection, datasets, dataset_name, debug=args.debug,
                    dive_down=True, netcdf=True, netcdf_name=str(stem),
                )
                save_json(stem.with_suffix(".json"), {
                    "model": model, "member": args.member, "collection": collection,
                    "result": result, "dive_down": dive,
                })
            except Exception as exc:
                failures.append({"model": model, "collection": collection,
                                 "error": f"{type(exc).__name__}: {exc}"})
                print(f"失败 {model} {collection}: {exc}")
    model_tag = "-".join(args.models)
    collection_tag = "-".join(args.collections)
    save_json(
        args.output / "manifests" / f"failures_{model_tag}_{collection_tag}.json",
        failures,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
