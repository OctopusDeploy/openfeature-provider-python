from collections.abc import Iterator

import pytest
from fake_feature_flags_server import (
    FakeFeatureFlagsServer,
    run_fake_feature_flags_server,
)
from openfeature import api


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-api-snapshot",
        action="store_true",
        help="Rewrite the committed public API snapshot instead of checking it.",
    )


@pytest.fixture
def feature_flags_server() -> Iterator[FakeFeatureFlagsServer]:
    yield from run_fake_feature_flags_server()


@pytest.fixture
def reset_the_sdk() -> Iterator[None]:
    """Shut down every registered provider after the test, so none carries over
    to the next one. Modules that register providers apply it to every test with
    `pytestmark = pytest.mark.usefixtures("reset_the_sdk")`."""
    yield
    api.shutdown()
