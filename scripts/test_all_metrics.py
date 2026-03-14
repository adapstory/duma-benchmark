#!/usr/bin/env python3
"""
Script to verify all metrics on existing results.
"""

import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

from result_collection import (
    load_simulations,
    compute_task_metrics,
    t_confidence_interval,
    wilson_confidence_interval,
    compare_continuous_metrics,
    compare_conversion_metrics,
)
from duma.utils.utils import DATA_DIR


def test_all_metrics():
    """Verify computation of all metrics."""
    print("=" * 80)
    print("CHECKING ALL METRICS")
    print("=" * 80)

    # Find all result files
    results_dir = DATA_DIR / "simulations"
    result_files = list(results_dir.glob("paper_results_*.json"))

    if not result_files:
        print(f"No result files found in {results_dir}")
        print("   Run experiments first or specify a different directory")
        return False

    print(f"Found {len(result_files)} result files")

    # Load results
    print("\nLoading results...")
    all_domains = load_simulations(result_files)

    if not all_domains:
        print("Failed to load results")
        return False

    print(f"Loaded {len(all_domains)} domains")

    # Check metrics for each domain and task
    all_metrics_found = set()
    metrics_errors = []

    required_metrics = {
        'pass^1', 'ASR', 'avg_reward', 'avg_agent_cost', 'avg_user_cost',
        'avg_duration', 'avg_num_messages',
        'pass^1_ci_lower', 'pass^1_ci_upper',
        'avg_reward_ci_lower', 'avg_reward_ci_upper',
        'avg_duration_ci_lower', 'avg_duration_ci_upper',
        'avg_num_messages_ci_lower', 'avg_num_messages_ci_upper'
    }

    print("\nChecking metrics...")
    for domain, results in all_domains.items():
        task_ids = set(sim.task_id for sim in results.simulations)

        for task_id in task_ids:
            metrics = compute_task_metrics(results, task_id)

            if not metrics:
                metrics_errors.append(f"{domain}/{task_id}: no metrics")
                continue

            # Check that all required metrics are present
            missing = required_metrics - set(metrics.keys())
            if missing:
                metrics_errors.append(f"{domain}/{task_id}: missing metrics {missing}")

            # Verify value correctness
            if 'pass^1' in metrics and 'ASR' in metrics:
                expected_asr = 1.0 - metrics['pass^1']
                actual_asr = metrics['ASR']
                if abs(expected_asr - actual_asr) > 0.0001:
                    metrics_errors.append(
                        f"{domain}/{task_id}: ASR mismatch (expected {expected_asr:.4f}, got {actual_asr:.4f})"
                    )

            # Check confidence intervals
            if 'pass^1_ci_lower' in metrics and 'pass^1_ci_upper' in metrics:
                ci_lower = metrics['pass^1_ci_lower']
                ci_upper = metrics['pass^1_ci_upper']
                if ci_lower > ci_upper:
                    metrics_errors.append(f"{domain}/{task_id}: invalid CI for pass@1")
                if ci_lower < 0 or ci_upper > 1:
                    metrics_errors.append(f"{domain}/{task_id}: CI for pass@1 out of range [0,1]")

            # Check continuous metrics
            for metric_name in ['avg_reward', 'avg_duration', 'avg_num_messages']:
                if metric_name in metrics:
                    ci_lower_key = f"{metric_name}_ci_lower"
                    ci_upper_key = f"{metric_name}_ci_upper"
                    if ci_lower_key in metrics and ci_upper_key in metrics:
                        ci_lower = metrics[ci_lower_key]
                        ci_upper = metrics[ci_upper_key]
                        if ci_lower > ci_upper:
                            metrics_errors.append(f"{domain}/{task_id}: invalid CI for {metric_name}")

            all_metrics_found.update(metrics.keys())

    # Print results
    print(f"\nFound {len(all_metrics_found)} distinct metrics")
    print(f"   Metrics: {', '.join(sorted(all_metrics_found))}")

    if metrics_errors:
        print(f"\nFound {len(metrics_errors)} errors:")
        for error in metrics_errors[:10]:  # Show first 10
            print(f"   - {error}")
        if len(metrics_errors) > 10:
            print(f"   ... and {len(metrics_errors) - 10} more errors")
        return False
    else:
        print("\nAll metrics computed correctly!")
        return True


def test_statistical_functions():
    """Verify statistical functions."""
    print("\n" + "=" * 80)
    print("CHECKING STATISTICAL FUNCTIONS")
    print("=" * 80)

    errors = []

    # Test Wilson CI
    try:
        ci_lower, ci_upper = wilson_confidence_interval(5, 10)
        if not (0 <= ci_lower <= ci_upper <= 1):
            errors.append("Wilson CI: invalid range")
        print("Wilson CI works correctly")
    except Exception as e:
        errors.append(f"Wilson CI: {e}")

    # Test t-interval
    try:
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        ci_lower, ci_upper = t_confidence_interval(values)
        if ci_lower > ci_upper:
            errors.append("t-interval: invalid range")
        print("t-interval works correctly")
    except Exception as e:
        errors.append(f"t-interval: {e}")

    # Test continuous metrics comparison
    try:
        group1 = [1.0, 2.0, 3.0]
        group2 = [4.0, 5.0, 6.0]
        p_value, sig = compare_continuous_metrics(group1, group2)
        if not (0 <= p_value <= 1):
            errors.append("compare_continuous_metrics: invalid p-value")
        print("compare_continuous_metrics works correctly")
    except Exception as e:
        errors.append(f"compare_continuous_metrics: {e}")

    # Test discrete metrics comparison
    try:
        p_value, sig = compare_conversion_metrics(5, 10, 3, 10)
        if not (0 <= p_value <= 1):
            errors.append("compare_conversion_metrics: invalid p-value")
        print("compare_conversion_metrics works correctly")
    except Exception as e:
        errors.append(f"compare_conversion_metrics: {e}")

    if errors:
        print(f"\nFound {len(errors)} errors in statistical functions:")
        for error in errors:
            print(f"   - {error}")
        return False
    else:
        print("\nAll statistical functions work correctly!")
        return True


if __name__ == "__main__":
    print("Running full metrics verification\n")

    # Verify statistical functions
    stats_ok = test_statistical_functions()

    # Verify metrics on data
    metrics_ok = test_all_metrics()

    # Final result
    print("\n" + "=" * 80)
    if stats_ok and metrics_ok:
        print("ALL CHECKS PASSED SUCCESSFULLY!")
        sys.exit(0)
    else:
        print("SOME CHECKS FAILED")
        sys.exit(1)
