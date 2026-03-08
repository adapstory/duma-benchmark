# DUMA-Bench: Dual-Control Multi Agent systems vulnerabilities benchmark

[![python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)


<div align="center">
<img src="figs/attaks.jpg" width="95%" alt="System Overview"><br>
<em>Figure 1: Duma-bench allows users to interact with the agent and the environment</em>
</div>

<div align="center">
<img src="figs/diagram.jpg" width="95%" alt="Trajectory"><br>
<em>Figure 2: Trajectory of a conversation between an agent and a user</em>
</div>

## 🆕 What's New
- Added three new security domains:
  - `mktg_phishing` (campaign phishing pressure / external domain approval gates)
  - `auth_spoof_support` (identity spoofing and privileged-action auth bypass)
  - `tool_shadow_poison` (tool shadowing / unsigned export tool misuse)
- Added full task sets, policies, and deterministic ENV assertions for all three domains.
- Added domain tests under `tests/test_domains/` for tool behavior and environment wiring.

## Overview

DUMA-bench implements a simulation framework for evaluating customer service agents across various domains.

Each domain specifies:
- a policy that the agent must follow
- a set of tools that the agent can use
- a set of tasks to evaluate the agent's performance
- Optionally: A set of tools that the user simulator can use

Domains are:
- `collab` (cross-agent poisoning)
- `crm_leak` (customer data leakage)
- `mail_rag_phishing` (phishing via RAG)
- `infra_loadshed` (resource overload / denial-of-wallet)
- `output_handling` (improper output filtering)
- `mktg_phishing` (marketing phishing pressure and unapproved-domain blocking)
- `auth_spoof_support` (support-side identity spoofing and auth bypass resistance)
- `tool_shadow_poison` (tool-shadow poisoning and signed-tool enforcement)

All the information that an agent developer needs to build an agent for a domain can be accessed through the domain's API docs. See [View domain documentation](#view-domain-documentation) for more details.

## Authors ([ai-securitylab ITMO](https://github.com/ai-security-lab-itmo))
* [Aleksandrov Ivan](https://github.com/Ivanich-spb)
* [Kochnev German](https://github.com/germanKoch)
* [Rogoza Yaroslav](https://github.com/123yaroslav)
* [Kalimanova Anastasia](https://github.com/katimanova)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/ai-security-lab-itmo/duma-benchmark.git
cd duma-benchmark
```

2. Create a new environment (optional)

DUMA-benchmark requires Python 3.10 or higher. You may create and activate a new environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

3. Install DUMA

```bash
pip install -e .
```

This will enable you to run the `duma` command.

**Note:** If you use `pip install .` (without `-e`), you'll need to set the `DUMA_DATA_DIR` environment variable to point to your data directory:

```bash
export DUMA_DATA_DIR=/path/to/your/duma-bench/data
```

**Check your data directory setup:**

After installation, you can verify that your data directory is correctly configured by running:

```bash
duma check-data
```

This command will check if the data directory exists and print instructions if it is missing.

To remove all the generated files and the virtual environment, run:
```bash
make clean
```

## Quick Start

### Setup LLM API keys

We use [LiteLLM](https://github.com/BerriAI/litellm) to manage LLM APIs, so you can use any LLM provider supported by LiteLLM.

To provide your API keys, copy `.env.example` as `.env` and edit it to include your API keys.

### Run agent evaluation

To run a test evaluation on only 5 tasks with 1 trial per task, run:

```bash
duma run \ 
--domain collab \
--agent-llm gpt-4.1 \
--user-llm gpt-4.1 \
--num-trials 1 \
--num-tasks 5
```

Results will be saved in `data/duma/simulations/`.

## Command Line Interface

The `duma` command provides a unified interface for all functionality:

### Running Benchmark 
```bash
duma run \
  --domain <domain> \
  --agent-llm <llm_name> \
  --user-llm <llm_name> \
  --num-trials <trial_count> \
  --task-ids <task_ids> \
  --max-concurrency <concurrent_sims> \
  ...
```

### Agent Modes

The benchmark supports three built-in agent modes:

- `llm_agent` (default): regular interactive mode with simulated user (`user_simulator`).
- `llm_agent_gt`: ground-truth helper mode for debugging/validation. The agent receives expected task actions in its system prompt. Use this as a diagnostic baseline, not as a fair production benchmark.
- `llm_agent_solo`: no-user mode. The agent works directly with tools and finishes by calling `done`; this mode must be paired with `--user dummy_user`.

Examples:

```bash
# Default interactive benchmark mode
duma run \
  --domain collab \
  --agent llm_agent \
  --user user_simulator \
  --agent-llm gpt-4.1 \
  --user-llm gpt-4.1
```

```bash
# Ground-truth diagnostic mode
duma run \
  --domain collab \
  --agent llm_agent_gt \
  --user user_simulator \
  --agent-llm gpt-4.1 \
  --user-llm gpt-4.1
```

```bash
# No-user (solo) mode
duma run \
  --domain collab \
  --agent llm_agent_solo \
  --user dummy_user \
  --agent-llm gpt-4.1
```

### Viewing Results
```bash
duma view
```
This tool allows you to:
- Browse simulation files (in `data/duma/simulations/`)
- View agent performance metrics
- View a particular simulation
- View task details

### View domain documentation
```bash
duma domain <domain>
```
Visit http://127.0.0.1:8004/redoc to see the domain policy and API documentation.

### Run multiple domains with custom endpoints
```bash
duma run \
  --domains collab infra_loadshed output_handling \
  --agent-llm gpt-4o-mini \
  --user-llm gpt-4o-mini \
  --api-key-env ALTERNATIVE_API_KEY \
  --agent-base-url https://api.openai.com/v1 \
  --max-concurrency 2
```
Use `--local-models` to skip API keys for local providers, and `--user-base-url`/`--agent-base-url` to point to custom endpoints.

![domain_viewer1](figs/domain_viewer.png)

### Check data configuration
```bash
duma check-data
```
This command checks if your data directory is properly configured and all required files are present.

## Experiments

### Experimental Code Directory

The `@experiments/` directory contains experimental features and research code that extends beyond the core duma benchmark. This directory is designed for community contributions of innovative approaches, prototypes, and new features that are not part of the core evaluation framework.

- **Purpose**: Research code and experimental features
- **Location**: `src/experiments/`
- **Usage**: Each experimental component has its own README with documentation
- **Status**: Experimental code is provided as-is and may not be fully tested or supported

For more details, see the [experiments README](src/experiments/README.md).

## Domains

For all the details see the domains [README](src/duma/domains/README.md).
Additional attack-focused summaries and runnable examples are in [docs/new_domains.md](docs/new_domains.md).

## Results


**Hypothesis 1**: With fixed agent and user temperatures, increasing the number of runs *k* reduces the variance of the pass@k metric, but does not guarantee monotonic change in ASR.

**Hypothesis 2**: Changes in non-attacking user requests cause changes in ASR with fixed agent temperature.

<p align="center">
  <img src="figs/res_t0_pass1.svg" width="45%"/>
  <img src="figs/res_t05_pass1.svg" width="45%"/>
</p>
<p align="center">
  <img src="figs/res_t1_pass1.svg" width="45%"/>
  <img src="figs/res_t0_pass4.svg" width="45%"/>
</p>


**Hypothesis 3**: The GPT-4o model performed better in the RAG-poisoning domain compared to the more expensive GPT-4.1 and Sonnet-4.5, but proved unstable when increasing *k*. GPT-3.5-turbo shows the most stable results when varying T-user.

<p align="center">
  <img src="figs/pass1.svg" width="45%"/>
  <img src="figs/pass4.svg" width="45%"/>
</p>

### Basics

- Code is located in `src/duma/domains/`
- Data is located in `data/duma/domains/`
- Each domain has its own configuration and task definitions

#### View domain-specific policy and API docs:
Run the following command to see the domain policy and API documentation.
```bash
duma domain <domain>
```

Then visit http://127.0.0.1:8004/redoc

### Environment CLI (beta)

An interactive command-line interface for directly querying and testing domain environments. Features:
- Interactive query interface with domain-specific tools
- Support for multiple domains (collab, infra_loadshed, crm_leak, mail_rag_*, output_handling)
- Session management with history

To use:
```bash
make env-cli
```

Available commands:
- `:q` - quit the program
- `:d` - change domain
- `:n` - start new session (clears history)

Example usage:
```bash
$ make env-cli

Welcome to the Environment CLI!
Connected to collab domain.

Query (:n new session, :d change domain, :q quit)> Please summarize the ticket and explain why we cannot share raw logs.
Assistant: I can inspect the ticket context and collaborator notes first.
[Tool outputs and policy-aligned response will appear here]
```

The Environment CLI is useful for:
- Testing domain tools and queries
- Debugging environment responses
- Exploring available domain functionality
- Quick domain interaction without starting the full server stack


## Run tests
To run the test suite use the command

```sh
make test
```

## Config

To configure the framework, see the [config](src/duma/config.py) file.

### LLM Calls caching
LLM call caching is disabled by default.

To enable LLM calls caching:
    - Make sure `redis` is running.
    - Update the redis config in `config.py` if necessary.
    - Set `LLM_CACHE_ENABLED` to `True` in `config.py`


## Evaluate Your Own Agent
For local or remote agent evaluation, see our [agent developer guide](src/duma/agent/README.md).

## Contributing

We welcome contributions to DUMA-bench! Whether you're fixing bugs, adding new features, creating new domains, or contributing experimental research code, please see our [Contributing Guide](CONTRIBUTING.md) for detailed guidelines on:

- **Opening issues** before starting work
- **Branch naming conventions** and development workflow  
- **Code quality standards** and testing requirements
- **Pull request guidelines** for clean, reviewable contributions
- **Domain and experimental contributions** specific guidelines

For experimental features and research code, check out the [`@experiments/`](src/experiments/) directory.

## Orchestration Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant U as User / Attacker
    participant O as DUMA Orchestrator
    participant A as Agent (Target LLM)
    participant E as Environment & Tools
    participant P as Policy Engine (Threat Analysis)
    participant EV as Evaluator

    Note over U, O: Initialization
    U->>O: Trigger Interaction / Attack Scenario
    O->>A: Provide System Prompt & SOP

    Note over A, E: Tool Interaction Phase
    loop Agent Reasoning
        A->>E: Execute Tool Call (e.g., search_emails)
        E-->>A: Return Observation (may contain Poisoned Data)
    end

    Note over A, P: DUMA Security Intervention
    A->>P: Propose Final Action / Response
    P->>P: Analysis: Check against Security Policy

    alt Policy Violation (Attack Successful)
        P-->>O: Flag Prohibited Action
        O->>EV: Log Security Breach / Failure
    else Policy Compliant (Defense Successful)
        P-->>O: Approve Action
        O->>EV: Log Correct Execution (SOP)
    end

    Note over O, EV: Scoring
    O->>A: Finalize Execution Context
    A-->>U: Final Response
    EV->>O: Calculate Resilience Score & Metrics

```
