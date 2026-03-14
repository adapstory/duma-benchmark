#!/usr/bin/env python3
"""
Script to retry only failed experiments.

Usage:
    python scripts/retry_failed_experiments.py [--max-concurrency 3] [--force-rerun]
"""

import argparse
import json
import re
import shlex
import subprocess
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import timedelta
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )

    _RICH_AVAILABLE = True
except Exception:
    _RICH_AVAILABLE = False

# Add src to path for importing duma
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

try:
    from duma.utils.model_ref import normalize_model_ref
    from duma.utils.utils import DATA_DIR
except ImportError:
    print(
        "Error: Cannot import duma. Make sure you're in the project root and duma is installed."
    )
    sys.exit(1)


def _get_venv_python(project_root: Path) -> str:
    """Prefer repo .venv python to match installed deps."""
    candidate = project_root / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def parse_error_log(error_log_path: Path) -> List[dict]:
    """
    Parse error log and extract information about failed experiments.

    Returns:
        List of dicts with error info: {idx, name, command, error}
    """
    if not error_log_path.exists():
        print(f"⚠️  Error log not found: {error_log_path}")
        return []

    errors = []
    current_error = {}

    with open(error_log_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split into error blocks
    blocks = content.split("=" * 80)

    for block in blocks:
        if not block.strip():
            continue

        error_info = {}
        lines = block.strip().split("\n")

        for line in lines:
            if line.startswith("Experiment ["):
                # Extract idx and name
                match = re.search(r"Experiment \[(\d+)\]: (.+)", line)
                if match:
                    error_info["idx"] = int(match.group(1))
                    error_info["name"] = match.group(2)
            elif line.startswith("Command:"):
                error_info["command"] = line.replace("Command: ", "").strip()
            elif line.startswith("Duration:"):
                error_info["duration"] = line.replace("Duration: ", "").strip()
            elif line.startswith("Full error message:") or line.startswith("Error:"):
                # The rest is the error message
                error_start = block.find(line)
                error_info["error"] = block[error_start:].replace(line, "").strip()

        if error_info:
            errors.append(error_info)

    return errors


def _model_id_for_results(model: str) -> str:
    """Normalize model name for result filenames."""
    return normalize_model_ref(model)


def _sanitize_model_for_filename(model: str) -> str:
    # Keep filenames stable and portable by replacing separators and odd chars.
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", model).strip("-")


def find_missing_results(
    models: List[str],
    temperatures: List[float],
    domains: dict,
    num_trials: int,
    duma_max_concurrency: int,
    results_dir: Path,
    project_root: Path,
) -> List[Tuple[List[str], Path]]:
    """
    Find experiments with missing or incomplete result files.

    Returns:
        List of tuples (command, output_file)
    """
    missing = []

    def get_all_tasks_for_domain(domain_name: str) -> List[str]:
        """Load all tasks for a domain from tasks.json."""
        possible_paths = [
            DATA_DIR / "duma" / "domains" / domain_name / "tasks.json",
            DATA_DIR / "domains" / domain_name / "tasks.json",
            Path("data/duma/domains") / domain_name / "tasks.json",
        ]

        for path in possible_paths:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        tasks_data = json.load(f)
                        # tasks.json can be either a list or a dict with "tasks" key
                        if isinstance(tasks_data, list):
                            return [task["id"] for task in tasks_data if "id" in task]
                        elif isinstance(tasks_data, dict):
                            tasks_list = tasks_data.get("tasks", [])
                            return [task["id"] for task in tasks_list if "id" in task]
                        else:
                            print(
                                f"Unexpected format in {path}: expected list or dict"
                            )
                            return []
                except (json.JSONDecodeError, KeyError, IOError) as e:
                    print(f"Error reading {path}: {e}")
                    continue
        return []

    actual_output_dir = results_dir

    for domain, task_list in domains.items():
        tasks = task_list if task_list else get_all_tasks_for_domain(domain)

        if not tasks:
            print(f"No tasks found for domain {domain}")
            continue

        for model in models:
            for temp in temperatures:
                for task in tasks:
                    # Normalize model for filename to avoid duplicating result sets
                    # when switching providers (e.g. openrouter/openai/gpt-4o vs gpt-4o).
                    model_id = _model_id_for_results(model)
                    file_model = _sanitize_model_for_filename(model_id)

                    stable_file_name = (
                        f"paper_results_{domain}_{file_model}_T{temp}_{task}"
                    )
                    legacy_file_name = (
                        f"paper_results_{domain}_{_sanitize_model_for_filename(model)}_T{temp}_{task}"
                    )

                    stable_output_file = actual_output_dir / f"{stable_file_name}.json"
                    legacy_output_file = actual_output_dir / f"{legacy_file_name}.json"

                    # Prefer continuing an existing file (stable or legacy) to avoid
                    # creating a second parallel result file for the same config.
                    candidate_files = []
                    if stable_output_file.exists():
                        candidate_files.append(stable_output_file)
                    if legacy_output_file.exists() and legacy_output_file != stable_output_file:
                        candidate_files.append(legacy_output_file)
                    if not candidate_files:
                        candidate_files.append(stable_output_file)

                    def _inspect_result_file(path: Path) -> tuple[int, bool, bool]:
                        """(num_sims, task_id_ok, readable)"""
                        if not path.exists():
                            return (0, False, False)
                        try:
                            with open(path, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            simulations = data.get("simulations", [])
                            task_ids = set(
                                sim.get("task_id")
                                for sim in simulations
                                if sim and sim.get("task_id")
                            )
                            task_ok = (not task_ids) or (task in task_ids)
                            return (len(simulations), task_ok, True)
                        except (
                            json.JSONDecodeError,
                            KeyError,
                            IOError,
                            UnicodeDecodeError,
                        ):
                            return (0, False, False)

                    # Pick best candidate: complete > most sims; ignore wrong task_id.
                    best_output_file = None
                    best_sim_count = -1
                    best_readable = False
                    for cand in candidate_files:
                        sim_count, task_ok, readable = _inspect_result_file(cand)
                        if readable and not task_ok:
                            continue
                        if sim_count >= num_trials and readable:
                            best_output_file = cand
                            best_sim_count = sim_count
                            best_readable = True
                            break
                        if sim_count > best_sim_count:
                            best_output_file = cand
                            best_sim_count = sim_count
                            best_readable = readable

                    assert best_output_file is not None
                    output_file = best_output_file
                    file_name = output_file.stem

                    # Check if file is missing/incomplete
                    is_missing = True
                    existing_simulations = 0

                    if output_file.exists():
                        sim_count, task_ok, readable = _inspect_result_file(output_file)
                        existing_simulations = sim_count

                        if readable and sim_count >= num_trials and task_ok:
                            is_missing = False
                        elif not readable:
                            # Corrupted/unreadable - delete and rerun
                            try:
                                output_file.unlink()
                                print(f"Deleted corrupted file: {output_file.name}")
                            except Exception:
                                pass
                            is_missing = True
                        else:
                            # Incomplete but readable
                            is_missing = True

                    if is_missing:
                        if output_file.exists() and existing_simulations > 0:
                            print(
                                f"   ℹ️  File {output_file.name} has {existing_simulations}/{num_trials} simulations, will continue"
                            )

                        python_exe = _get_venv_python(project_root)
                        cmd = [
                            python_exe,
                            "-m",
                            "duma.cli",
                            "run",
                            "--domain",
                            domain,
                            "--agent-llm",
                            model,
                            "--user-llm",
                            model,
                            "--user-llm-args",
                            json.dumps({"temperature": temp}),
                            "--num-trials",
                            str(num_trials),
                            "--task-ids",
                            task,
                            "--save-to",
                            file_name,
                            "--max-concurrency",
                            str(duma_max_concurrency),
                        ]
                        missing.append((cmd, output_file))

    return missing


def run_single_experiment(
    cmd: List[str],
    output_file: Path,
    idx: int,
    total: int,
    process_timeout_seconds: int,
    max_retries: int = 3,
) -> Tuple[bool, float, Optional[str]]:
    """Run a single experiment with automatic retries on rate limit."""
    exp_start_time = time.time()
    start_time_str = time.strftime("%H:%M:%S", time.localtime(exp_start_time))

    project_root = Path(__file__).parent.parent

    domain = cmd[cmd.index("--domain") + 1] if "--domain" in cmd else "unknown"
    model = cmd[cmd.index("--agent-llm") + 1] if "--agent-llm" in cmd else "unknown"
    task = cmd[cmd.index("--task-ids") + 1] if "--task-ids" in cmd else "unknown"
    short_name = f"{domain[:15]}/{model[:10]}/{task.split('_')[-1][:20]}"

    print(f"[{idx}/{total}] Starting: {short_name} at {start_time_str}")

    for attempt in range(max_retries):
        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(project_root),
            )

            # duma may prompt for interactive resume confirmation if save_to already exists.
            # In non-interactive mode this looks like a hang. Automatically answer "y".
            resume_input = "y\n" * 5

            try:
                stdout, stderr = process.communicate(
                    input=resume_input, timeout=process_timeout_seconds
                )
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                exp_duration = time.time() - exp_start_time
                error_msg = (
                    f"Process timeout after {process_timeout_seconds} seconds. "
                    "The process may be stuck. Killing it."
                )
                print(
                    f"[{idx}/{total}] ⚠️  TIMEOUT after {process_timeout_seconds} seconds: {short_name}"
                )
                return (False, exp_duration, error_msg)

            returncode = process.returncode
            exp_duration = time.time() - exp_start_time

            # If successful, return result
            if returncode == 0:
                end_time_str = time.strftime("%H:%M:%S", time.localtime())
                duration_str = (
                    f"{int(exp_duration // 60)}m {int(exp_duration % 60)}s"
                    if exp_duration > 60
                    else f"{exp_duration:.1f}s"
                )
                print(
                    f"[{idx}/{total}] ✅ DONE after {duration_str} (finished at {end_time_str}): {short_name}"
                )
                return (True, exp_duration, None)

            # Check if error is a rate limit
            is_rate_limit = False
            if returncode != 0:
                error_text = (stderr + stdout).lower()
                is_rate_limit = any(
                    keyword in error_text
                    for keyword in [
                        "ratelimit",
                        "rate limit",
                        "rate_limit",
                        "please try again in",
                        "tpm",
                        "rpm",
                    ]
                )

                # If rate limit and retries remain, retry with delay
                if is_rate_limit and attempt < max_retries - 1:
                    # Extract wait time from error message
                    wait_time = 5.0  # Default 5 seconds
                    full_error_text = stderr + stdout
                    import re

                    wait_match = re.search(
                        r"try again in ([\d.]+)s", full_error_text, re.IGNORECASE
                    )
                    if wait_match:
                        wait_time = (
                            float(wait_match.group(1)) + 2.0
                        )  # Add 2 seconds buffer

                    print(
                        f"[{idx}/{total}] ⏳ Rate limit hit, retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})..."
                    )
                    time.sleep(wait_time)
                    continue  # Retry

            # If not rate limit or retries exhausted, handle as error
            if returncode != 0:
                # Collect full error message
                error_parts = []
                if stderr:
                    error_parts.append(f"STDERR:\n{stderr}")
                if stdout:
                    error_parts.append(f"STDOUT:\n{stdout}")
                if not error_parts:
                    error_parts.append("No error message")
                error_msg = "\n".join(error_parts)

                # Use a more informative snippet for output
                error_preview = (
                    stderr if stderr else stdout if stdout else "No error message"
                )
                # Look for last lines with ERROR, Exception, Traceback, or Failed
                error_lines = error_preview.split("\n")
                error_lines_filtered = [
                    l
                    for l in error_lines
                    if any(
                        keyword in l.upper()
                        for keyword in [
                            "ERROR",
                            "EXCEPTION",
                            "FAILED",
                            "TRACEBACK",
                            "CRITICAL",
                        ]
                    )
                ]
                if error_lines_filtered:
                    error_preview = "\n".join(
                        error_lines_filtered[-8:]
                    )  # Last 8 error lines
                else:
                    # If no explicit errors, take last lines of output
                    error_preview = (
                        "\n".join(error_lines[-10:])
                        if len(error_lines) > 10
                        else error_preview
                    )

                end_time_str = time.strftime("%H:%M:%S", time.localtime())
                duration_str = (
                    f"{int(exp_duration // 60)}m {int(exp_duration % 60)}s"
                    if exp_duration > 60
                    else f"{exp_duration:.1f}s"
                )
                print(
                    f"[{idx}/{total}] ❌ ERROR after {duration_str} (finished at {end_time_str}): {short_name}"
                )
                print(f"   Return code: {returncode}")
                if error_preview.strip():
                    print(f"   Error details:")
                    for line in error_preview.strip().split("\n")[
                        :10
                    ]:  # Max 10 lines
                        print(f"      {line}")
                return (False, exp_duration, error_msg)

        except Exception as e:
            exp_duration = time.time() - exp_start_time
            end_time_str = time.strftime("%H:%M:%S", time.localtime())
            duration_str = (
                f"{int(exp_duration // 60)}m {int(exp_duration % 60)}s"
                if exp_duration > 60
                else f"{exp_duration:.1f}s"
            )
            print(
                f"[{idx}/{total}] Exception after {duration_str} (finished at {end_time_str}): {short_name}"
            )
            print(f"   Exception: {str(e)[:200]}")
            # If this is the last attempt, return error
            if attempt == max_retries - 1:
                return (False, exp_duration, str(e))
            # Otherwise continue retrying
            time.sleep(2.0)
            continue

    # All retry attempts exhausted
    return (False, time.time() - exp_start_time, "All retry attempts exhausted")


def main():
    parser = argparse.ArgumentParser(
        description="Retry only failed experiments"
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=["gpt-4o", "gpt-4o-mini"],
        help="Models to run",
    )
    parser.add_argument(
        "--temperatures",
        nargs="+",
        type=float,
        default=[0.0, 0.5, 1.0],
        help="Temperatures to run",
    )
    parser.add_argument(
        "--domains",
        nargs="+",
        default=["mail_rag_phishing", "collab", "output_handling"],
        help="Domains to check",
    )
    parser.add_argument(
        "--num-trials", type=int, default=10, help="Number of runs per configuration"
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=1,
        help="Maximum number of parallel runs (1 recommended to avoid rate limits, 2-3 only with high API limits)",
    )
    parser.add_argument(
        "--duma-max-concurrency",
        type=int,
        default=1,
        help="Internal duma parallelism within a single experiment (parallel trials).",
    )
    parser.add_argument(
        "--process-timeout-seconds",
        type=int,
        default=3600,
        help="Timeout for a single duma run (seconds).",
    )
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="Force rerun all found failed experiments",
    )
    parser.add_argument(
        "--from-error-log",
        action="store_true",
        help="Use experiment_errors.log to determine failed experiments",
    )
    parser.add_argument(
        "--check-missing",
        action="store_true",
        default=True,
        help="Check for missing/incomplete result files (enabled by default)",
    )
    parser.add_argument(
        "--no-check-missing",
        dest="check_missing",
        action="store_false",
        help="Disable missing file check",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress bar (even if rich is installed)",
    )

    args = parser.parse_args()

    # Determine tasks for each domain (empty list = load all)
    tasks_by_domain = {domain: [] for domain in args.domains}

    commands = []

    # Method 1: From error log
    if args.from_error_log:
        error_log_path = project_root / "experiment_errors.log"
        errors = parse_error_log(error_log_path)

        if errors:
            print(f"Found {len(errors)} errors in log file")
            for error in errors:
                if "command" in error:
                    cmd_parts = shlex.split(error["command"])

                    # Find output_file from command
                    if "--save-to" in cmd_parts:
                        save_to_idx = cmd_parts.index("--save-to")
                        file_name = cmd_parts[save_to_idx + 1]
                        output_file = DATA_DIR / "simulations" / f"{file_name}.json"
                        commands.append((cmd_parts, output_file))

        else:
            print("No errors found in log file")

    # Method 2: Check for missing/incomplete files
    if args.check_missing:
        print("Checking for missing or incomplete result files...")
        missing = find_missing_results(
            args.models,
            args.temperatures,
            tasks_by_domain,
            args.num_trials,
            args.duma_max_concurrency,
            DATA_DIR / "simulations",
            project_root,
        )

        if missing:
            print(f"📋 Found {len(missing)} missing/incomplete experiments")
            commands.extend(missing)
        else:
            print("✅ All experiments have complete result files")

    if not commands:
        print("✅ No failed experiments to retry!")
        return

    # Remove duplicates:
    # - the same experiment may be found both in log and by missing-check
    # - provider changes may create different cmds for the same output_file
    seen_files = set()
    unique_commands = []
    for cmd, output_file in commands:
        key = str(output_file)
        if key in seen_files:
            continue
        seen_files.add(key)
        unique_commands.append((cmd, output_file))

    commands = unique_commands
    print(f"\nWill retry {len(commands)} experiments\n")

    # If force_rerun, delete existing files
    if args.force_rerun:
        for cmd, output_file in commands:
            if output_file.exists():
                output_file.unlink()
                print(f"🗑️  Deleted: {output_file.name}")

    # Run commands in parallel
    completed = 0
    errors = 0
    counters_lock = threading.Lock()  # Lock for thread-safe counter access
    start_time = time.time()

    # Clear error log at start
    error_log_file = project_root / "retry_errors.log"
    if error_log_file.exists():
        error_log_file.unlink()

    print(
        f"Starting {len(commands)} experiments with max_concurrency={args.max_concurrency}..."
    )
    print(
        f"   duma internal max_concurrency per experiment: {args.duma_max_concurrency}"
    )
    print(f"   Process timeout per experiment: {args.process_timeout_seconds}s")
    print(
        f"   Each experiment runs {args.num_trials} trials; speed depends on API limits."
    )

    use_progress = (
        _RICH_AVAILABLE
        and (not args.no_progress)
        and (sys.stdout.isatty() or sys.stderr.isatty())
    )

    progress = None
    progress_task_id = None
    progress_console = None

    if use_progress:
        from rich.console import Console as RichConsole
        from rich.progress import (
            BarColumn as RichBarColumn,
            Progress as RichProgress,
            SpinnerColumn as RichSpinnerColumn,
            TextColumn as RichTextColumn,
            TimeElapsedColumn as RichTimeElapsedColumn,
            TimeRemainingColumn as RichTimeRemainingColumn,
        )

        progress_console = RichConsole()
        progress = RichProgress(
            RichSpinnerColumn(),
            RichTextColumn("{task.description}"),
            RichBarColumn(),
            RichTextColumn("{task.completed}/{task.total}"),
            RichTimeElapsedColumn(),
            RichTimeRemainingColumn(),
            console=progress_console,
            transient=False,
        )
        progress_task_id = progress.add_task("Starting...", total=len(commands))
        progress.start()
    else:
        estimated_minutes = (len(commands) * 3) // max(args.max_concurrency, 1)
        print(
            f"   ℹ️  With {args.max_concurrency} parallel experiment(s), rough estimate ~{estimated_minutes} minutes total."
        )
        if args.max_concurrency > 2:
            print(
                f"   ⚠️  WARNING: High concurrency ({args.max_concurrency}) may cause rate limits!"
            )
        print("   Status updates every 30 seconds.\n")

    with ThreadPoolExecutor(max_workers=args.max_concurrency) as executor:
        # Track active experiments for periodic status output
        active_experiments = {}
        active_experiments_lock = threading.Lock()
        start_time_for_status = time.time()
        status_stop = threading.Event()
        futures = {}

        # Create experiment queue
        experiment_queue = [
            (idx, cmd, output_file)
            for idx, (cmd, output_file) in enumerate(commands, 1)
        ]

        # Submit first max_concurrency experiments immediately
        initial_batch = min(args.max_concurrency, len(experiment_queue))
        for _ in range(initial_batch):
            if experiment_queue:
                idx, cmd, output_file = experiment_queue.pop(0)
                future = executor.submit(
                    run_single_experiment,
                    cmd,
                    output_file,
                    idx,
                    len(commands),
                    args.process_timeout_seconds,
                )
                futures[future] = (idx, cmd, output_file)
                with active_experiments_lock:
                    active_experiments[future] = (idx, cmd, output_file)

        print(
            f"✅ Started first {initial_batch} experiment(s). Remaining {len(experiment_queue)} will start as slots become available.\n"
        )

        # Function for periodic status output in a separate thread
        def status_printer():
            time.sleep(5)  # Wait 5 seconds before first output
            with active_experiments_lock:
                active_count = len(active_experiments)
                queue_count = len(experiment_queue)
            if active_count > 0:
                print(
                    f"{active_count} experiment(s) running, {queue_count} waiting in queue...\n"
                )

            while not status_stop.is_set():
                time.sleep(30)  # Every 30 seconds
                if status_stop.is_set():
                    break

                with active_experiments_lock:
                    queue_count = len(experiment_queue)
                    if active_experiments or queue_count > 0:
                        current_time = time.time()
                        elapsed = current_time - start_time_for_status
                        active_count = len(active_experiments)
                        elapsed_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
                        with counters_lock:
                            completed_count = completed
                            errors_count = errors

                        # Estimate remaining time
                        if completed_count > 0:
                            avg_time_per_exp = elapsed / completed_count
                            remaining = (active_count + queue_count) * avg_time_per_exp
                            remaining_str = (
                                f"{int(remaining // 60)}m {int(remaining % 60)}s"
                            )
                            print(
                                f"\n[{elapsed_str}] Running: {active_count}, waiting: {queue_count}, completed: {completed_count}, errors: {errors_count}"
                            )
                            print(f"   Estimated time remaining: ~{remaining_str}")
                        else:
                            # If nothing completed yet, give a rough estimate
                            estimated_total = (
                                active_count + queue_count
                            ) * 3  # ~3 minutes per experiment
                            remaining_str = f"{int(estimated_total // 60)}m {int(estimated_total % 60)}s"
                            print(
                                f"\n[{elapsed_str}] Running: {active_count}, waiting: {queue_count}, completed: {completed_count}, errors: {errors_count}"
                            )
                            print(
                                f"   Estimated time remaining: ~{remaining_str} (first experiments may take longer)"
                            )
                        # Show first few active experiments
                        for i, (f, (idx, cmd, output_file)) in enumerate(
                            list(active_experiments.items())[:3]
                        ):
                            domain = (
                                cmd[cmd.index("--domain") + 1]
                                if "--domain" in cmd
                                else "unknown"
                            )
                            model = (
                                cmd[cmd.index("--agent-llm") + 1]
                                if "--agent-llm" in cmd
                                else "unknown"
                            )
                            task = (
                                cmd[cmd.index("--task-ids") + 1]
                                if "--task-ids" in cmd
                                else "unknown"
                            )
                            short_name = (
                                f"{domain[:15]}/{model[:10]}/{task.split('_')[-1][:20]}"
                            )
                            print(f"   [{idx}] {short_name}")
                        if active_count > 3:
                            print(f"   ... and {active_count - 3} more")
                        print()

        status_thread = None
        if not use_progress:
            # Start status output thread
            status_thread = threading.Thread(target=status_printer, daemon=True)
            status_thread.start()

        # IMPORTANT: as_completed() takes a snapshot of futures at call time.
        # We need to dynamically pick up added tasks from the queue.
        while futures:
            done_futures, _ = wait(list(futures.keys()), return_when=FIRST_COMPLETED)

            for future in done_futures:
                idx, cmd, output_file = futures.pop(future)

                # Remove completed experiment from active set
                with active_experiments_lock:
                    active_experiments.pop(future, None)

                try:
                    success, duration, error_msg = future.result()
                except Exception as e:
                    success, duration, error_msg = False, 0.0, str(e)

                with counters_lock:
                    if success:
                        completed += 1
                    else:
                        errors += 1

                if (
                    use_progress
                    and progress is not None
                    and progress_task_id is not None
                ):
                    with active_experiments_lock:
                        active_count = len(active_experiments)
                        queue_count = len(experiment_queue)
                    progress.update(
                        progress_task_id,
                        description=(
                            f"Running={active_count} Waiting={queue_count} "
                            f"Done={completed} Errors={errors}"
                        ),
                    )
                    progress.advance(progress_task_id, 1)

                # Log error to file
                if error_msg:
                    try:
                        cmd_str = " ".join(cmd)
                        with open(error_log_file, "a", encoding="utf-8") as f:
                            f.write(f"\n{'=' * 80}\n")
                            f.write(f"Failed experiment: {output_file.name}\n")
                            f.write(f"Command: {cmd_str}\n")
                            f.write(f"Duration: {duration:.1f}s\n")
                            f.write(f"Full error:\n{error_msg}\n")
                            f.write(f"{'=' * 80}\n")
                    except Exception as log_err:
                        print(f"   ⚠️  Failed to write to error log: {log_err}")

                # If there are experiments in the queue, start the next one
                if experiment_queue:
                    next_idx, next_cmd, next_output_file = experiment_queue.pop(0)
                    new_future = executor.submit(
                        run_single_experiment,
                        next_cmd,
                        next_output_file,
                        next_idx,
                        len(commands),
                        args.process_timeout_seconds,
                    )
                    futures[new_future] = (next_idx, next_cmd, next_output_file)
                    with active_experiments_lock:
                        active_experiments[new_future] = (
                            next_idx,
                            next_cmd,
                            next_output_file,
                        )

        # Stop status thread
        status_stop.set()
        if status_thread is not None:
            status_thread.join(timeout=1)

    if use_progress and progress is not None:
        progress.stop()

    total_time = time.time() - start_time
    total_time_str = str(timedelta(seconds=int(total_time)))
    end_time_str = time.strftime("%H:%M:%S", time.localtime())
    start_time_str = time.strftime("%H:%M:%S", time.localtime(start_time))

    print("\n" + "=" * 80)
    print("📊 Summary:")
    print(f"   ✅ Completed: {completed}")
    print(f"   ❌ Errors: {errors}")
    print(f"   ⏱️ Total time: {total_time_str}")
    print(f"   🕐 Started: {start_time_str}")
    print(f"   🕐 Finished: {end_time_str}")
    if completed > 0:
        avg_time = total_time / completed
        avg_time_str = (
            f"{int(avg_time // 60)}m {int(avg_time % 60)}s"
            if avg_time > 60
            else f"{avg_time:.1f}s"
        )
        print(f"   📈 Average time per experiment: {avg_time_str}")
    if errors > 0 and error_log_file.exists():
        print(
            f"\n⚠️  {errors} errors occurred. Full error details saved to: {error_log_file}"
        )
        print(f"   To view errors: cat {error_log_file.name}")
    print("=" * 80)


if __name__ == "__main__":
    main()
