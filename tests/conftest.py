import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-api-snapshot",
        action="store_true",
        help="Rewrite the committed public API snapshot instead of checking it.",
    )
