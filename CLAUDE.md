# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common commands

- `uv sync --all-extras --group dev` — install the full local development environment.
- `uv run pytest -q` — run the main pytest suite.
- `uv run pytest -q tests/<file>_test.py` — run one test file.
- `uv run pytest -q tests/<file>_test.py::test_name` — run a single test.
- `uv run tox` — run pytest across Python 3.10 through 3.14, matching the tox matrix.
- `uv run pre-commit run --all-files` — run repository formatting, linting, mypy, lockfile, and hygiene hooks.
- `uv run mypy ai_assistant` — run the project type checker directly.
- `uv build` — build the Hatchling wheel and source distribution.
- `uv run typer --app cmd ai_assistant.commands.main utils docs --name ai-assistant --output docs/COMMANDS.md` — regenerate CLI docs after command changes.

CI runs `uv run tox -e <python-version>` for Python 3.10–3.14 plus `uv run pre-commit run --all-files`.

## Architecture overview

This is a Python 3.10+ Typer CLI toolkit published as `ai-assistant`. The package entry points are defined in `pyproject.toml`: `ai-assistant` maps to `ai_assistant.commands.main:cmd`, with additional console scripts for `ghi` and `uv-tool`.

The root CLI uses lazy command loading. `ai_assistant/commands/main.py` declares `_Root.lazy_subcommands`, mapping command names to `("module:cmd", extra)` tuples. `ai_assistant/commands/_lazy.py` renders root help by AST-reading each command module's top-level `helptext` string, without importing heavy optional dependencies. When adding a command, add it to this registry and set the optional dependency extra name when the command requires one.

Most command implementations live in `ai_assistant/commands/`; shared helpers belong in `ai_assistant/lib/`; settings are in `ai_assistant/settings.py` and use `pydantic-settings` with `.env` support for prefixes such as `OPENAI_` and `CLOUDFLARE_`. `ai_assistant/commands/__init__.py` provides `make_typer()` so command modules get a consistent Typer app and `--version` behavior.

Optional feature dependencies are declared as project extras (`mcd`, `oss`, `freshrss`, `docker`, `cookies`, `cursor`, `telegram`, `all`). Commands that need optional dependencies should keep those imports inside command paths loaded only after the lazy resolver runs, so minimal installs and root `--help` stay lightweight.

Tests are in `tests/` with the existing `*_test.py` naming pattern. They cover command behavior, packaging, plugin manifests, security-sensitive helpers, and docs-adjacent behavior. Generated command reference lives in `docs/COMMANDS.md`; refresh it when command arguments, options, help text, or environment variables change.

Plugin assets live under `plugins/`, especially the `agent-bark-notify-*` plugin variants for Claude, Codex, and OpenClaw. Marketplace manifests are under `.claude-plugin/` and `.agents/plugins/`; update the corresponding tests when plugin manifest structure or versions change.

## Security-sensitive areas

README documents several behaviors that need extra care when modified:

- `disable-ssl-verify`, `httpx-disable-verify`, and `requests-disable-verify` install `.pth` patches that globally affect SSL verification inside the target Python environment.
- `httpx-rfc-cache` installs a `.pth` patch that globally wraps `httpx` transport for the target interpreter unless disabled by `AI_ASSISTANT_HTTPX_RFC_CACHE_DISABLE=1`.
- `reality build` can download and execute the upstream Xray install script as root unless `--skip-install` is used.
- `file-change-runner`, `docker-hub-runner`, and `cf-tunnel-watcher` execute user-provided command strings with `shell=True`.
- `agent-bark-notify` audit logging must not record raw hook payloads, Bark device keys/URLs, or full notification bodies.

When changing these areas, update tests and the README warnings together.

## Style and project conventions

Ruff is the formatter/linter with 4-space indentation, double quotes, magic trailing commas, and a 200-character line length. isort uses the `hug` profile. Mypy is configured in `pyproject.toml` with relatively gradual strictness. Pre-commit runs YAML/TOML/JSON checks, whitespace fixes, isort, pycln, mypy, Ruff, and `uv-lock`.

Use Conventional Commit style for commits, e.g. `feat(scope): summary` or `fix(scope): summary`. The repository follows GitHub Flow: branch from `main`, keep changes scoped to an issue, and fill out the PR template with validation, risk, rollback, and AI-assistance details.
