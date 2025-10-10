# Repository Guidelines

## Project Structure & Module Organization
The root `Makefile` and `environment-llm.yml` define the Conda-based workflow; run tools through the `llm` environment (`conda run -n llm ...`). Product docs live in `docs/`, with `docs/JOURNAL.md` capturing history and `docs/AGENT_CONTEXT.md` holding prompt scaffolding. Operational helpers sit in `scripts/`, especially `manage_vllm.sh` for serving and observability. Translation code resides in `tasks/translation/src/` across `core/` (pipelines, quality checks), `cli/` (argument parsing), and `utils/`, while profiles and prompts stay alongside. Runtime artifacts flow to `logs/` and `tasks/translation/logs/`; large datasets belong in `tasks/translation/data/`, already `.gitignore`d.

## Build, Test, and Development Commands
Launch the vLLM service with `make vllm-start` (foreground) or `make vllm-start-bg` (background); follow up with `make vllm-status`, `make vllm-logs`, or `make vllm-stop` as needed. Use `make vllm-test` for a quick `/v1/models` probe via `scripts/check_vllm.py`. Run translations through `make translate` or `make translate-batch INPUT_DIR=...`, both delegating to `scripts/manage_translation.sh`. For lower-level debugging, call `conda run -n llm python tasks/translation/src/translate.py --help`.

## Coding Style & Naming Conventions
Python files use 4-space indentation, type hints, and docstrings for multi-step flows. Keep modules and symbols in `snake_case` and group imports as in `tasks/translation/src/translate.py`. No formatter is locked in; if you run `black` or `ruff format`, stay within the 120-character soft limit and keep diffs minimal.

## Testing Guidelines
Tests rely on the standard library `unittest` runner. Co-locate new specs beside their targets using the `*_test.py` suffix (see `tasks/translation/src/core/quality_checker_test.py`). Execute the suite with `conda run -n llm python -m unittest discover -s tasks/translation/src -p "*_test.py"` and build fixtures that mimic streaming handlers so quality checks cover both acceptance and rejection paths.

## Commit & Pull Request Guidelines
Commits follow Conventional Commit style with scoped types (`refactor(translation): …`, `feat(translation): …`) and concise, imperative summaries. Use Chinese descriptions when matching prior history, and group related changes so review stays focused. Pull requests should state motivation, list the commands exercised, and attach key artifacts such as `logs/latest.log` or sample outputs when behavior shifts.

## Security & Configuration Tips
Never commit API secrets or translation payloads; keep raw inputs in `tasks/translation/data/input/` and outputs in the sibling directory so `.gitignore` protections stay effective. Switch model weights by passing `MODEL=...` into the relevant Make targets instead of editing scripts. When adding dependencies, update both `environment-llm.yml` and `requirements-llm.txt` so fresh environments reproduce without guesswork.
