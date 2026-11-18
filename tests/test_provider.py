from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from openfeature import api
from openfeature.exception import ErrorCode, FlagNotFoundError
from openfeature.flag_evaluation import Reason
from openfeature.provider import AbstractProvider, ProviderStatus

from octopus_openfeature_provider import (
    OctopusFeatureConfiguration,
    OctopusFeatureProvider,
    ProductMetadata,
)


def new_configuration() -> OctopusFeatureConfiguration:
    return OctopusFeatureConfiguration(
        "client-identifier", ProductMetadata("test-product")
    )


@pytest.fixture
def provider() -> OctopusFeatureProvider:
    return OctopusFeatureProvider(new_configuration())


@pytest.fixture
def registered_provider(
    provider: OctopusFeatureProvider,
) -> Iterator[OctopusFeatureProvider]:
    api.set_provider(provider)
    yield provider
    api.shutdown()
    api.clear_providers()


def test_subclasses_the_sdk_abstract_provider(
    provider: OctopusFeatureProvider,
) -> None:
    assert isinstance(provider, AbstractProvider)


def test_metadata_name(provider: OctopusFeatureProvider) -> None:
    assert provider.get_metadata().name == "octopus-python-provider"


def test_boolean_evaluation_through_the_sdk_returns_the_default_with_flag_not_found(
    registered_provider: OctopusFeatureProvider,
) -> None:
    client = api.get_client()
    assert client.get_provider_status() == ProviderStatus.READY

    details = client.get_boolean_details("some-flag", True)

    assert details.value is True
    assert details.reason == Reason.ERROR
    assert details.error_code == ErrorCode.FLAG_NOT_FOUND


@pytest.mark.parametrize(
    ("evaluate", "default_value"),
    [
        (
            lambda client, default: client.get_string_details("some-flag", default),
            "default",
        ),
        (lambda client, default: client.get_integer_details("some-flag", default), 7),
        (lambda client, default: client.get_float_details("some-flag", default), 1.5),
        (
            lambda client, default: client.get_object_details("some-flag", default),
            {"a": 1},
        ),
    ],
    ids=["string", "integer", "float", "object"],
)
def test_non_boolean_evaluation_through_the_sdk_returns_the_default_with_flag_not_found(
    registered_provider: OctopusFeatureProvider,
    evaluate: Callable[[Any, Any], Any],
    default_value: object,
) -> None:
    details = evaluate(api.get_client(), default_value)

    assert details.value == default_value
    assert details.reason == Reason.ERROR
    assert details.error_code == ErrorCode.FLAG_NOT_FOUND


def test_non_boolean_resolve_raises_flag_not_found_for_an_unknown_flag(
    provider: OctopusFeatureProvider,
) -> None:
    with pytest.raises(FlagNotFoundError):
        provider.resolve_string_details("some-flag", "default")


def test_is_unaffected_by_later_configuration_changes() -> None:
    configuration = new_configuration()
    provider = OctopusFeatureProvider(configuration)

    configuration.cache_duration = timedelta(hours=1)
    configuration.client_identifier = ""

    assert provider._configuration.cache_duration == timedelta(minutes=1)
    assert provider._configuration.client_identifier == "client-identifier"


def test_keeps_a_server_url_set_by_a_test() -> None:
    configuration = new_configuration()
    configuration._server_url = "http://localhost:8080"

    provider = OctopusFeatureProvider(configuration)

    assert provider._configuration._server_url == "http://localhost:8080"


def test_keeps_the_callers_http_client() -> None:
    with httpx.Client() as http_client:
        configuration = OctopusFeatureConfiguration(
            "client-identifier",
            ProductMetadata("test-product"),
            http_client=http_client,
        )

        provider = OctopusFeatureProvider(configuration)

        assert provider._configuration.http_client is http_client


@pytest.mark.parametrize("client_identifier", ["", "   "])
def test_rejects_an_empty_client_identifier(client_identifier: str) -> None:
    configuration = new_configuration()
    configuration.client_identifier = client_identifier

    with pytest.raises(ValueError, match="client_identifier"):
        OctopusFeatureProvider(configuration)


@pytest.mark.parametrize("field", ["cache_duration", "request_timeout"])
@pytest.mark.parametrize("value", [timedelta(0), timedelta(seconds=-1)])
def test_rejects_a_non_positive_duration(field: str, value: timedelta) -> None:
    configuration = new_configuration()
    setattr(configuration, field, value)

    with pytest.raises(ValueError, match=field):
        OctopusFeatureProvider(configuration)


@pytest.mark.parametrize("field", ["cache_duration", "request_timeout"])
def test_rejects_a_duration_that_is_not_a_timedelta(field: str) -> None:
    configuration = new_configuration()
    setattr(configuration, field, 60)

    with pytest.raises(TypeError, match=field):
        OctopusFeatureProvider(configuration)
