"""Requests to the Octopus feature flags service."""

import base64
import binascii
import json
import logging

import httpx

from octopus_openfeature_provider._evaluation_response import EvaluationResponse
from octopus_openfeature_provider._octopus_feature_configuration import (
    OctopusFeatureConfiguration,
)
from octopus_openfeature_provider._v4.parse_server_side_evaluation import (
    InvalidManifestError,
    parse_manifest,
)
from octopus_openfeature_provider._version import __version__

_logger = logging.getLogger(__name__)

EVALUATIONS_PATH = "/api/feature-flags/evaluations/v4/"
CHECK_PATH = "/api/feature-flags/check/v4/"
AUTHORIZATION_HEADER = "Authorization"
OCTOPUS_CLIENT_HEADER = "X-Octopus-Client"
RELEASE_VERSION_HEADER = "X-Release-Version"
CONTENT_HASH_HEADER = "ContentHash"
_PROVIDER_NAME = "openfeature-provider-python"


class ContentHashCheckError(Exception):
    """The check endpoint didn't return a usable content hash."""


class FeatureFlagApiClient:
    """Retrieves evaluations and checks for changes from the feature flags service."""

    def __init__(self, configuration: OctopusFeatureConfiguration) -> None:
        self._server_url = configuration._server_url.rstrip("/")
        self._headers = _build_headers(configuration)

        request_timeout = configuration.request_timeout.total_seconds()
        supplied_client = configuration.http_client
        self._owns_client = supplied_client is None
        if supplied_client is None:
            self._client = httpx.Client(timeout=request_timeout)
            self._timeout = self._client.timeout
        else:
            self._client = supplied_client
            self._timeout = _shorter_timeout(supplied_client.timeout, request_timeout)

    def open(self) -> None:
        if self._owns_client and self._client.is_closed:
            self._client = httpx.Client(timeout=self._timeout)

    def close(self) -> None:
        """Close the HTTP client only if the provider created it"""
        if self._owns_client:
            self._client.close()

    def have_features_changed(self, content_hash: bytes) -> bool:
        if not content_hash:
            return True

        response = self._client.get(
            self._server_url + CHECK_PATH,
            headers=self._headers,
            timeout=self._timeout,
        )

        if not response.is_success:
            raise ContentHashCheckError(
                f"Feature flag check from {self._server_url} had unsuccessful status {response.status_code}"
            )

        return (
            _parse_check_content_hash(response.content, self._server_url)
            != content_hash
        )

    def get_server_side_evaluations(self) -> EvaluationResponse | None:
        response = self._client.get(
            self._server_url + EVALUATIONS_PATH,
            headers=self._headers,
            timeout=self._timeout,
        )

        if response.status_code == httpx.codes.NOT_FOUND:
            _logger.warning(
                "Failed to retrieve feature flags for the client identifier from %s",
                self._server_url,
            )
            return None

        if not response.is_success:
            _logger.warning(
                "Feature flag response from %s had unsuccessful status %d",
                self._server_url,
                response.status_code,
            )
            return None

        raw_content_hash = response.headers.get(CONTENT_HASH_HEADER)
        if raw_content_hash is None:
            _logger.warning(
                "Feature flag response from %s did not contain expected ContentHash header",
                self._server_url,
            )
            return None

        if not raw_content_hash:
            _logger.warning(
                "Feature flag response from %s returned an empty ContentHash header",
                self._server_url,
            )
            return None

        try:
            content_hash = base64.b64decode(raw_content_hash, validate=True)
        except binascii.Error:
            _logger.warning(
                "Feature flag response from %s returned a ContentHash header that is not valid base64",
                self._server_url,
            )
            return None

        try:
            return parse_manifest(response.content, content_hash)
        except InvalidManifestError:
            _logger.warning(
                "Feature flag response content from %s was not a list of flag evaluations",
                self._server_url,
                exc_info=True,
            )
            return None


def _parse_check_content_hash(content: bytes, server_url: str) -> bytes:
    invalid = ContentHashCheckError(
        f"Feature flag check from {server_url} did not return a valid content hash"
    )
    try:
        body = json.loads(content)
    except ValueError as error:
        raise invalid from error

    raw_content_hash = body.get("contentHash") if isinstance(body, dict) else None
    if not isinstance(raw_content_hash, str) or not raw_content_hash:
        raise invalid

    try:
        return base64.b64decode(raw_content_hash, validate=True)
    except binascii.Error as error:
        raise invalid from error


def _build_headers(configuration: OctopusFeatureConfiguration) -> dict[str, str]:
    headers = {
        AUTHORIZATION_HEADER: f"Bearer {configuration.client_identifier}",
        OCTOPUS_CLIENT_HEADER: _octopus_client_header_value(configuration),
    }

    if configuration.release_version_override is not None:
        headers[RELEASE_VERSION_HEADER] = configuration.release_version_override

    return headers


def _octopus_client_header_value(configuration: OctopusFeatureConfiguration) -> str:
    product = configuration.product_metadata
    value = product.name
    if product.version is not None:
        value += f"/{product.version}"
    return f"{value} {_PROVIDER_NAME}/{__version__}"


def _shorter_timeout(
    client_timeout: httpx.Timeout, configuration_timeout: float
) -> httpx.Timeout:
    """Apply the shorter of the client's own timeout and the timeout from configuration.

    httpx has no limit on a request's total time, only on each phase of it, so ``configuration_timeout`` bounds each phase.
    """

    def shorter(own: float | None) -> float:
        return configuration_timeout if own is None else min(own, configuration_timeout)

    return httpx.Timeout(
        connect=shorter(client_timeout.connect),
        read=shorter(client_timeout.read),
        write=shorter(client_timeout.write),
        pool=shorter(client_timeout.pool),
    )
