import base64
import logging
import threading
import time
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fake_feature_flags_server import (
    CHECK_PATH,
    EVALUATIONS_PATH,
    FakeFeatureFlagsServer,
    check_body,
    configuration_for,
)
from openfeature import api
from openfeature.client import OpenFeatureClient
from openfeature.evaluation_context import EvaluationContext
from openfeature.event import EventDetails, ProviderEvent
from openfeature.exception import ErrorCode, FlagNotFoundError
from openfeature.flag_evaluation import Reason
from openfeature.provider import AbstractProvider, ProviderStatus

from octopus_openfeature_provider import (
    OctopusFeatureConfiguration,
    OctopusFeatureProvider,
    ProductMetadata,
)
from octopus_openfeature_provider._feature_flag_evaluator_cache import (
    POLLING_THREAD_NAME,
)
from octopus_openfeature_provider._octopus_feature_provider import MAX_CACHE_DURATION

pytestmark = pytest.mark.usefixtures("reset_the_sdk")

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


def client_for(server: FakeFeatureFlagsServer, **options: Any) -> OpenFeatureClient:
    """Register a provider for server, wait until it's initialized, and return
    an SDK client."""
    api.set_provider_and_wait(
        OctopusFeatureProvider(configuration_for(server, **options))
    )
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


# Polling

POLL_INTERVAL = timedelta(milliseconds=20)
CHANGED_MANIFEST = (
    '[{ "slug": "enabled-feature", "value": false, "reason": "Changed." }]'
)
CHANGED_CONTENT_HASH = base64.b64encode(b"\x02").decode()
LOGGER = "octopus_openfeature_provider"


