#!/bin/bash
# Downloads GGUF models in priority order. Tier 1 covers the headline experiments.
set -u
DEST="$HOME/llm-models"
dl() { uvx --from huggingface_hub hf download "$1" "$2" --local-dir "$DEST" >/dev/null 2>&1 && echo "OK $2" || echo "FAIL $2"; }
# tier 1
dl bartowski/Qwen2.5-7B-Instruct-GGUF  Qwen2.5-7B-Instruct-Q4_K_M.gguf
dl bartowski/Qwen2.5-0.5B-Instruct-GGUF Qwen2.5-0.5B-Instruct-Q8_0.gguf
dl bartowski/Qwen2.5-1.5B-Instruct-GGUF Qwen2.5-1.5B-Instruct-Q8_0.gguf
dl bartowski/Qwen2.5-3B-Instruct-GGUF  Qwen2.5-3B-Instruct-Q4_K_M.gguf
dl bartowski/Qwen2.5-7B-Instruct-GGUF  Qwen2.5-7B-Instruct-Q2_K.gguf
dl bartowski/Qwen2.5-7B-Instruct-GGUF  Qwen2.5-7B-Instruct-Q8_0.gguf
dl bartowski/Qwen2.5-14B-Instruct-GGUF Qwen2.5-14B-Instruct-Q4_K_M.gguf
echo "TIER1 DONE"
# tier 2
dl bartowski/Qwen2.5-7B-Instruct-GGUF  Qwen2.5-7B-Instruct-Q3_K_M.gguf
dl bartowski/Qwen2.5-7B-Instruct-GGUF  Qwen2.5-7B-Instruct-Q5_K_M.gguf
dl bartowski/Qwen2.5-14B-Instruct-GGUF Qwen2.5-14B-Instruct-Q5_K_M.gguf
echo "TIER2 DONE"
