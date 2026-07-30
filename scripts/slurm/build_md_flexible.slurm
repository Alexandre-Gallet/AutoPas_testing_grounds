#!/bin/bash

#SBATCH -J autopas_build
#SBATCH -D ./
#SBATCH -o ./benchmarks/logs/%x.%j.%N.out
#SBATCH --get-user-env
#SBATCH --export=NONE
#SBATCH --clusters=serial
#SBATCH --partition=serial_std
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=02:00:00

# Stop immediately if a command fails.
set -e

# Keep the job log readable.
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
module load cmake/3.30.0

module list

echo ""
echo "===== TOOL VERSIONS ====="
which cmake
cmake --version

which c++
c++ --version

echo ""
echo "===== CONFIGURE ====="
cmake -S . -B cmake-build-relwithdebinfo \
-DCMAKE_BUILD_TYPE=RelWithDebInfo \
-DMD_FLEXIBLE_FUNCTOR_AVX=ON

echo ""
echo "===== BUILD ====="
cmake --build cmake-build-relwithdebinfo \
--target md-flexible \
-j "${SLURM_CPUS_PER_TASK}"

echo ""
echo "===== BUILD OUTPUT CHECK ====="
test -x ./cmake-build-relwithdebinfo/examples/md-flexible/md-flexible
ls -lh ./cmake-build-relwithdebinfo/examples/md-flexible/md-flexible

echo ""
echo "===== DONE ====="
date
