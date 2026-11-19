import dataclasses

import pytest

from octopus_openfeature_provider import ProductMetadata


def test_keeps_a_name_of_valid_characters_unchanged() -> None:
    assert ProductMetadata("OctopusDeploy").name == "OctopusDeploy"


def test_strips_characters_that_are_not_tchars_from_the_name() -> None:
    metadata = ProductMetadata("My ,Product (v2.0)/release@2024:final")

    assert metadata.name == "MyProductv2.0release2024final"


def test_keeps_every_tchar_symbol() -> None:
    symbols = "!#$%&'*+-.^_`|~"

    assert ProductMetadata(symbols).name == symbols


def test_strips_non_ascii_characters() -> None:
    assert ProductMetadata("Café™").name == "Caf"


def test_version_defaults_to_none() -> None:
    assert ProductMetadata("MyProduct").version is None


def test_keeps_a_version_of_valid_characters_unchanged() -> None:
    assert ProductMetadata("MyProduct", "2024.1.0").version == "2024.1.0"


def test_strips_characters_that_are_not_tchars_from_the_version() -> None:
    assert ProductMetadata("MyProduct", "2024.1 (beta)").version == "2024.1beta"


@pytest.mark.parametrize("name", ["", "   ", "()/"])
def test_rejects_a_name_that_is_empty_after_cleaning(name: str) -> None:
    with pytest.raises(ValueError, match="Product name"):
        ProductMetadata(name)


@pytest.mark.parametrize("version", ["", "   ", "()/"])
def test_rejects_a_version_that_is_empty_after_cleaning(version: str) -> None:
    with pytest.raises(ValueError, match="Product version"):
        ProductMetadata("MyProduct", version)


def test_is_immutable() -> None:
    metadata = ProductMetadata("MyProduct")

    with pytest.raises(dataclasses.FrozenInstanceError):
        metadata.name = "Other"  # type: ignore[misc]


def test_compares_by_value() -> None:
    assert ProductMetadata("My Product", "1.0") == ProductMetadata("MyProduct", "1.0")
