#!/usr/bin/env bash
# Full Stage 1 run. Resumes if interrupted: rerun the same script.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p results/logs
log="results/logs/run-$(date +%Y%m%d-%H%M%S).log"
sudo -v || echo "no sudo: E6 energy will be skipped"
uv run dartbench run all --energy --label full "$@" 2>&1 | tee "$log"
echo "log: $log"
