from collections.abc import Iterator

import pytest
from fake_feature_flags_server import (
    FakeFeatureFlagsServer,
    run_fake_feature_flags_server,
)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-api-snapshot",
        action="store_true",
        help="Rewrite the committed public API snapshot instead of checking it.",
    )


@pytest.fixture
def feature_flags_server() -> Iterator[FakeFeatureFlagsServer]:
    yield from run_fake_feature_flags_server()
