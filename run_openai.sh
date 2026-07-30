#!/usr/bin/env bash
# Review one paper with both stages on the OpenAI Agents SDK — the configuration
# that produced results/deepseek.csv (DeepSeek V4 Flash over OpenRouter with the
# provider pinned to deepseek, calibration RAG on).
#
# Usage: ./run_openai.sh /abs/path/to/paper.pdf
set -e
cd "$(dirname "$0")"

export HARSH_MODEL="deepseek-v4-flash"
export MERGER_MODEL="deepseek-v4-flash"
export REASONING_EFFORT="max"
export EXTRACTOR_MODEL="deepseek/deepseek-v4-flash"
export OPENROUTER_PROVIDER="deepseek"

python code/main.py --single_paper "$1"
