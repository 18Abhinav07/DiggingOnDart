#!/usr/bin/env bash
# Reproduce the headline result on your own Mac: prefilling a 4k-token prompt with a local 7B model makes a
# GPU-heavy page drop most of its frames, decode doesn't, and a 64-token batch removes the drops for ~10% TTFT.
#
#   ./reproduce.sh            core experiment: 7B at batch 512 vs 64, our shader page + WebGL Aquarium (~15 min)
#   ./reproduce.sh --safari   also run the shader page in Safari, and CPU-only inference against a CPU-bound page (+35 min)
#   ./reproduce.sh --demo     the whole pipeline on simulated data, no model or GPU needed (~2 min)
#
# Needs: Apple Silicon, macOS, Brave Browser, Homebrew, ~5 GB disk for the model, the Mac on AC power.
# Don't touch the Mac while it runs: frame timing needs the browser window in front and the machine otherwise idle.
set -euo pipefail
cd "$(dirname "$0")/bench"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1; }

mode=core
case "${1:-}" in
  --demo) mode=demo ;;
  --safari) mode=safari ;;
  "") ;;
  *) echo "usage: $0 [--demo|--safari]"; exit 2 ;;
esac

if ! need uv; then
  echo "uv is required: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1
fi

if [ "$mode" = demo ]; then
  export DARTBENCH_FAKE=1
  say "Demo: simulated llama-server and frame stream (results/fake.db)"
  uv run dartbench run e4 core --quick --yes
  uv run dartbench export --out reports/dashboard-fake.html
  open reports/dashboard-fake.html
  exit 0
fi

[ "$(uname -m)" = arm64 ] || { echo "Apple Silicon only (the effect is Metal GPU contention)."; exit 1; }
[ -d "/Applications/Brave Browser.app" ] || { echo "Install Brave: https://brave.com/download/ (the harness drives its own profile, not yours)"; exit 1; }
if ! need llama-server; then
  read -r -p "llama.cpp not found. Install it with Homebrew now? [y/N] " a
  [ "$a" = y ] || [ "$a" = Y ] || exit 1
  brew install llama.cpp
fi

MODELS="${DARTBENCH_MODELS:-$HOME/llm-models}"
MODEL="Qwen2.5-7B-Instruct-Q4_K_M.gguf"
if [ ! -f "$MODELS/$MODEL" ]; then
  say "Downloading $MODEL (4.7 GB) to $MODELS"
  uvx --from huggingface_hub hf download bartowski/Qwen2.5-7B-Instruct-GGUF "$MODEL" --local-dir "$MODELS"
fi

say "Preflight"
uv run dartbench check --allow-missing || { echo "Fix the FAIL lines above and rerun."; exit 1; }

# a fresh database, so this run never resumes into (or mixes with) the published M4 Pro data
export DARTBENCH_DB="$PWD/results/mine.db"
exps=(core)
[ "$mode" = safari ] && exps+=(e4y)
say "Running ${exps[*]}. Hands off the Mac until it finishes."
uv run dartbench run "${exps[@]}" --allow-missing
uv run dartbench export --out reports/dashboard-mine.html

say "Done"
echo "  report:    bench/reports/report-mine.md"
echo "  dashboard: bench/reports/dashboard-mine.html (opening it now)"
echo "  compare with the published M4 Pro run: docs/dashboard.html"
open reports/dashboard-mine.html