def wait_until(condition: Callable[[], bool], timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "Timed out waiting for the condition."
        time.sleep(0.005)


def wait_for_checks(server: FakeFeatureFlagsServer, count: int) -> None:
    already = len(server.requests_to(CHECK_PATH))
    wait_until(lambda: len(server.requests_to(CHECK_PATH)) >= already + count)


def change_manifest(server: FakeFeatureFlagsServer) -> None:
    server.evaluations.body = CHANGED_MANIFEST
    server.evaluations.content_hash = CHANGED_CONTENT_HASH
    server.check.body = check_body(CHANGED_CONTENT_HASH)


def polling_threads() -> list[threading.Thread]:
    return [
        thread for thread in threading.enumerate() if thread.name == POLLING_THREAD_NAME
    ]


@pytest.fixture
def polling_provider(
    feature_flags_server: FakeFeatureFlagsServer,
) -> Iterator[OctopusFeatureProvider]:
    """A provider that polls every POLL_INTERVAL. It's shut down after the
    test, so its polling thread can't leak into later tests."""
    provider = OctopusFeatureProvider(
        configuration_for(feature_flags_server, cache_duration=POLL_INTERVAL)
    )
    yield provider
    provider.shutdown()


def test_polling_does_not_fetch_again_while_the_content_hash_is_unchanged(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    feature_flags_server.evaluations.body = MANIFEST
    client = client_for(feature_flags_server, cache_duration=POLL_INTERVAL)

    wait_for_checks(feature_flags_server, 3)

    assert len(feature_flags_server.requests_to(EVALUATIONS_PATH)) == 1
    assert client.get_boolean_value("enabled-feature", False) is True


def test_polling_fetches_and_serves_the_new_manifest_when_the_content_hash_changes(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    feature_flags_server.evaluations.body = MANIFEST
    client = client_for(feature_flags_server, cache_duration=POLL_INTERVAL)

    change_manifest(feature_flags_server)

    wait_until(lambda: client.get_boolean_value("enabled-feature", True) is False)
    assert client.get_boolean_details("enabled-feature", True).reason == "Changed."
    # The removed flag is gone too, so the whole manifest was replaced.
    assert (
        client.get_boolean_details("disabled-feature", True).error_code
        == ErrorCode.FLAG_NOT_FOUND
    )
    # Once the new manifest is held, its hash matches and it isn't fetched again.
    wait_for_checks(feature_flags_server, 2)
    assert len(feature_flags_server.requests_to(EVALUATIONS_PATH)) == 2


def test_polling_waits_the_cache_duration_between_checks(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    client_for(feature_flags_server, cache_duration=timedelta(hours=1))

    time.sleep(0.1)

    assert feature_flags_server.requests_to(CHECK_PATH) == []


def fail_the_check_with_an_http_error(server: FakeFeatureFlagsServer) -> None:
    server.check.status = 500


def return_a_malformed_check_body(server: FakeFeatureFlagsServer) -> None:
    server.check.body = "not json"


def time_out_the_check(server: FakeFeatureFlagsServer) -> None:
    server.check.delay = 1


def fail_the_fetch_of_a_changed_manifest_with_an_http_error(
    server: FakeFeatureFlagsServer,
) -> None:
    change_manifest(server)
    server.evaluations.status = 500


def return_a_malformed_changed_manifest(server: FakeFeatureFlagsServer) -> None:
    change_manifest(server)
    server.evaluations.body = "not json"


@pytest.mark.parametrize(
    "break_the_server",
    [
        fail_the_check_with_an_http_error,
        return_a_malformed_check_body,
        time_out_the_check,
        fail_the_fetch_of_a_changed_manifest_with_an_http_error,
        return_a_malformed_changed_manifest,
    ],
)
def test_a_failed_refresh_keeps_the_last_good_manifest_and_logs_then_recovers(
    feature_flags_server: FakeFeatureFlagsServer,
    caplog: pytest.LogCaptureFixture,
    break_the_server: Callable[[FakeFeatureFlagsServer], None],
) -> None:
    feature_flags_server.evaluations.body = MANIFEST

    with caplog.at_level(logging.ERROR, logger=LOGGER):
        client = client_for(
            feature_flags_server,
            cache_duration=POLL_INTERVAL,
            request_timeout=timedelta(milliseconds=100),
        )
        break_the_server(feature_flags_server)

        wait_until(
            lambda: any(
                "Retaining the existing evaluations" in record.getMessage()
                for record in caplog.records
            )
        )

    assert client.get_boolean_value("enabled-feature", False) is True

    # The service recovers and serves a changed manifest.
    feature_flags_server.check.status = 200
    feature_flags_server.check.delay = 0
    feature_flags_server.evaluations.status = 200
    change_manifest(feature_flags_server)

    wait_until(lambda: client.get_boolean_value("enabled-feature", True) is False)


def test_a_failed_refresh_is_retried_every_cache_duration(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    feature_flags_server.evaluations.body = MANIFEST
    client_for(feature_flags_server, cache_duration=POLL_INTERVAL)
    feature_flags_server.check.status = 500

    # Polling carries on after failures rather than giving up.
    wait_for_checks(feature_flags_server, 3)


def test_polling_fetches_the_manifest_without_checking_when_initialization_failed(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    feature_flags_server.evaluations.status = 500
    client = client_for(feature_flags_server, cache_duration=POLL_INTERVAL)

    wait_until(lambda: len(feature_flags_server.requests_to(EVALUATIONS_PATH)) >= 3)
    # With no manifest there's no hash to compare, so it doesn't check.
    assert feature_flags_server.requests_to(CHECK_PATH) == []

    feature_flags_server.evaluations.status = 200
    feature_flags_server.evaluations.body = MANIFEST

    wait_until(lambda: client.get_boolean_value("enabled-feature", False) is True)


# Shutdown


def test_shutdown_stops_polling_and_leaves_no_thread_behind(
    feature_flags_server: FakeFeatureFlagsServer,
    polling_provider: OctopusFeatureProvider,
) -> None:
    api.set_provider_and_wait(polling_provider)
    wait_for_checks(feature_flags_server, 1)
    assert len(polling_threads()) == 1

    polling_provider.shutdown()

    assert polling_threads() == []


def test_shutdown_is_idempotent(
    polling_provider: OctopusFeatureProvider,
) -> None:
    polling_provider.initialize(EvaluationContext())

    polling_provider.shutdown()
    polling_provider.shutdown()

    assert polling_threads() == []


def test_shutdown_before_initialization_does_not_raise(
    provider: OctopusFeatureProvider,
) -> None:
    provider.shutdown()

    assert polling_threads() == []


def test_initialization_after_shutdown_fetches_and_polls_again(
    feature_flags_server: FakeFeatureFlagsServer,
    polling_provider: OctopusFeatureProvider,
) -> None:
    feature_flags_server.evaluations.body = MANIFEST
    polling_provider.initialize(EvaluationContext())
    polling_provider.shutdown()

    polling_provider.initialize(EvaluationContext())

    assert len(feature_flags_server.requests_to(EVALUATIONS_PATH)) == 2
    assert len(polling_threads()) == 1
    # The HTTP client closed by shutdown was replaced, so polling works.
    wait_for_checks(feature_flags_server, 2)


def test_a_provider_set_again_after_sdk_shutdown_serves_new_manifests(
    feature_flags_server: FakeFeatureFlagsServer,
    polling_provider: OctopusFeatureProvider,
) -> None:
    feature_flags_server.evaluations.body = MANIFEST
    api.set_provider_and_wait(polling_provider)
    api.shutdown()

    api.set_provider_and_wait(polling_provider)
    change_manifest(feature_flags_server)

    client = api.get_client()
    assert client.get_provider_status() == ProviderStatus.READY
    wait_until(lambda: client.get_boolean_value("enabled-feature", True) is False)


def test_initializing_again_discards_evaluations_from_the_earlier_start(
    feature_flags_server: FakeFeatureFlagsServer,
    polling_provider: OctopusFeatureProvider,
) -> None:
    feature_flags_server.evaluations.body = MANIFEST
    polling_provider.initialize(EvaluationContext())
    polling_provider.shutdown()
    feature_flags_server.evaluations.status = 500

    polling_provider.initialize(EvaluationContext())

    with pytest.raises(FlagNotFoundError):
        polling_provider.resolve_boolean_details("enabled-feature", False)


def test_initializing_twice_leaves_one_polling_thread(
    polling_provider: OctopusFeatureProvider,
) -> None:

    polling_provider.initialize(EvaluationContext())
    polling_provider.initialize(EvaluationContext())

    assert len(polling_threads()) == 1
    polling_provider.shutdown()
    assert polling_threads() == []


def test_shutdown_waits_for_a_refresh_in_flight(
    feature_flags_server: FakeFeatureFlagsServer,
    polling_provider: OctopusFeatureProvider,
) -> None:
    feature_flags_server.check.delay = 0.3
    polling_provider.initialize(EvaluationContext())
    wait_until(lambda: len(feature_flags_server.requests_to(CHECK_PATH)) == 1)

    polling_provider.shutdown()

    assert polling_threads() == []


def test_shutdown_during_initialization_does_not_start_polling(
    feature_flags_server: FakeFeatureFlagsServer,
    polling_provider: OctopusFeatureProvider,
) -> None:
    feature_flags_server.evaluations.delay = 0.3
    feature_flags_server.evaluations.body = MANIFEST
    initializing = threading.Thread(
        target=polling_provider.initialize, args=(EvaluationContext(),)
    )
    initializing.start()
    wait_until(lambda: len(feature_flags_server.requests_to(EVALUATIONS_PATH)) == 1)

    polling_provider.shutdown()

    initializing.join(timeout=2)
    assert not initializing.is_alive()
    assert polling_threads() == []
    with pytest.raises(FlagNotFoundError):
        polling_provider.resolve_boolean_details("enabled-feature", False)


def test_shutdown_closes_the_http_client_the_provider_created(
    polling_provider: OctopusFeatureProvider,
) -> None:
    polling_provider.initialize(EvaluationContext())

    polling_provider.shutdown()

    assert polling_provider._evaluator_cache._api_client._client.is_closed


def test_shutdown_never_closes_a_supplied_http_client(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    with httpx.Client() as http_client:
        provider = OctopusFeatureProvider(
            configuration_for(feature_flags_server, http_client=http_client)
        )
        provider.initialize(EvaluationContext())

        provider.shutdown()

        assert not http_client.is_closed


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


@pytest.mark.parametrize(
    "value",
    [MAX_CACHE_DURATION + timedelta(seconds=1), timedelta.max],
)
def test_rejects_a_cache_duration_too_long_to_wait(value: timedelta) -> None:
    configuration = new_configuration()
    configuration.cache_duration = value

    with pytest.raises(ValueError, match="cache_duration"):
        OctopusFeatureProvider(configuration)


def test_accepts_the_longest_cache_duration() -> None:
    configuration = new_configuration()
    configuration.cache_duration = MAX_CACHE_DURATION

    OctopusFeatureProvider(configuration)


@pytest.mark.parametrize("field", ["cache_duration", "request_timeout"])
def test_rejects_a_duration_that_is_not_a_timedelta(field: str) -> None:
    configuration = new_configuration()
    setattr(configuration, field, 60)

    with pytest.raises(TypeError, match=field):
        OctopusFeatureProvider(configuration)
