import copy
import threading
from collections.abc import Mapping, Sequence
from datetime import timedelta

from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import FlagNotFoundError, TypeMismatchError
from openfeature.flag_evaluation import FlagResolutionDetails, FlagValueType
from openfeature.provider import AbstractProvider, Metadata

from octopus_openfeature_provider._feature_flag_api_client import FeatureFlagApiClient
from octopus_openfeature_provider._feature_flag_evaluator import FLAG_NOT_FOUND_MESSAGE
from octopus_openfeature_provider._feature_flag_evaluator_cache import (
    FeatureFlagEvaluatorCache,
)
from octopus_openfeature_provider._octopus_feature_configuration import (
    OctopusFeatureConfiguration,
)

MAX_CACHE_DURATION = timedelta(seconds=threading.TIMEOUT_MAX)


class OctopusFeatureProvider(AbstractProvider):
    """An OpenFeature provider for Octopus feature flags.

    Register it with the OpenFeature SDK, for example with
    `openfeature.api.set_provider`. Octopus feature flags are booleans only.

    Raises:
        ValueError: If the configuration's client identifier is empty, or its
            `cache_duration` or `request_timeout` isn't positive, or its
            `cache_duration` is longer than `threading.TIMEOUT_MAX` seconds.
        TypeError: If the configuration's client identifier isn't a `str`,
            or its `cache_duration` or `request_timeout` isn't a `timedelta`.
    """

    def __init__(self, configuration: OctopusFeatureConfiguration) -> None:
        super().__init__()
        # A shallow copy, so the provider is unaffected by later changes to the
        # configuration but still uses the caller's HTTP client.
        self._configuration = copy.copy(configuration)
        _validate(self._configuration)
        self._evaluator_cache = FeatureFlagEvaluatorCache(
            FeatureFlagApiClient(self._configuration),
            self._configuration.cache_duration,
        )

    def initialize(self, evaluation_context: EvaluationContext) -> None:
        # Never raises, so the SDK reports the provider as ready even when the
        # fetch fails. Every flag is then missing until a refresh succeeds.
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
        return self._evaluator_cache.get_evaluator().evaluate(
            flag_key, evaluation_context
        )

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
        evaluator = self._evaluator_cache.get_evaluator()
        if evaluator.find_evaluation_by_slug(flag_key) is None:
            return FlagNotFoundError(FLAG_NOT_FOUND_MESSAGE)
        return TypeMismatchError("Octopus only supports boolean flags.")


def _validate(configuration: OctopusFeatureConfiguration) -> None:
    client_identifier = configuration.client_identifier
    # Callers without a type checker may pass None, for example from an unset
    # environment variable.
    if not isinstance(client_identifier, str):
        raise TypeError(
            f"client_identifier must be a str, but was {type(client_identifier).__name__}."
        )
    if not client_identifier.strip():
        raise ValueError("client_identifier must not be empty.")
    _validate_positive_duration("cache_duration", configuration.cache_duration)
    # The polling thread waits this long between checks, and a longer wait
    # raises OverflowError there, which would stop polling without a log.
    if configuration.cache_duration > MAX_CACHE_DURATION:
        raise ValueError(
            f"cache_duration must be at most {MAX_CACHE_DURATION}, but was {configuration.cache_duration}."
        )
    _validate_positive_duration("request_timeout", configuration.request_timeout)


def _validate_positive_duration(name: str, value: timedelta) -> None:
    # Callers without a type checker may pass a number of seconds instead.
    if not isinstance(value, timedelta):
        raise TypeError(f"{name} must be a timedelta, but was {type(value).__name__}.")
    if value <= timedelta(0):
        raise ValueError(f"{name} must be positive, but was {value}.")
