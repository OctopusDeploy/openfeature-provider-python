import threading
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fake_feature_flags_server import (
    EVALUATIONS_PATH,
    FakeFeatureFlagsServer,
    configuration_for,
)
from openfeature import api
from openfeature.client import OpenFeatureClient
from openfeature.evaluation_context import EvaluationContext
from openfeature.event import EventDetails, ProviderEvent
from openfeature.exception import ErrorCode
from openfeature.flag_evaluation import Reason
from openfeature.provider import AbstractProvider, ProviderStatus

from octopus_openfeature_provider import (
    OctopusFeatureConfiguration,
    OctopusFeatureProvider,
    ProductMetadata,
)

MANIFEST = """
[
    { "slug": "enabled-feature", "value": true, "reason": "The flag is enabled for this environment." },
    { "slug": "disabled-feature", "value": false, "reason": "The flag is disabled for this environment." },
    { "slug": "malformed-feature", "value": "yes" },
    {
        "slug": "pro-feature",
        "evaluationKey": "evaluation-key",
        "rules": [
            {
                "name": "Pro customers",
                "conditions": [
                    { "type": "context-attribute-is-one-of", "key": "plan", "values": ["pro"] }
                ]
            }
        ]
    }
]
"""


def new_configuration() -> OctopusFeatureConfiguration:
    return OctopusFeatureConfiguration(
        "client-identifier", ProductMetadata("test-product")
    )


@pytest.fixture
def provider() -> OctopusFeatureProvider:
    return OctopusFeatureProvider(new_configuration())


@pytest.fixture(autouse=True)
def reset_the_sdk() -> Iterator[None]:
    yield
    api.shutdown()


def client_for(server: FakeFeatureFlagsServer) -> OpenFeatureClient:
    """Register a provider for server, wait until it's initialized, and return
    an SDK client."""
    api.set_provider_and_wait(OctopusFeatureProvider(configuration_for(server)))
    return api.get_client()


def wait_until_ready(client: OpenFeatureClient) -> None:
    ready = threading.Event()

    def on_ready(details: EventDetails) -> None:
        ready.set()

    # Runs at once if the provider is already ready.
    client.add_handler(ProviderEvent.PROVIDER_READY, on_ready)
    assert ready.wait(timeout=5), "The provider never became ready."


def test_subclasses_the_sdk_abstract_provider(
    provider: OctopusFeatureProvider,
) -> None:
    assert isinstance(provider, AbstractProvider)


def test_metadata_name(provider: OctopusFeatureProvider) -> None:
    assert provider.get_metadata().name == "octopus-python-provider"


# Initialization


