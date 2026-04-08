# Repository Guidelines

## Project Structure & Module Organization
The Conda specs in `environment-llm.yml` and the root `Makefile` define how every tool is invoked through the `llm` environment. Product documentation sits in `docs/`, with `docs/PROJECT_STATUS.md` as the current source of truth for active priorities and component status, `docs/AGENT_CONTEXT.md` for stable project context, and `docs/journal/README.md` for historical decisions and operational notes. Translation logic is under `tasks/translation/src/` with `core/` for pipelines and QA, `cli/` for user entry points, and `utils/` for helpers; prompts, profiles, and configs live alongside. Runtime artifacts land in `logs/` or `tasks/translation/logs/`, while large datasets belong in `tasks/translation/data/` (git-ignored). Shell utilities are collected in `scripts/`, notably `manage_vllm.sh` for lifecycle commands.

## Build, Test, and Development Commands
Key invocations (always `conda run -n llm ...` if not using `make`):
- `make vllm-start` / `make vllm-start-bg`: boot the vLLM server in foreground/background, then inspect with `make vllm-status` or `make vllm-logs`.
- `make vllm-stop`: gracefully shut down the server before switching models or branches.
- `make translate` and `make translate-batch INPUT_DIR=...`: orchestrate translation jobs via `scripts/manage_translation.sh`.
- `python tasks/translation/src/translate.py --help`: inspect lower-level flags when debugging CLI behavior.

## Coding Style & Naming Conventions
Use Python 4-space indentation, type hints for public functions, and concise docstrings for multi-step routines. Modules, variables, and files stay in `snake_case`, while Make targets use `kebab-case`. Follow the import layout used in `tasks/translation/src/translate.py`, and keep lines within ~120 characters. Formatters such as `black` or `ruff format` are optional—run them only on the files you touch and commit the resulting diffs.

## Testing Guidelines
Unit tests lean on `unittest`. Name files `*_test.py` and co-locate them near the code they validate (example: `tasks/translation/src/core/quality_checker_test.py`). Run the entire suite with `conda run -n llm python -m unittest discover -s tasks/translation/src -p "*_test.py"`. Provide fixtures that simulate both successful and rejected translation events so quality gates and logging branches receive coverage; attach representative inputs in `tasks/translation/data/test/` when documenting failures.

## Commit & Pull Request Guidelines
Commits follow Conventional Commit prefixes with scopes such as `feat(translation): add glossary filters` or `fix(vllm): retry startup`. Keep subject lines under 72 characters and describe user-visible behavior in the body when necessary. Pull requests should link to the motivating issue, summarize affected Make targets, list verification commands (e.g., `make translate` + dataset), and attach logs or sample translations when behavior changes. Request reviews from an owner familiar with the translation pipeline before merging, and rebase to keep the history linear.
