import base64
import logging
from datetime import timedelta

import httpx
import pytest
from fake_feature_flags_server import (
    EVALUATIONS_PATH,
    FakeFeatureFlagsServer,
    configuration_for,
)

from octopus_openfeature_provider import ProductMetadata, __version__
from octopus_openfeature_provider._feature_flag_api_client import FeatureFlagApiClient

LOGGER = "octopus_openfeature_provider"

MANIFEST = '[{"slug":"test-feature","value":true,"reason":"The flag is enabled for this environment."}]'


def fetch(server: FakeFeatureFlagsServer, **options: object) -> FeatureFlagApiClient:
    client = FeatureFlagApiClient(configuration_for(server, **options))
    client.get_server_side_evaluations()
    return client


def sent_header(server: FakeFeatureFlagsServer, name: str) -> str | None:
    (request,) = server.requests_to(EVALUATIONS_PATH)
    return request.header(name)


# Requests


def test_requests_the_v4_evaluations_endpoint(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    fetch(feature_flags_server)

    assert [request.path for request in feature_flags_server.requests] == [
        EVALUATIONS_PATH
    ]


def test_tolerates_a_server_url_with_a_trailing_slash(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    configuration = configuration_for(feature_flags_server)
    configuration._server_url += "/"

    FeatureFlagApiClient(configuration).get_server_side_evaluations()

    assert len(feature_flags_server.requests_to(EVALUATIONS_PATH)) == 1


def test_sends_the_client_identifier_as_a_bearer_token(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    fetch(feature_flags_server)

    assert (
        sent_header(feature_flags_server, "Authorization") == "Bearer client-identifier"
    )


def test_sends_the_product_and_provider_in_the_octopus_client_header(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    fetch(feature_flags_server)

    assert (
        sent_header(feature_flags_server, "X-Octopus-Client")
        == f"test-product openfeature-provider-python/{__version__}"
    )


def test_includes_the_product_version_in_the_octopus_client_header(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    configuration = configuration_for(feature_flags_server)
    configuration.product_metadata = ProductMetadata("My Product", "2026.1.0")

    FeatureFlagApiClient(configuration).get_server_side_evaluations()

    assert (
        sent_header(feature_flags_server, "X-Octopus-Client")
        == f"MyProduct/2026.1.0 openfeature-provider-python/{__version__}"
    )


def test_sends_the_release_version_override_when_set(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    fetch(feature_flags_server, release_version_override="2026.1.0")

    assert sent_header(feature_flags_server, "X-Release-Version") == "2026.1.0"


def test_omits_the_release_version_header_when_not_set(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    fetch(feature_flags_server)

    assert sent_header(feature_flags_server, "X-Release-Version") is None


def test_uses_a_supplied_http_client_without_letting_its_headers_override_ours(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    with httpx.Client(
        headers={"Authorization": "Bearer someone-else", "X-Custom": "kept"}
    ) as http_client:
        fetch(feature_flags_server, http_client=http_client)

    assert (
        sent_header(feature_flags_server, "Authorization") == "Bearer client-identifier"
    )
    assert sent_header(feature_flags_server, "X-Custom") == "kept"


# Responses


def test_returns_the_parsed_evaluations_and_decoded_content_hash(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    feature_flags_server.evaluations.body = MANIFEST
    feature_flags_server.evaluations.content_hash = base64.b64encode(
        b"\x01\x02"
    ).decode()

    response = FeatureFlagApiClient(
        configuration_for(feature_flags_server)
    ).get_server_side_evaluations()

    assert response is not None
    assert response.content_hash == b"\x01\x02"
    assert [evaluation.slug for evaluation in response.evaluations] == ["test-feature"]


@pytest.mark.parametrize(
    ("status", "content_hash", "body"),
    [
        (404, base64.b64encode(b"\x01").decode(), MANIFEST),
        (500, base64.b64encode(b"\x01").decode(), MANIFEST),
        (401, None, ""),
        (200, None, MANIFEST),
        (200, "", MANIFEST),
        (200, "not base64!", MANIFEST),
        (200, base64.b64encode(b"\x01").decode(), "not json"),
        (200, base64.b64encode(b"\x01").decode(), "null"),
        (200, base64.b64encode(b"\x01").decode(), '{"slug":"test-feature"}'),
    ],
    ids=[
        "not-found",
        "server-error",
        "unauthorized",
        "missing-content-hash",
        "empty-content-hash",
        "invalid-content-hash",
        "invalid-json",
        "null-body",
        "not-a-list",
    ],
)
def test_returns_none_and_warns_for_an_unusable_response(
    feature_flags_server: FakeFeatureFlagsServer,
    caplog: pytest.LogCaptureFixture,
    status: int,
    content_hash: str | None,
    body: str,
) -> None:
    feature_flags_server.evaluations.status = status
    feature_flags_server.evaluations.content_hash = content_hash
    feature_flags_server.evaluations.body = body

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        response = FeatureFlagApiClient(
            configuration_for(feature_flags_server)
        ).get_server_side_evaluations()

    assert response is None
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_raises_when_the_server_cannot_be_reached(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    configuration = configuration_for(feature_flags_server)
    # Nothing listens on port 1.
    configuration._server_url = "http://127.0.0.1:1"

    with pytest.raises(httpx.ConnectError):
        FeatureFlagApiClient(configuration).get_server_side_evaluations()


# Timeouts


def test_a_response_slower_than_the_request_timeout_times_out(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    feature_flags_server.evaluations.delay = 5

    client = FeatureFlagApiClient(
        configuration_for(
            feature_flags_server, request_timeout=timedelta(milliseconds=100)
        )
    )

    with pytest.raises(httpx.TimeoutException):
        client.get_server_side_evaluations()


def test_the_request_timeout_applies_to_a_supplied_client_without_its_own_timeout(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    feature_flags_server.evaluations.delay = 5

    with (
        httpx.Client(timeout=None) as unlimited_client,  # noqa: S113 - deliberately unlimited
        pytest.raises(httpx.TimeoutException),
    ):
        fetch(
            feature_flags_server,
            request_timeout=timedelta(milliseconds=100),
            http_client=unlimited_client,
        )


def test_a_supplied_clients_shorter_timeout_wins(
    feature_flags_server: FakeFeatureFlagsServer,
) -> None:
    feature_flags_server.evaluations.delay = 5

    with httpx.Client(timeout=0.1) as http_client:
        client = FeatureFlagApiClient(
            configuration_for(
                feature_flags_server,
                request_timeout=timedelta(minutes=1),
                http_client=http_client,
            )
        )

        with pytest.raises(httpx.TimeoutException):
            client.get_server_side_evaluations()
