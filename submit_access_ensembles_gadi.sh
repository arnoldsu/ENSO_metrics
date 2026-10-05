#!/usr/bin/env bash
set -euo pipefail

REPO=/g/data/p66/ars599/ENSO_metrics
OUTPUT=${ENSO_OUTPUT:-${REPO}/results_gadi_full}
MODELS=(ACCESS-CM2 ACCESS-ESM1-5)
# r1 results already exist in results_gadi_full; add r2-r5 here.
MEMBERS=(r2i1p1f1 r3i1p1f1 r4i1p1f1 r5i1p1f1)
COLLECTIONS=(ENSO_perf ENSO_proc ENSO_tel)
JOB_IDS=()

cd "${REPO}"
mkdir -p "${OUTPUT}/manifests"
: > "${OUTPUT}/manifests/submitted_access_ensembles.txt"

for model in "${MODELS[@]}"; do
  for member in "${MEMBERS[@]}"; do
    for collection in "${COLLECTIONS[@]}"; do
      short_collection=${collection#ENSO_}
      job_name="enso_${model//-/_}_${member%%i*}_${short_collection}"
      job_id=$(qsub \
        -N "${job_name}" \
        -v "MODE=compute,ENSO_MODELS=${model},ENSO_MEMBER=${member},ENSO_COLLECTIONS=${collection},ENSO_OUTPUT=${OUTPUT}" \
        run_enso_gadi.sh)
      job_id=${job_id%%.*}
      JOB_IDS+=("${job_id}")
      printf '%s %s %s %s\n' "${job_id}" "${model}" "${member}" "${collection}" \
        | tee -a "${OUTPUT}/manifests/submitted_access_ensembles.txt"
    done
  done
done

# Recompute TaiESM1 with the corrected local multi-file reader.
for collection in "${COLLECTIONS[@]}"; do
  short_collection=${collection#ENSO_}
  job_id=$(qsub \
    -N "enso_TaiESM1_fix_${short_collection}" \
    -v "MODE=compute,ENSO_MODELS=TaiESM1,ENSO_MEMBER=r1i1p1f1,ENSO_COLLECTIONS=${collection},ENSO_OUTPUT=${OUTPUT}" \
    run_enso_gadi.sh)
  job_id=${job_id%%.*}
  JOB_IDS+=("${job_id}")
  printf '%s %s %s %s\n' "${job_id}" TaiESM1 r1i1p1f1 "${collection}" \
    | tee -a "${OUTPUT}/manifests/submitted_access_ensembles.txt"
done

dependency=$(IFS=:; echo "${JOB_IDS[*]}")
plot_id=$(qsub \
  -N enso_access5_pmp_plot \
  -W "depend=afterany:${dependency}" \
  -v "MODE=pmp_plot,ENSO_OUTPUT=${OUTPUT}" \
  run_enso_gadi.sh)
plot_id=${plot_id%%.*}
printf '%s PMP_portrait_plot\n' "${plot_id}" | tee -a "${OUTPUT}/manifests/submitted_access_ensembles.txt"

echo "已提交 ${#JOB_IDS[@]} 个计算作业；绘图作业: ${plot_id}"
echo "最终图片: ${OUTPUT}/plots/ENSO_selected_models_PMP_portrait_plot.png"
