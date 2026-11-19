from pathlib import Path

import pytest
from api_surface import analyse_api_surface

_SOURCE = Path(__file__).parents[1] / "src"
_SNAPSHOT = Path(__file__).with_name("public_api.txt")


def test_public_api_matches_the_committed_snapshot(
    request: pytest.FixtureRequest,
) -> None:
    surface = analyse_api_surface("octopus_openfeature_provider", _SOURCE)

    if request.config.getoption("--update-api-snapshot"):
        _SNAPSHOT.write_text(surface.text)

    assert surface.text == _SNAPSHOT.read_text(), (
        "The public API changed. If that's deliberate, run "
        "`uv run pytest tests/test_public_api.py --update-api-snapshot` and commit "
        f"{_SNAPSHOT.name}."
    )


def test_public_api_only_exposes_importable_types() -> None:
    surface = analyse_api_surface("octopus_openfeature_provider", _SOURCE)

    assert surface.leaks == []
