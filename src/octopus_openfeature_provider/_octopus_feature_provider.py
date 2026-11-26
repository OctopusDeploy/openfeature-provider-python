import copy
import re
import threading
from collections.abc import Mapping, Sequence
from datetime import timedelta

import httpx
from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import (
    FlagNotFoundError,
    ProviderNotReadyError,
    TypeMismatchError,
)
from openfeature.flag_evaluation import FlagResolutionDetails, FlagValueType
from openfeature.provider import AbstractProvider, Metadata

from octopus_openfeature_provider._feature_flag_api_client import FeatureFlagApiClient
from octopus_openfeature_provider._feature_flag_evaluator import (
    FLAG_NOT_FOUND_MESSAGE,
    FeatureFlagEvaluator,
)
from octopus_openfeature_provider._feature_flag_evaluator_cache import (
    FeatureFlagEvaluatorCache,
)
from octopus_openfeature_provider._octopus_feature_configuration import (
    OctopusFeatureConfiguration,
)

MAX_CACHE_DURATION = timedelta(seconds=threading.TIMEOUT_MAX)

PROVIDER_NOT_READY_MESSAGE = "No Octopus feature flags are available. The provider failed to initialize, or was used before initializing."

# httpx sends header values as ASCII, and rejects control characters in them.
_INVALID_HEADER_VALUE_CHARACTERS = re.compile(r"[^\x20-\x7e]")


class OctopusFeatureProvider(AbstractProvider):
    """An OpenFeature provider for Octopus feature flags.

    Register it with the OpenFeature SDK, for example with
    `openfeature.api.set_provider`. Octopus feature flags are booleans only.

    Until the provider has fetched the flags, every evaluation returns the
    default value with the `PROVIDER_NOT_READY` error code.

    Leading and trailing whitespace, such as the newline at the end of a value
    read from a file, is removed from the client identifier and the release
    version override.

    Raises:
        ValueError: If the configuration's client identifier or release
            version override is empty or contains characters that aren't valid
            in an HTTP header, or its `cache_duration` or `request_timeout`
            isn't positive, or its `cache_duration` is longer than
            `threading.TIMEOUT_MAX` seconds.
        TypeError: If the configuration's client identifier or release version
            override isn't a `str`, its `cache_duration` or `request_timeout`
            isn't a `timedelta`, or its `http_client` isn't an `httpx.Client`.
    """

    def __init__(self, configuration: OctopusFeatureConfiguration) -> None:
        super().__init__()
        # A shallow copy, so the provider is unaffected by later changes to the
        # configuration but still uses the caller's HTTP client.
        self._configuration = copy.copy(configuration)
        _validate_and_clean(self._configuration)
        self._evaluator_cache = FeatureFlagEvaluatorCache(
            FeatureFlagApiClient(self._configuration),
            self._configuration.cache_duration,
        )

    def initialize(self, evaluation_context: EvaluationContext) -> None:
        # Never raises, so the SDK reports the provider as ready even when the
        # fetch fails. Every evaluation then reports PROVIDER_NOT_READY until
        # a refresh succeeds.
        self._evaluator_cache.initialize()

    def shutdown(self) -> None:
        self._evaluator_cache.shutdown()

    def get_metadata(self) -> Metadata:
        return Metadata(name="octopus-python-provider")

    def resolve_boolean_details(
        self,
        flag_key: str,
        default_value: bool,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[bool]:
        return self._require_evaluator().evaluate(flag_key, evaluation_context)

    def resolve_string_details(
        self,
        flag_key: str,
        default_value: str,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[str]:
        raise self._reject_non_boolean_evaluation(flag_key)

    def resolve_integer_details(
        self,
        flag_key: str,
        default_value: int,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[int]:
        raise self._reject_non_boolean_evaluation(flag_key)

    def resolve_float_details(
        self,
        flag_key: str,
        default_value: float,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[float]:
        raise self._reject_non_boolean_evaluation(flag_key)

    def resolve_object_details(
        self,
        flag_key: str,
        default_value: Sequence[FlagValueType] | Mapping[str, FlagValueType],
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[Sequence[FlagValueType] | Mapping[str, FlagValueType]]:
        raise self._reject_non_boolean_evaluation(flag_key)

    def _reject_non_boolean_evaluation(self, flag_key: str) -> Exception:
        evaluator = self._require_evaluator()
        if evaluator.find_evaluation_by_slug(flag_key) is None:
            return FlagNotFoundError(FLAG_NOT_FOUND_MESSAGE)
        return TypeMismatchError("Octopus only supports boolean flags.")

    def _require_evaluator(self) -> FeatureFlagEvaluator:
        """Without any evaluations, an unknown slug can't be told apart from
        one that was never received, so report PROVIDER_NOT_READY rather than
        masking the failure as FLAG_NOT_FOUND."""
        evaluator = self._evaluator_cache.get_evaluator()
        # Every successful fetch has a content hash, so an empty one means no
        # fetch has succeeded yet.
        if not evaluator.content_hash:
            raise ProviderNotReadyError(PROVIDER_NOT_READY_MESSAGE)
        return evaluator


def _validate_and_clean(configuration: OctopusFeatureConfiguration) -> None:
    configuration.client_identifier = _clean_header_value(
        "client_identifier", configuration.client_identifier
    )
    if configuration.release_version_override is not None:
        configuration.release_version_override = _clean_header_value(
            "release_version_override", configuration.release_version_override
        )
    _validate_positive_duration("cache_duration", configuration.cache_duration)
    # The polling thread waits this long between checks, and a longer wait
    # raises OverflowError there, which would stop polling without a log.
    if configuration.cache_duration > MAX_CACHE_DURATION:
        raise ValueError(
            f"cache_duration must be at most {MAX_CACHE_DURATION}, but was {configuration.cache_duration}."
        )
    _validate_positive_duration("request_timeout", configuration.request_timeout)
    http_client = configuration.http_client
    # An httpx.AsyncClient would otherwise fail every request, because its
    # methods return coroutines that are never awaited.
    if http_client is not None and not isinstance(http_client, httpx.Client):
        raise TypeError(
            f"http_client must be an httpx.Client, but was {type(http_client).__name__}."
        )


def _clean_header_value(name: str, value: str) -> str:
    # Callers without a type checker may pass None, for example from an unset
    # environment variable.
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str, but was {type(value).__name__}.")
    # Values read from a file or a mounted secret often end with a newline,
    # which httpx would reject on every request.
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{name} must not be empty.")
    if _INVALID_HEADER_VALUE_CHARACTERS.search(cleaned):
        raise ValueError(
            f"{name} must contain only printable ASCII characters, so it can be sent in an HTTP header."
        )
    return cleaned


def _validate_positive_duration(name: str, value: timedelta) -> None:
    # Callers without a type checker may pass a number of seconds instead.
    if not isinstance(value, timedelta):
        raise TypeError(f"{name} must be a timedelta, but was {type(value).__name__}.")
    if value <= timedelta(0):
        raise ValueError(f"{name} must be positive, but was {value}.")
