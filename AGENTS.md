# Repository Guidelines

## Project Structure & Module Organization

`ai_assistant/` contains the Python package and CLI entry points. Most commands live in `ai_assistant/commands/`; shared helpers belong in `ai_assistant/lib/`, settings in `ai_assistant/settings.py`, and typed public package metadata in `ai_assistant/py.typed`. Tests are in `tests/` and generally mirror command behavior with files named `*_test.py`. Generated CLI documentation is kept in `docs/COMMANDS.md`, with design notes under `docs/design/`. Agent notification plugin assets live in `plugins/`, especially `plugins/agent-bark-notify-openclaw/`.

## Build, Test, and Development Commands

- `uv sync --all-extras --group dev`: install the full local development environment.
- `uv run pytest -q`: run the main test suite.
- `uv run tox`: run pytest across the configured Python versions, 3.10 through 3.14.
- `uv run pre-commit run --all-files`: run formatting, linting, and configured repository hooks.
- `uv build`: build the wheel and source distribution with Hatchling.
- `uv run typer --app cmd ai_assistant.commands.main utils docs --name ai-assistant --output docs/COMMANDS.md`: refresh generated CLI docs after command changes.

## Coding Style & Naming Conventions

Use Python 3.10+ and keep code typed where practical. Ruff is the formatter and linter: 4-space indentation, double quotes, magic trailing commas, and a 200-character line length are configured in `pyproject.toml`. Prefer adding new CLI commands through the lazy command registry in `ai_assistant/commands/main.py`, using clear command module names such as `pypi_upload.py` or `httpx_rfc_cache.py`. Keep optional dependency imports inside command paths that require the matching extra.

## Testing Guidelines

Use pytest for unit and behavior tests. Add or update tests in `tests/` when changing command behavior, plugin manifests, packaging, or security-sensitive helpers. Name new test files with the existing `*_test.py` pattern. Before opening a PR, run `uv run pytest -q`; for compatibility-sensitive changes, also run `uv run tox`.

## Commit & Pull Request Guidelines

Recent history follows Conventional Commit style, for example `feat(agent-bark-notify): support OpenClaw icon`, `fix(openclaw): notify on sent messages`, and `chore: bump version to 0.4.9`. Keep commits scoped and imperative. PRs should follow `.github/PULL_REQUEST_TEMPLATE.md`: include a summary, linked issue, change type, impact, validation, risk and rollback plan, AI assistance disclosure, and reviewer focus. Attach screenshots or logs when changing user-visible CLI output, docs generation, or plugin behavior.

## Security & Configuration Tips

Do not commit real secrets, tokens, certificates, private keys, `.env`, or `.pypirc`. Treat commands that alter SSL verification, install `.pth` hooks, execute shell strings, or call external services as security-sensitive; update README warnings and tests when their behavior changes.
