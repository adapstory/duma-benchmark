# scripts/

Minimal set of useful commands for working with results in `data/simulations`.

## Quickly rebuild paper (tables + plots + PDF)

```bash
./.venv/bin/python scripts/run_experiments_and_generate_tables.py \
  --skip-experiments \
  --models gpt-4o gpt-4o-mini \
  --temperatures 0.0 0.5 1.0 \
  --domains mail_rag_phishing collab output_handling \
  --num-trials 10 \
  --results-dir data/simulations
```

Output artifacts:
- `docs/paper_template/template.tex`, `docs/paper_template/template.pdf`
- tables: `docs/paper_template/model_domain_table.tex`, `docs/paper_template/significance_table.tex`, `docs/paper_template/temperature_significance_table.tex`, `docs/paper_template/detailed_metrics_table.tex`
- plots: `docs/paper_template/figs/*.pdf`

## Run / resume experiments (main pipeline)

```bash
./scripts/run_experiments.sh \
  --models gpt-4o gpt-4o-mini \
  --temperatures 0.0 0.5 1.0 \
  --domains mail_rag_phishing collab output_handling \
  --num-trials 10 \
  --max-concurrency 2 \
  --duma-max-concurrency 1
```

## Retry only missing results

If some files in `data/simulations` are incomplete/missing:

```bash
./.venv/bin/python scripts/retry_failed_experiments.py \
  --models gpt-4o gpt-4o-mini \
  --temperatures 0.0 0.5 1.0 \
  --num-trials 10 \
  --max-concurrency 1 \
  --duma-max-concurrency 3
```

## Maximum load (aggressive)

Auto-rollback on rate limit / timeout.

```bash
export OPENAI_API_KEY=...  # or OPENROUTER_API_KEY (if OpenRouter routing is configured)
./scripts/max_load_retry.sh
```

## Verify metrics correctness

```bash
./.venv/bin/python scripts/test_all_metrics.py
```

## Benchmark suite (for a full run)

```bash
./.venv/bin/python scripts/run_benchmark_suite.py --config scripts/benchmark_config_example.json
```

## Archive

Irrelevant/helper scripts and notebooks have been moved to `scripts/_archive/`.
