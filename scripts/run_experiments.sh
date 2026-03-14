#!/bin/bash
# Script to run experiments with venv activation

cd "$(dirname "$0")/.."

# Activate venv if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run the script with passed arguments
python3 scripts/run_experiments_and_generate_tables.py "$@"
