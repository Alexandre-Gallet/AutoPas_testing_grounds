#!/bin/bash

#SBATCH -J autopas_memory
#SBATCH -D ./
#SBATCH -o ./benchmarks/logs/%x.%j.%N.out
#SBATCH --get-user-env
#SBATCH --export=NONE
#SBATCH --clusters=serial
#SBATCH --partition=serial_std
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=02:00:00

# Stop immediately if a command fails and print the failing command.
set -Eeuo pipefail
trap 'echo "ERROR at line ${LINENO}: ${BASH_COMMAND}"' ERR

# User-configurable parameters. Override them when calling sbatch, for example:
# sbatch --export=ALL,SCENARIO=homogeneous40,VARIANT=no-sorting scripts/slurm/vtune_memory_one_variant.slurm
APP="${APP:-./cmake-build-relwithdebinfo/examples/md-flexible/md-flexible}"
SCENARIO="${SCENARIO:-homogeneous40}"
VARIANT="${VARIANT:-no-sorting}"
BENCHMARK_ROOT="${BENCHMARK_ROOT:-benchmarks/CoolMuc/${SCENARIO}}"
RAW_RESULT_ROOT="${RAW_RESULT_ROOT:-${SCRATCH_DSS}/autopas_raw_results/${SCENARIO}}"
YAML="${YAML:-${BENCHMARK_ROOT}/inputs/${VARIANT}.yaml}"
REPORT_DIR="${BENCHMARK_ROOT}/${VARIANT}/vtune_memory"
RESULT_DIR="${RAW_RESULT_ROOT}/${VARIANT}/vtune_memory/result"

export OMP_NUM_THREADS=1
export OMP_PROC_BIND=true
export OMP_PLACES=cores

mkdir -p "${REPORT_DIR}"
mkdir -p "$(dirname "${RESULT_DIR}")"

echo "===== JOB INFO ====="
echo "Job name:        ${SLURM_JOB_NAME}"
echo "Job ID:          ${SLURM_JOB_ID}"
echo "Node list:       ${SLURM_JOB_NODELIST}"
echo "Submit dir:      ${SLURM_SUBMIT_DIR}"
echo "Working dir:     $(pwd)"
echo "CPUs per task:   ${SLURM_CPUS_PER_TASK}"
date

echo ""
echo "===== MODULES ====="
module load slurm_setup
module load gcc/14.2.0
module load module-git
module load intel-oneapi-vtune/2024.2.1
module list

echo ""
echo "===== BENCHMARK CONFIG ====="
echo "APP=${APP}"
echo "SCENARIO=${SCENARIO}"
echo "VARIANT=${VARIANT}"
echo "BENCHMARK_ROOT=${BENCHMARK_ROOT}"
echo "RAW_RESULT_ROOT=${RAW_RESULT_ROOT}"
echo "YAML=${YAML}"
echo "REPORT_DIR=${REPORT_DIR}"
echo "RESULT_DIR=${RESULT_DIR}"

echo ""
echo "===== INPUT CHECK ====="
test -x "${APP}"
test -f "${YAML}"
ls -lh "${APP}"
sha256sum "${APP}"
which vtune
vtune --version

{
  echo "===== DATE ====="
  date
  echo ""
  echo "===== JOB ====="
  echo "job_name=${SLURM_JOB_NAME}"
  echo "job_id=${SLURM_JOB_ID}"
  echo "node_list=${SLURM_JOB_NODELIST}"
  echo "submit_dir=${SLURM_SUBMIT_DIR}"
  echo "working_dir=$(pwd)"
  echo "cpus_per_task=${SLURM_CPUS_PER_TASK}"
  echo ""
  echo "===== BENCHMARK ====="
  echo "scenario=${SCENARIO}"
  echo "variant=${VARIANT}"
  echo "benchmark_root=${BENCHMARK_ROOT}"
  echo "raw_result_root=${RAW_RESULT_ROOT}"
  echo "yaml=${YAML}"
  echo "command=srun --exact -n 1 -c 1 --cpu-bind=cores vtune -collect memory-access -result-dir ${RESULT_DIR} -- ${APP} --yaml-filename ${YAML}"
  echo ""
  echo "===== OPENMP ====="
  echo "OMP_NUM_THREADS=${OMP_NUM_THREADS}"
  echo "OMP_PROC_BIND=${OMP_PROC_BIND}"
  echo "OMP_PLACES=${OMP_PLACES}"
  echo ""
  echo "===== MODULES ====="
  module list 2>&1
  echo ""
  echo "===== CPU INFO ====="
  lscpu
  echo ""
  echo "===== EXECUTABLE ====="
  ls -lh "${APP}"
  sha256sum "${APP}"
  echo ""
  echo "===== TOOLS ====="
  which vtune
  vtune --version
  echo ""
  echo "===== GIT ====="
  if command -v git >/dev/null 2>&1; then
    git rev-parse HEAD
    git describe --tags --always --dirty
    git status --short --branch
  else
    echo "git command not available in this SLURM job environment"
  fi
  echo ""
  echo "===== YAML CONTENT ====="
  cat "${YAML}"
} > "${BENCHMARK_ROOT}/${VARIANT}/metadata.txt"

if [[ -e "${RESULT_DIR}" ]]; then
  echo "ERROR: VTune memory result already exists: ${RESULT_DIR}"
  echo "Move or delete it before rerunning this job."
  exit 1
fi

echo ""
echo "===== VTUNE MEMORY COLLECTION ====="
srun --exact -n 1 -c 1 --cpu-bind=cores \
  vtune -collect memory-access \
  -result-dir "${RESULT_DIR}" \
  -- \
  "${APP}" --yaml-filename "${YAML}"

echo ""
echo "===== VTUNE MEMORY REPORTS ====="
vtune -report summary \
  -format=csv \
  -csv-delimiter=comma \
  -r "${RESULT_DIR}" \
  > "${REPORT_DIR}/summary.csv"

vtune -report hotspots \
  -group-by=function \
  -format=csv \
  -csv-delimiter=comma \
  -r "${RESULT_DIR}" \
  > "${REPORT_DIR}/functions.csv"

vtune -report hw-events \
  -format=csv \
  -csv-delimiter=comma \
  -r "${RESULT_DIR}" \
  > "${REPORT_DIR}/hw_events.csv"

vtune -report top-down \
  -format=csv \
  -csv-delimiter=comma \
  -r "${RESULT_DIR}" \
  > "${REPORT_DIR}/top_down.csv"

echo ""
echo "===== REPORT OUTPUT CHECK ====="
ls -lh "${REPORT_DIR}/summary.csv"
ls -lh "${REPORT_DIR}/functions.csv"
ls -lh "${REPORT_DIR}/hw_events.csv"
ls -lh "${REPORT_DIR}/top_down.csv"

echo ""
echo "===== DONE ====="
date
