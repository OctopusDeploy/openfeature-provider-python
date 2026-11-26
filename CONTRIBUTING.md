# Contributing

## Setup

Clone the repository with its submodules:

```bash
git clone --recurse-submodules https://github.com/OctopusDeploy/openfeature-provider-python.git
```

If you've already cloned it without them, fetch them now:

```bash
git submodule update --init
```

The project uses [uv](https://docs.astral.sh/uv/). Install it, then install the project and its development tools:

```bash
uv sync
```

## Specification fixtures

`specification/` is a submodule of [openfeature-provider-specification](https://github.com/OctopusDeploy/openfeature-provider-specification), which holds the fixtures every Octopus provider runs. `tests/test_specification_fixtures.py` runs every case in `specification/Fixtures/*.json` through the real provider and the OpenFeature SDK, against a fake feature flags server, as part of `uv run pytest`. Each test is named `<fixture file> - <case description>`.

The test run fails if the submodule isn't checked out, so the fixtures can't be skipped by accident.

To pick up new fixtures, move the submodule to the specification repository's latest commit and commit the result:

```bash
git submodule update --remote specification
git add specification
```

When a fixture fails, fix the evaluator or the provider, not the test runner. If a fixture itself is wrong, fix it in the specification repository so every provider gets the change.

## Running the checks

CI runs these on every PR, and fails the build if any of them fail. Run them locally before you push.

| Check | Command | Fix it with |
|---|---|---|
| Tests | `uv run pytest` | |
| Linting ([ruff](https://docs.astral.sh/ruff/)) | `uv run ruff check` | `uv run ruff check --fix` for the rules ruff can fix itself |
| Formatting (ruff) | `uv run ruff format --check` | `uv run ruff format` |
| Types ([mypy](https://mypy.readthedocs.io/), strict mode) | `uv run mypy` | |
| Known vulnerabilities ([pip-audit](https://github.com/pypa/pip-audit)) | See [Security vulnerabilities](#security-vulnerabilities) | See [Fixing a vulnerability](#fixing-a-vulnerability) |

Or run them all at once:

```bash
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
```

The configuration for all three tools is in `pyproject.toml`.

CI also runs the tests on every maintained CPython version. To test against one locally, pass `--python`:

```bash
uv run --python 3.11 pytest
```

## Public API

`tests/test_public_api.py` keeps the public API from changing by accident. It fails when:

- **The public API changes without the snapshot changing too.** `tests/public_api.txt` lists every name in the package's `__all__` with its signature, attributes, base classes and decorators. After a deliberate change, update it and commit the result:

  ```bash
  uv run pytest tests/test_public_api.py --update-api-snapshot
  ```

- **The public API exposes a type consumers can't import.** A type from the provider has to be exported from `__init__.py` and listed in `__all__`. A type from anywhere else mustn't come from a private module, for example `httpx._types`.

The check reads the source with [griffe](https://mkdocstrings.github.io/griffe/) rather than importing it, so the snapshot is the same on every Python version. The snapshot includes the members the provider inherits from the OpenFeature SDK, so an SDK update that changes them fails the check too. Review the diff, then update the snapshot.

## Dependencies

`uv.lock` is committed, and CI fails if it's out of date. After changing dependencies in `pyproject.toml`, run `uv lock` and commit the result.

Keep runtime dependencies to a minimum. The provider is a library that customers embed, so every runtime dependency ends up in their apps and their vulnerability scanners.

## Security vulnerabilities

Two things report known vulnerabilities in our dependencies:

- **The `audit` CI job** runs [pip-audit](https://github.com/pypa/pip-audit) against every package in `uv.lock`, including transitive and dev dependencies. It runs on every PR, on pushes to `main` and nightly, and fails the build on any finding. The nightly run catches advisories published against a lockfile that hasn't changed.
- **Dependabot alerts** show in the repository's Security tab and in the team's daily health report.

To run the audit locally:

```bash
uv export --frozen --format requirements.txt --no-emit-project --no-group audit --output-file requirements-audit.txt
uv run --only-group audit pip-audit --requirement requirements-audit.txt --require-hashes --disable-pip --strict
```

`pip-audit` is in its own `audit` dependency group, so `uv sync` doesn't install it and its own dependencies aren't part of what's audited.

### Fixing a vulnerability

Work through these in order, and stop at the first one that works.

1. **Upgrade the direct dependency.** If the vulnerable package is in `[project].dependencies` or a dependency group, raise its minimum version in `pyproject.toml` to the fixed release, then run `uv lock`. If the vulnerability is in a transitive dependency, first check whether a newer release of the direct dependency that pulls it in requires the fixed version, and upgrade to that.
2. **Raise the transitive dependency's minimum.** If no release of the direct dependency fixes it yet, add the transitive package with a minimum of the fixed version, and a comment naming the advisory. Then run `uv lock`:

   ```toml
   dependencies = [
       "openfeature-sdk>=0.10.0,<0.11",
       # CVE-2026-12345: not a direct dependency, raised to the fixed version.
       # Remove once openfeature-sdk requires it.
       "example-package>=2.4.1",
   ]
   ```

   For a runtime dependency, put it in `[project].dependencies`, as above, so customers installing the provider get the fixed version too. Don't use `[tool.uv] constraint-dependencies` for this: it only affects our lockfile, and customers never see it. For a dev-only dependency, add it to the `dev` group instead.
3. **Mitigate it and document it.** If there's no fixed version, or the vulnerable code can't be reached from the provider, record the decision and make the audit ignore that advisory. Add `--ignore-vuln <ID>` to the `pip-audit` command in the `audit` job, with a comment explaining why it's safe and what would end the exception. Also dismiss the matching Dependabot alert with the same reason. Review exceptions whenever the package is upgraded.

## PR titles

PR titles must follow [Conventional Commits](https://www.conventionalcommits.org/), for example `feat: add flag caching`. Release Please uses them to work out the next version and write the changelog.

Don't edit the version in `pyproject.toml`, `uv.lock` or `_version.py`, or `CHANGELOG.md`, by hand. Release Please manages them.

## Releases

Maintainers handle releases. If you're curious how it works, see [RELEASING.md](RELEASING.md).
