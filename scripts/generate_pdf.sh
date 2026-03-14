#!/bin/bash
# Script to generate plots and compile PDF

set -e  # Stop on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "Generating plots and compiling PDF"
echo "=========================================="
echo ""

# Step 1: Process results and generate tables
echo "Step 1: Processing results and generating tables..."
python scripts/run_experiments_and_generate_tables.py \
    --skip-experiments \
    --compile-pdf

echo ""
echo "=========================================="
echo "Done! PDF compiled:"
echo "  docs/paper_template/template.pdf"
echo "=========================================="
