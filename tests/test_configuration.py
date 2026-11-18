from datetime import timedelta

import pytest

from octopus_openfeature_provider import (
    OctopusFeatureConfiguration,
    OctopusFeatureProvider,
    ProductMetadata,
)


def test_sets_the_required_values() -> None:
    metadata = ProductMetadata("test-product")

    configuration = OctopusFeatureConfiguration("client-identifier", metadata)

    assert configuration.client_identifier == "client-identifier"
    assert configuration.product_metadata == metadata


def test_sets_defaults() -> None:
    configuration = OctopusFeatureConfiguration(
        "client-identifier", ProductMetadata("test-product")
    )

    assert configuration.cache_duration == timedelta(minutes=1)
    assert configuration.request_timeout == timedelta(seconds=10)
    assert configuration.release_version_override is None
    assert configuration.http_client is None
    assert configuration._server_url == "https://features.octopus.com"


def test_optional_values_are_keyword_only() -> None:
    with pytest.raises(TypeError):
        OctopusFeatureConfiguration(  # type: ignore[call-arg]
            "client-identifier",
            ProductMetadata("test-product"),
            timedelta(minutes=5),
        )


def test_server_url_cannot_be_passed_in() -> None:
    with pytest.raises(TypeError):
        OctopusFeatureConfiguration(  # type: ignore[call-arg]
            "client-identifier",
            ProductMetadata("test-product"),
            _server_url="https://example.com",
        )


@pytest.mark.parametrize(
    "name",
    [
        # .NET reads this one. The Python provider deliberately doesn't.
        "OctoToggle__Url",
        "OCTOTOGGLE__URL",
        "OCTOPUS_FEATURES_URL",
        "OCTOPUS_FEATURE_FLAGS_URL",
        "OCTOPUS_SERVER_URL",
    ],
)
def test_ignores_server_url_environment_variables(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "https://example.com")

    configuration = OctopusFeatureConfiguration(
        "client-identifier", ProductMetadata("test-product")
    )
    provider = OctopusFeatureProvider(configuration)

    assert configuration._server_url == "https://features.octopus.com"
    assert provider._configuration._server_url == "https://features.octopus.com"
