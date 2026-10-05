#!/usr/bin/env bash
#PBS -P p66
#PBS -q normal
#PBS -l walltime=06:00:00
#PBS -l mem=64GB
#PBS -l ncpus=4
#PBS -l storage=gdata/p66+gdata/fs38+gdata/oi10+gdata/ct11+gdata/kj13+scratch/p66
#PBS -l wd
#PBS -j oe

set -euo pipefail

REPO=/g/data/p66/ars599/ENSO_metrics
MODE=${MODE:-inventory}          # setup | check | inventory | compute | plot | pmp_plot | all
ENV_PREFIX=${ENSO_ENV_PREFIX:-/scratch/p66/ars599/enso_metrics_env}
if [[ -n "${ENSO_PYTHON:-}" ]]; then
  PYTHON=${ENSO_PYTHON}
elif [[ -x "${ENV_PREFIX}/bin/python" ]]; then
  PYTHON=${ENV_PREFIX}/bin/python
else
  PYTHON=python3
fi
OUTPUT=${ENSO_OUTPUT:-${REPO}/results_gadi}
CACHE=${ENSO_CACHE:-/scratch/p66/ars599/enso_metrics_cache}
MEMBER=${ENSO_MEMBER:-r1i1p1f1}
MODELS=${ENSO_MODELS:-"ACCESS-CM2 ACCESS-ESM1-5 TaiESM1 CESM2"}
COLLECTIONS=${ENSO_COLLECTIONS:-"ENSO_perf ENSO_proc ENSO_tel"}
REDUCED_SET=${ENSO_REDUCED_SET:-true}
DIVEDOWN_METRICS=${ENSO_DIVEDOWN_METRICS:-}
DIVEDOWN_MEMBERS=${ENSO_DIVEDOWN_MEMBERS:-}
CMIP6_ROOTS=${CMIP6_ROOTS:-/g/data/fs38/publications/CMIP6:/g/data/oi10/replicas/CMIP6}
OBS_ROOTS=${OBS_ROOTS:-/g/data/ct11/access-nri/replicas/esmvaltool/obsdata-v2:/g/data/kj13/datasets/esmvaltool/obsdata-v2:/g/data/ct11/access-nri/era5-derived}

cd "${REPO}"
mkdir -p "${OUTPUT}/logs"
mkdir -p "${CACHE}"
exec > >(tee -a "${OUTPUT}/logs/${MODE}_$(date -u +%Y%m%dT%H%M%SZ).log") 2>&1

# Gadi's preloaded analysis3 module exports paths to its own ESMF/GDAL/PROJ
# libraries. They must not leak into the isolated ENSO environment.
if [[ "${PYTHON}" == "${ENV_PREFIX}/bin/python" ]]; then
  unset ESMFMKFILE PYTHONPATH LD_LIBRARY_PATH GDAL_DRIVER_PATH GDAL_DATA PROJ_LIB PROJ_DATA
  export PYTHONNOUSERSITE=1
  export PROJ_DATA="${ENV_PREFIX}/share/proj"
  export GDAL_DATA="${ENV_PREFIX}/share/gdal"
fi
export XDG_CACHE_HOME="${CACHE}"
export CARTOPY_DATA_DIR="${CACHE}/cartopy"
mkdir -p "${CARTOPY_DATA_DIR}"

echo "开始时间: $(date -u)"
echo "模式: ${MODELS}"
echo "集合: ${COLLECTIONS}"
echo "Python: $(${PYTHON} --version 2>&1)"

# The conda-forge enso_metrics package installs a physical EnsoMetrics/
# directory which can shadow this checkout even after ``pip install -e``.
# Expose this checkout as the package explicitly so jobs always run the
# patched Python 3 code in REPO.
LOCAL_PACKAGES="${CACHE}/pythonpath"
mkdir -p "${LOCAL_PACKAGES}"
ln -sfn "${REPO}/lib" "${LOCAL_PACKAGES}/EnsoMetrics"
ln -sfn "${REPO}/plots" "${LOCAL_PACKAGES}/EnsoPlots"
export PYTHONPATH="${LOCAL_PACKAGES}:${REPO}:${PYTHONPATH:-}"

