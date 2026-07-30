#!/usr/bin/env bash
# Review one paper with both stages on the Claude Agent SDK — the configuration
# that produced results/claude.csv (claude-sonnet-4-6, subscription auth via an
# empty ANTHROPIC_API_KEY, calibration RAG on).
#
# Usage: ./run_claude.sh /abs/path/to/paper.pdf
set -e
cd "$(dirname "$0")"

export ANTHROPIC_API_KEY=""
export HARSH_MODEL="claude_sdk:claude-sonnet-4-6"
export MERGER_MODEL="claude_sdk:claude-sonnet-4-6"
export REASONING_EFFORT="max"
export EXTRACTOR_MODEL="deepseek/deepseek-v4-flash"

python code/main.py --single_paper "$1"
