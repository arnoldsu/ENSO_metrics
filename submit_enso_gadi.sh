#!/usr/bin/env bash
set -euo pipefail

REPO=/g/data/p66/ars599/ENSO_metrics
OUTPUT=${ENSO_OUTPUT:-${REPO}/results_gadi_full}
MODELS=(ACCESS-CM2 ACCESS-ESM1-5 TaiESM1 CESM2)
COLLECTIONS=(ENSO_perf ENSO_proc ENSO_tel)
JOB_IDS=()

cd "${REPO}"
mkdir -p "${OUTPUT}"/manifests

echo "输出目录: ${OUTPUT}"
echo "提交 4 模式 × 3 collections = 12 个计算作业"

for model in "${MODELS[@]}"; do
  for collection in "${COLLECTIONS[@]}"; do
    short_collection=${collection#ENSO_}
    job_name="enso_${model//-/_}_${short_collection}"
    job_id=$(qsub \
      -N "${job_name}" \
      -v "MODE=compute,ENSO_MODELS=${model},ENSO_COLLECTIONS=${collection},ENSO_OUTPUT=${OUTPUT}" \
      run_enso_gadi.sh)
    job_id=${job_id%%.*}
    JOB_IDS+=("${job_id}")
    printf '%s %s %s\n' "${job_id}" "${model}" "${collection}" | tee -a "${OUTPUT}/manifests/submitted_jobs.txt"
  done
done

dependency=$(IFS=:; echo "${JOB_IDS[*]}")
plot_id=$(qsub \
  -N enso_pmp_plot \
  -W "depend=afterany:${dependency}" \
  -v "MODE=pmp_plot,ENSO_OUTPUT=${OUTPUT}" \
  run_enso_gadi.sh)
plot_id=${plot_id%%.*}

printf '%s %s\n' "${plot_id}" "PMP portrait plot" | tee -a "${OUTPUT}/manifests/submitted_jobs.txt"

echo
echo "全部作业已提交。"
echo "计算作业: ${JOB_IDS[*]}"
echo "绘图作业: ${plot_id}（等待全部计算作业结束）"
echo "查看状态: qstat -u ${USER}"
echo "最终图片: ${OUTPUT}/plots/ENSO_selected_models_PMP_portrait_plot.png"
