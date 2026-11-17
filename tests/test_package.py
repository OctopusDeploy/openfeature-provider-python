from importlib import metadata
from importlib.resources import files

import openfeature.api

import octopus_openfeature_provider


def test_version_constant_matches_package_metadata() -> None:
    assert octopus_openfeature_provider.__version__ == metadata.version(
        "octopus-openfeature-provider"
    )


def test_package_ships_py_typed() -> None:
    assert files("octopus_openfeature_provider").joinpath("py.typed").is_file()


def test_openfeature_sdk_is_installed() -> None:
    # Keeps the dependency honest until the provider imports it for real.
    assert callable(openfeature.api.get_client)
