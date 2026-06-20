# Contributing

This repository uses GitHub Flow.

## Workflow

1. Open or pick an issue before starting work.
2. Create a branch from `main`. Prefer `type/issue-id-short-summary` when ref names allow it.
3. Keep the change scoped to the issue.
4. Run local checks before opening a pull request.
5. Open a pull request and fill in the repository template.

## Local Checks

```shell
uv sync --all-extras --group dev
uv run pre-commit run --all-files
uv run pytest -q
```

## Commit Messages

Use Conventional Commits:

```text
type(scope): short summary (#issue)
```

Common types are `feat`, `fix`, `docs`, `ci`, `chore`, `refactor`, and `test`.

## Security

Do not commit API keys, tokens, passwords, private keys, `.env`, local virtual environments, build outputs, or cache directories. Use `.env.example` to document required variables without real values.
