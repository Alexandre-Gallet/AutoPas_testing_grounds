#!/bin/bash
#SBATCH -J autopas_variant
#SBATCH -D ./
#SBATCH -o ./benchmarks/logs/%x.%j.%N.out
#SBATCH --get-user-env
#SBATCH --export=NONE
#SBATCH --clusters=serial
#SBATCH --partition=serial_std
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=06:00:00

# Stop immediately if a command fails and print the failing command.
set -Eeuo pipefail
trap 'echo "ERROR at line ${LINENO}: ${BASH_COMMAND}"' ERR

# User-configurable parameters. Override them when calling sbatch, for example:
# sbatch --export=ALL,SCENARIO=homogeneous40,VARIANT=no-sorting,RUNS=10 scripts/slurm/benchmark_one_variant.slurm
APP="${APP:-./cmake-build-relwithdebinfo/examples/md-flexible/md-flexible}"
SCENARIO="${SCENARIO:-homogeneous40}"
VARIANT="${VARIANT:-no-sorting}"
RUNS="${RUNS:-10}"
BENCHMARK_ROOT="${BENCHMARK_ROOT:-benchmarks/CoolMuc/${SCENARIO}}"
RAW_RESULT_ROOT="${RAW_RESULT_ROOT:-${SCRATCH_DSS}/autopas_raw_results/${SCENARIO}}"
YAML="${YAML:-${BENCHMARK_ROOT}/inputs/${VARIANT}.yaml}"
VARIANT_DIR="${BENCHMARK_ROOT}/${VARIANT}"
RUNTIME_DIR="${VARIANT_DIR}/runtime"
HOTSPOTS_REPORT_DIR="${VARIANT_DIR}/vtune_hotspots"
MEMORY_REPORT_DIR="${VARIANT_DIR}/vtune_memory"
HOTSPOTS_RESULT_DIR="${RAW_RESULT_ROOT}/${VARIANT}/vtune_hotspots/result"
MEMORY_RESULT_DIR="${RAW_RESULT_ROOT}/${VARIANT}/vtune_memory/result"

export OMP_NUM_THREADS=1
export OMP_PROC_BIND=true
export OMP_PLACES=cores

mkdir -p "${RUNTIME_DIR}"
mkdir -p "${HOTSPOTS_REPORT_DIR}"
mkdir -p "${MEMORY_REPORT_DIR}"
mkdir -p "$(dirname "${HOTSPOTS_RESULT_DIR}")"
mkdir -p "$(dirname "${MEMORY_RESULT_DIR}")"

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
echo "RUNS=${RUNS}"
echo "BENCHMARK_ROOT=${BENCHMARK_ROOT}"
echo "RAW_RESULT_ROOT=${RAW_RESULT_ROOT}"
echo "YAML=${YAML}"
echo "VARIANT_DIR=${VARIANT_DIR}"
echo "HOTSPOTS_RESULT_DIR=${HOTSPOTS_RESULT_DIR}"
echo "MEMORY_RESULT_DIR=${MEMORY_RESULT_DIR}"

echo ""
echo "===== INPUT CHECK ====="
test -x "${APP}"
test -f "${YAML}"
ls -lh "${APP}"
sha256sum "${APP}"
which vtune
vtune --version

echo ""
echo "===== OUTPUT CHECK ====="
if [[ -e "${RUNTIME_DIR}/runtimes.csv" ]]; then
  echo "ERROR: Runtime measurements already exist: ${RUNTIME_DIR}/runtimes.csv"
  echo "Move or delete the existing runtime folder before rerunning this benchmark."
  exit 1
fi

if [[ -e "${HOTSPOTS_RESULT_DIR}" ]]; then
  echo "ERROR: VTune hotspots result already exists: ${HOTSPOTS_RESULT_DIR}"
  echo "Move or delete it before rerunning this benchmark."
  exit 1
fi

if [[ -e "${MEMORY_RESULT_DIR}" ]]; then
  echo "ERROR: VTune memory result already exists: ${MEMORY_RESULT_DIR}"
  echo "Move or delete it before rerunning this benchmark."
  exit 1
fi

if compgen -G "${HOTSPOTS_REPORT_DIR}/*.csv" > /dev/null; then
  echo "ERROR: VTune hotspots CSV reports already exist in ${HOTSPOTS_REPORT_DIR}"
  echo "Move or delete the existing report files before rerunning this benchmark."
  exit 1
fi

if compgen -G "${MEMORY_REPORT_DIR}/*.csv" > /dev/null; then
  echo "ERROR: VTune memory CSV reports already exist in ${MEMORY_REPORT_DIR}"
  echo "Move or delete the existing report files before rerunning this benchmark."
  exit 1
