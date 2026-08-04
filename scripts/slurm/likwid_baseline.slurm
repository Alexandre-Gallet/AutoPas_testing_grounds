#!/bin/bash
#SBATCH -J likwid-baseline
#SBATCH -D ./
#SBATCH -o ./benchmarks/logs/%x.%j.%N.out
#SBATCH --get-user-env
#SBATCH --export=NONE
#SBATCH --clusters=serial
#SBATCH --partition=serial_std
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=01:00:00

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

REPORT_DIR="${BENCHMARK_ROOT}/${VARIANT}/likwid"
mkdir -p "${REPORT_DIR}"

echo "===== LIKWID CONFIG ====="
echo "APP=${APP}"
echo "YAML=${YAML}"
echo "LIKWID_GROUP=${LIKWID_GROUP}"

test -x "${APP}"
test -f "${YAML}"

srun --exact -n 1 -c 1 --cpu-bind=cores \
  likwid-perfctr \
  -C 0 \
  -g "${LIKWID_GROUP}" \
  "${APP}" \
  --yaml-filename "${YAML}" \
  > "${REPORT_DIR}/likwid-${LIKWID_GROUP}.txt"

echo "===== DONE ====="
ls -lh "${REPORT_DIR}/likwid-${LIKWID_GROUP}.txt"