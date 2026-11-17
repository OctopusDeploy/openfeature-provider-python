# Contributing

## Setup

The project uses [uv](https://docs.astral.sh/uv/). Install it, then install the project and its development tools:

```bash
uv sync
```

## Running the checks

CI runs these on every PR, and fails the build if any of them fail. Run them locally before you push.

| Check | Command | Fix it with |
|---|---|---|
| Tests | `uv run pytest` | |
| Linting ([ruff](https://docs.astral.sh/ruff/)) | `uv run ruff check` | `uv run ruff check --fix` for the rules ruff can fix itself |
| Formatting (ruff) | `uv run ruff format --check` | `uv run ruff format` |
| Types ([mypy](https://mypy.readthedocs.io/), strict mode) | `uv run mypy` | |

Or run them all at once:

```bash
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
```

The configuration for all three tools is in `pyproject.toml`.

CI also runs the tests on every maintained CPython version. To test against one locally, pass `--python`:

```bash
uv run --python 3.11 pytest
```

## Dependencies

`uv.lock` is committed, and CI fails if it's out of date. After changing dependencies in `pyproject.toml`, run `uv lock` and commit the result.

## PR titles

PR titles must follow [Conventional Commits](https://www.conventionalcommits.org/), for example `feat: add flag caching`. Release Please uses them to work out the next version and write the changelog.
