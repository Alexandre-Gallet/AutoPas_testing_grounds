#!/bin/bash

#SBATCH -J autopas_runtime
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
# sbatch --export=ALL,SCENARIO=homogeneous50,VARIANT=cell-morton,RUNS=3 scripts/slurm/runtime_one_variant.slurm
APP="${APP:-./cmake-build-relwithdebinfo/examples/md-flexible/md-flexible}"
SCENARIO="${SCENARIO:-homogeneous40}"
VARIANT="${VARIANT:-no-sorting}"
RUNS="${RUNS:-3}"
BENCHMARK_ROOT="${BENCHMARK_ROOT:-benchmarks/CoolMuc/${SCENARIO}}"
YAML="${YAML:-${BENCHMARK_ROOT}/inputs/${VARIANT}.yaml}"
RUNTIME_DIR="${BENCHMARK_ROOT}/${VARIANT}/runtime"

export OMP_NUM_THREADS=1
export OMP_PROC_BIND=true
export OMP_PLACES=cores

mkdir -p benchmarks/logs
mkdir -p "${RUNTIME_DIR}"

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
module list

echo ""
echo "===== BENCHMARK CONFIG ====="
echo "APP=${APP}"
echo "SCENARIO=${SCENARIO}"
echo "VARIANT=${VARIANT}"
echo "RUNS=${RUNS}"
echo "BENCHMARK_ROOT=${BENCHMARK_ROOT}"
echo "YAML=${YAML}"

echo ""
echo "===== INPUT CHECK ====="
test -x "${APP}"
test -f "${YAML}"
ls -lh "${APP}"
sha256sum "${APP}"

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
  echo "runs=${RUNS}"
  echo "benchmark_root=${BENCHMARK_ROOT}"
  echo "yaml=${YAML}"
  echo "command=srun --exact -n 1 -c 1 --cpu-bind=cores ${APP} --yaml-filename ${YAML}"
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

echo "run_id,wall_clock_s,output_file" > "${RUNTIME_DIR}/runtimes.csv"

for run_id in $(seq 1 "${RUNS}")
do
  output_file="${RUNTIME_DIR}/run_${run_id}.out"

  echo ""
  echo "===== RUN ${run_id}/${RUNS} ====="
  srun --exact -n 1 -c 1 --cpu-bind=cores "${APP}" --yaml-filename "${YAML}" > "${output_file}"

  wall_clock_s="$(sed -n 's/.*Total wall-clock time[[:space:]]*:.*(\([0-9.][0-9.]*\)s).*/\1/p' "${output_file}" | tail -n 1)"

  if [[ -z "${wall_clock_s}" ]]; then
    echo "ERROR: Could not extract total wall-clock time from ${output_file}"
    exit 1
  fi

  echo "${run_id},${wall_clock_s},${output_file}" >> "${RUNTIME_DIR}/runtimes.csv"
  echo "Run ${run_id} wall-clock time: ${wall_clock_s} s"
done

echo ""
echo "===== RUNTIME MEASUREMENTS ====="
cat "${RUNTIME_DIR}/runtimes.csv"

echo ""
echo "===== DONE ====="
date