def test_initialization_fetches_the_evaluations_once(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    feature_flags_server.evaluations.body = MANIFEST

    client_for(feature_flags_server)

    assert [request.path for request in feature_flags_server.requests] == [
        EVALUATIONS_PATH
    ]


def test_evaluation_does_not_fetch_again(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    feature_flags_server.evaluations.body = MANIFEST
    client = client_for(feature_flags_server)

    client.get_boolean_value("enabled-feature", False)
    client.get_string_value("enabled-feature", "default")

    assert len(feature_flags_server.requests) == 1


def test_set_provider_initializes_in_the_background(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    feature_flags_server.evaluations.body = MANIFEST

    api.set_provider(OctopusFeatureProvider(configuration_for(feature_flags_server)))
    client = api.get_client()
    wait_until_ready(client)

    assert client.get_boolean_value("enabled-feature", False) is True


def test_when_the_fetch_fails_the_provider_is_ready_and_every_flag_is_missing(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    feature_flags_server.evaluations.body = MANIFEST
    feature_flags_server.evaluations.status = 500

    client = client_for(feature_flags_server)

    assert client.get_provider_status() == ProviderStatus.READY
    details = client.get_boolean_details("enabled-feature", False)
    assert details.value is False
    assert details.reason == Reason.ERROR
    assert details.error_code == ErrorCode.FLAG_NOT_FOUND


def test_when_the_server_is_unreachable_the_provider_is_ready_and_every_flag_is_missing(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    # Nothing listens on port 1, so the request raises rather than returning
    # an unusable response.
    feature_flags_server.url = "http://127.0.0.1:1"

    client = client_for(feature_flags_server)

    assert client.get_provider_status() == ProviderStatus.READY
    details = client.get_boolean_details("enabled-feature", False)
    assert details.reason == Reason.ERROR
    assert details.error_code == ErrorCode.FLAG_NOT_FOUND


# Boolean evaluation


@pytest.mark.parametrize(
    ("slug", "value", "reason"),
    [
        ("enabled-feature", True, "The flag is enabled for this environment."),
        ("disabled-feature", False, "The flag is disabled for this environment."),
    ],
)
def test_boolean_evaluation_returns_the_server_value_and_reason(
    feature_flags_server: FakeFeatureFlagsServer,
    slug: str,
    value: bool,
    reason: str,
) -> None:
    feature_flags_server.evaluations.body = MANIFEST

    details = client_for(feature_flags_server).get_boolean_details(slug, not value)

    assert details.value is value
    assert details.reason == reason
    assert details.error_code is None


@pytest.mark.parametrize(("plan", "value"), [("pro", True), ("free", False)])
def test_boolean_evaluation_applies_client_side_rules_to_the_context(
    feature_flags_server: FakeFeatureFlagsServer, plan: str, value: bool
) -> None:
    feature_flags_server.evaluations.body = MANIFEST

    details = client_for(feature_flags_server).get_boolean_details(
        "pro-feature", not value, EvaluationContext(attributes={"plan": plan})
    )

    assert details.value is value
    assert details.error_code is None


def test_boolean_evaluation_of_a_missing_flag_returns_the_default_with_flag_not_found(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    feature_flags_server.evaluations.body = MANIFEST

    details = client_for(feature_flags_server).get_boolean_details(
        "missing-feature", True
    )

    assert details.value is True
    assert details.reason == Reason.ERROR
    assert details.error_code == ErrorCode.FLAG_NOT_FOUND


def test_boolean_evaluation_of_a_malformed_flag_returns_the_default_with_parse_error(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    feature_flags_server.evaluations.body = MANIFEST

    details = client_for(feature_flags_server).get_boolean_details(
        "malformed-feature", True
    )

    assert details.value is True
    assert details.reason == Reason.ERROR
    assert details.error_code == ErrorCode.PARSE_ERROR


# Non-boolean evaluation

NON_BOOLEAN_EVALUATIONS = pytest.mark.parametrize(
    ("evaluate", "default_value"),
    [
        (
            lambda client, slug, default: client.get_string_details(slug, default),
            "default",
        ),
        (lambda client, slug, default: client.get_integer_details(slug, default), 7),
        (lambda client, slug, default: client.get_float_details(slug, default), 1.5),
        (
            lambda client, slug, default: client.get_object_details(slug, default),
            {"a": 1},
        ),
    ],
    ids=["string", "integer", "float", "object"],
)


@NON_BOOLEAN_EVALUATIONS
def test_non_boolean_evaluation_of_a_flag_returns_the_default_with_type_mismatch(
    feature_flags_server: FakeFeatureFlagsServer,
    evaluate: Callable[[Any, str, Any], Any],
    default_value: object,
) -> None:
    feature_flags_server.evaluations.body = MANIFEST

    details = evaluate(
        client_for(feature_flags_server), "enabled-feature", default_value
    )

    assert details.value == default_value
    assert details.reason == Reason.ERROR
    assert details.error_code == ErrorCode.TYPE_MISMATCH


@NON_BOOLEAN_EVALUATIONS
def test_non_boolean_evaluation_of_a_missing_flag_returns_the_default_with_flag_not_found(
    feature_flags_server: FakeFeatureFlagsServer,
    evaluate: Callable[[Any, str, Any], Any],
    default_value: object,
) -> None:
    feature_flags_server.evaluations.body = MANIFEST

    details = evaluate(
        client_for(feature_flags_server), "missing-feature", default_value
    )

    assert details.value == default_value
    assert details.reason == Reason.ERROR
    assert details.error_code == ErrorCode.FLAG_NOT_FOUND


# Configuration


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


def test_rejects_a_client_identifier_that_is_not_a_string() -> None:
    configuration = new_configuration()
    configuration.client_identifier = None  # type: ignore[assignment]

    with pytest.raises(TypeError, match="client_identifier"):
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