check_python() {
  "${PYTHON}" - <<'PY'
import importlib
import sys

required = ["numpy", "scipy", "xarray", "cftime", "netCDF4", "matplotlib", "cartopy", "xesmf"]
failed = False
for name in required:
    try:
        module = importlib.import_module(name)
        print(f"{name}: {getattr(module, '__version__', 'installed')}")
    except Exception as exc:
        failed = True
        print(f"ERROR {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
for name in ["xcdat", "regionmask", "cmocean"]:
    try:
        module = importlib.import_module(name)
        print(f"{name}: {getattr(module, '__version__', 'installed')}")
    except Exception as exc:
        print(f"WARNING {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
if failed:
    raise SystemExit(2)
PY
}

setup_env() {
  local mamba=/opt/conda/analysis3-26.01/bin/mamba
  local mamba_root=/scratch/p66/ars599/tmp/mamba-root
  local package_cache=/scratch/p66/ars599/tmp/conda-pkgs
  [[ -x "${mamba}" ]] || { echo "找不到 mamba: ${mamba}" >&2; exit 2; }
  mkdir -p "${mamba_root}" "${package_cache}"
  export MAMBA_ROOT_PREFIX="${mamba_root}"
  export CONDA_PKGS_DIRS="${package_cache}"
  if [[ -x "${ENV_PREFIX}/bin/python" ]]; then
    "${mamba}" env update --yes --prefix "${ENV_PREFIX}" --file environment-enso.yml
  else
    "${mamba}" env create --yes --prefix "${ENV_PREFIX}" --file environment-enso.yml
  fi
  "${ENV_PREFIX}/bin/python" -m pip install --no-deps -e "${REPO}"
  echo "环境已建立: ${ENV_PREFIX}"
}

inventory() {
  "${PYTHON}" scripts/run_enso_gadi.py \
    --mode inventory --models ${MODELS} --member "${MEMBER}" \
    --cmip-roots "${CMIP6_ROOTS}" --obs-roots "${OBS_ROOTS}" --output "${OUTPUT}"
}

compute() {
  check_python
  "${PYTHON}" scripts/run_enso_gadi.py \
    --mode compute --models ${MODELS} --collections ${COLLECTIONS} --member "${MEMBER}" \
    --cmip-roots "${CMIP6_ROOTS}" --obs-roots "${OBS_ROOTS}" --output "${OUTPUT}"
}

plot() {
  "${PYTHON}" scripts/plot_enso_gadi_summary.py \
    --input "${OUTPUT}/metrics" --output "${OUTPUT}/plots"
}

pmp_plot() {
  local reduced_arg=--reduced-set
  case "${REDUCED_SET,,}" in
    0|false|no|off) reduced_arg=--no-reduced-set ;;
    1|true|yes|on) ;;
    *) echo "ENSO_REDUCED_SET 必须是 true 或 false" >&2; exit 2 ;;
  esac
  "${PYTHON}" scripts/plot_enso_gadi_pmp.py \
    --metrics "${OUTPUT}/metrics" --output "${OUTPUT}/plots" "${reduced_arg}"
}

divedown_plot() {
  local args=(
    --metrics "${OUTPUT}/metrics"
    --output "${OUTPUT}/plots/divedown"
    --collections ${COLLECTIONS}
    --models ${MODELS}
  )
  if [[ -n "${DIVEDOWN_MEMBERS}" ]]; then
    args+=(--members ${DIVEDOWN_MEMBERS})
  fi
  if [[ -n "${DIVEDOWN_METRICS}" ]]; then
    args+=(--metric-names ${DIVEDOWN_METRICS})
  fi
  "${PYTHON}" scripts/plot_enso_gadi_divedowns.py "${args[@]}"
}

case "${MODE}" in
  setup) setup_env ;;
  check) check_python ;;
  inventory) inventory ;;
  compute) inventory; compute ;;
  plot) plot ;;
  pmp_plot) pmp_plot ;;
  divedown) divedown_plot ;;
  all) inventory; compute; pmp_plot; plot ;;
  *) echo "MODE 必须是 setup、check、inventory、compute、plot、pmp_plot、divedown 或 all" >&2; exit 2 ;;
esac

echo "完成时间: $(date -u)"
echo "输出目录: ${OUTPUT}"
