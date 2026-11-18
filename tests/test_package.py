from importlib import metadata
from importlib.resources import files

import octopus_openfeature_provider


def test_version_constant_matches_package_metadata() -> None:
    assert octopus_openfeature_provider.__version__ == metadata.version(
        "octopus-openfeature-provider"
    )


def test_package_ships_py_typed() -> None:
    assert files("octopus_openfeature_provider").joinpath("py.typed").is_file()


def test_package_exports_only_the_public_api() -> None:
    assert sorted(octopus_openfeature_provider.__all__) == [
        "OctopusFeatureConfiguration",
        "OctopusFeatureProvider",
        "ProductMetadata",
        "__version__",
    ]