fi

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
  echo "raw_result_root=${RAW_RESULT_ROOT}"
  echo "yaml=${YAML}"
  echo "runtime_command=srun --exact -n 1 -c 1 --cpu-bind=cores ${APP} --yaml-filename ${YAML}"
  echo "hotspots_command=srun --exact -n 1 -c 1 --cpu-bind=cores vtune -collect hotspots -result-dir ${HOTSPOTS_RESULT_DIR} -- ${APP} --yaml-filename ${YAML}"
  echo "memory_command=srun --exact -n 1 -c 1 --cpu-bind=cores vtune -collect memory-access -result-dir ${MEMORY_RESULT_DIR} -- ${APP} --yaml-filename ${YAML}"
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
} > "${VARIANT_DIR}/metadata.txt"

echo ""
echo "===== RUNTIME BENCHMARK ====="
echo "run_id,wall_clock_s,output_file" > "${RUNTIME_DIR}/runtimes.csv"

for run_id in $(seq 1 "${RUNS}")
do
  output_file="${RUNTIME_DIR}/run_${run_id}.out"

  echo ""
  echo "===== RUNTIME RUN ${run_id}/${RUNS} ====="
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
echo "===== VTUNE HOTSPOTS COLLECTION ====="
srun --exact -n 1 -c 1 --cpu-bind=cores \
  vtune -collect hotspots \
  -result-dir "${HOTSPOTS_RESULT_DIR}" \
  -- \
  "${APP}" --yaml-filename "${YAML}"

echo ""
echo "===== VTUNE HOTSPOTS REPORTS ====="
vtune -report summary \
  -format=csv \
  -csv-delimiter=comma \
  -r "${HOTSPOTS_RESULT_DIR}" \
  > "${HOTSPOTS_REPORT_DIR}/summary.csv"

vtune -report hotspots \
  -group-by=function \
  -format=csv \
  -csv-delimiter=comma \
  -r "${HOTSPOTS_RESULT_DIR}" \
  > "${HOTSPOTS_REPORT_DIR}/functions.csv"

vtune -report hotspots \
  -group-by=source-line \
  -format=csv \
  -csv-delimiter=comma \
  -r "${HOTSPOTS_RESULT_DIR}" \
  > "${HOTSPOTS_REPORT_DIR}/source_lines.csv"

vtune -report hotspots \
  -report-knob viewpoint=bottom-up \
  -format=csv \
  -csv-delimiter=comma \
  -r "${HOTSPOTS_RESULT_DIR}" \
  > "${HOTSPOTS_REPORT_DIR}/bottom_up.csv"

vtune -report top-down \
  -format=csv \
  -csv-delimiter=comma \
  -r "${HOTSPOTS_RESULT_DIR}" \
  > "${HOTSPOTS_REPORT_DIR}/top_down.csv"

echo ""
echo "===== VTUNE MEMORY COLLECTION ====="
srun --exact -n 1 -c 1 --cpu-bind=cores \
  vtune -collect memory-access \
  -result-dir "${MEMORY_RESULT_DIR}" \
  -- \
  "${APP}" --yaml-filename "${YAML}"

echo ""
echo "===== VTUNE MEMORY REPORTS ====="
vtune -report summary \
  -format=csv \
  -csv-delimiter=comma \
  -r "${MEMORY_RESULT_DIR}" \
  > "${MEMORY_REPORT_DIR}/summary.csv"

vtune -report hotspots \
  -group-by=function \
  -format=csv \
  -csv-delimiter=comma \
  -r "${MEMORY_RESULT_DIR}" \
  > "${MEMORY_REPORT_DIR}/functions.csv"

vtune -report hw-events \
  -format=csv \
  -csv-delimiter=comma \
  -r "${MEMORY_RESULT_DIR}" \
  > "${MEMORY_REPORT_DIR}/hw_events.csv"

vtune -report top-down \
  -format=csv \
  -csv-delimiter=comma \
  -r "${MEMORY_RESULT_DIR}" \
  > "${MEMORY_REPORT_DIR}/top_down.csv"

echo ""
echo "===== OUTPUT FILES ====="
ls -lh "${RUNTIME_DIR}/runtimes.csv"
ls -lh "${HOTSPOTS_REPORT_DIR}/summary.csv"
ls -lh "${HOTSPOTS_REPORT_DIR}/functions.csv"
ls -lh "${HOTSPOTS_REPORT_DIR}/source_lines.csv"
ls -lh "${HOTSPOTS_REPORT_DIR}/bottom_up.csv"
ls -lh "${HOTSPOTS_REPORT_DIR}/top_down.csv"
ls -lh "${MEMORY_REPORT_DIR}/summary.csv"
ls -lh "${MEMORY_REPORT_DIR}/functions.csv"
ls -lh "${MEMORY_REPORT_DIR}/hw_events.csv"
ls -lh "${MEMORY_REPORT_DIR}/top_down.csv"

echo ""
echo "===== DONE ====="
date
