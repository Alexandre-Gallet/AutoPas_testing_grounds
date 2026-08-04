#!/bin/bash
#SBATCH -J likwid-test
#SBATCH -D ./
#SBATCH -o ./benchmarks/logs/%x.%j.%N.out
#SBATCH --get-user-env
#SBATCH --export=NONE
#SBATCH --clusters=serial
#SBATCH --partition=serial_std
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:30:00

set -Eeuo pipefail
trap 'echo "ERROR at line ${LINENO}: ${BASH_COMMAND}"' ERR

module load slurm_setup
module load gcc/14.2.0
module load likwid/5.3.0-gcc13-perf

export OMP_NUM_THREADS=1
export OMP_PROC_BIND=true
export OMP_PLACES=cores

APP="${APP:-./cmake-build-relwithdebinfo/examples/md-flexible/md-flexible}"
SCENARIO="${SCENARIO:-homogeneous70-aos-with-neighbour-list-sorting}"
VARIANT="${VARIANT:-no-sorting}"
BENCHMARK_ROOT="${BENCHMARK_ROOT:-benchmarks/CoolMuc/${SCENARIO}}"
YAML="${YAML:-${BENCHMARK_ROOT}/inputs/${VARIANT}.yaml}"
LIKWID_GROUP="${LIKWID_GROUP:-MEM}"
LIKWID_CORE="${LIKWID_CORE:-0}"

REPORT_DIR="${BENCHMARK_ROOT}/${VARIANT}/likwid_test"
mkdir -p "${REPORT_DIR}"

echo "===== JOB INFO ====="
echo "Job name:        ${SLURM_JOB_NAME:-}"
echo "Job ID:          ${SLURM_JOB_ID:-}"
echo "Node list:       ${SLURM_JOB_NODELIST:-}"
echo "Working dir:     $(pwd)"
echo "CPUs per task:   ${SLURM_CPUS_PER_TASK:-}"
date

echo ""
echo "===== MODULES ====="
module list

echo ""
echo "===== INPUT CHECK ====="
test -x "${APP}"
test -f "${YAML}"
ls -lh "${APP}"
sha256sum "${APP}"
echo "YAML=${YAML}"
echo "LIKWID_GROUP=${LIKWID_GROUP}"
echo "LIKWID_CORE=${LIKWID_CORE}"

echo ""
echo "===== LIKWID VERSION ====="
which likwid-perfctr
likwid-perfctr -v

echo ""
echo "===== SLURM CPU INFO ====="
echo "SLURM_CPU_BIND=${SLURM_CPU_BIND:-}"
echo "SLURM_CPU_BIND_LIST=${SLURM_CPU_BIND_LIST:-}"
taskset -pc $$ || true

echo ""
echo "===== LIKWID TOPOLOGY ====="
likwid-topology > "${REPORT_DIR}/likwid-topology.txt"
sed -n '1,80p' "${REPORT_DIR}/likwid-topology.txt"

echo ""
echo "===== AVAILABLE LIKWID GROUPS ====="
likwid-perfctr -a > "${REPORT_DIR}/likwid-groups.txt"
sed -n '1,120p' "${REPORT_DIR}/likwid-groups.txt"

echo ""
echo "===== RUN LIKWID ====="
srun --exact -n 1 -c 1 --cpu-bind=cores \
  likwid-perfctr \
  -C "${LIKWID_CORE}" \
  -g "${LIKWID_GROUP}" \
  "${APP}" \
  --yaml-filename "${YAML}" \
  > "${REPORT_DIR}/likwid-${LIKWID_GROUP}.txt"

echo ""
echo "===== OUTPUT CHECK ====="
ls -lh "${REPORT_DIR}/likwid-${LIKWID_GROUP}.txt"

echo ""
echo "===== DONE ====="
date