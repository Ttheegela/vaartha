#!/bin/bash
#SBATCH --job-name=varta_gdelt_score
#SBATCH --partition=gpu
#SBATCH --constraint=ampere
#SBATCH --gres=gpu:4
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=/home/%u/varta_score_%j.out
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=tt633@rutgers.edu

# ── Environment ───────────────────────────────────────────────────────────────
source /projects/community/miniconda3/etc/profile.d/conda.sh
conda activate varta

echo "Job started: $(date)"
echo "Node: $(hostname)"
echo "GPUs allocated: $CUDA_VISIBLE_DEVICES"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

# ── Run scoring ───────────────────────────────────────────────────────────────
cd /home/tt633/varta

python scripts/amarel_score_gdelt.py \
    --input  data/processed/gdelt.parquet \
    --output data/processed/gdelt_scored.parquet \
    --model  google/gemma-4-26B-A4B-it \
    --batch  16

echo "Job finished: $(date)"
