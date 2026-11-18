import copy
from collections.abc import Mapping, Sequence
from datetime import timedelta

from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import ErrorCode, FlagNotFoundError
from openfeature.flag_evaluation import FlagResolutionDetails, FlagValueType, Reason
from openfeature.provider import AbstractProvider, Metadata

from octopus_openfeature_provider._configuration import OctopusFeatureConfiguration

_FLAG_NOT_FOUND_MESSAGE = "The slug provided did not match any of your Octopus Feature Flags. Please double check your slug and try again."


class OctopusFeatureProvider(AbstractProvider):
    """An OpenFeature provider for Octopus feature flags.

    Register it with the OpenFeature SDK, for example with
    `openfeature.api.set_provider`. Octopus feature flags are booleans only.

    Raises:
        ValueError: If the configuration's client identifier is empty, or its
            `cache_duration` or `request_timeout` isn't positive.
        TypeError: If `cache_duration` or `request_timeout` isn't a
            `timedelta`.
    """

    def __init__(self, configuration: OctopusFeatureConfiguration) -> None:
        super().__init__()
        # A shallow copy, so the provider is unaffected by later changes to the
        # configuration but still uses the caller's HTTP client.
        self._configuration = copy.copy(configuration)
        _validate(self._configuration)

    def get_metadata(self) -> Metadata:
        return Metadata(name="octopus-python-provider")

    def resolve_boolean_details(
        self,
        flag_key: str,
        default_value: bool,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[bool]:
        # A stub until manifest fetching lands. Every flag is missing.
        return FlagResolutionDetails(
            value=default_value,
            reason=Reason.ERROR,
            error_code=ErrorCode.FLAG_NOT_FOUND,
            error_message=_FLAG_NOT_FOUND_MESSAGE,
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
        # As in .NET, a flag that exists gets TypeMismatchError, and any other
        # gets FlagNotFoundError. There are no flags until manifest fetching
        # lands, so for now every flag is missing.
        return FlagNotFoundError(_FLAG_NOT_FOUND_MESSAGE)


def _validate(configuration: OctopusFeatureConfiguration) -> None:
    if not configuration.client_identifier.strip():
        raise ValueError("client_identifier must not be empty.")
    _validate_positive_duration("cache_duration", configuration.cache_duration)
    _validate_positive_duration("request_timeout", configuration.request_timeout)


def _validate_positive_duration(name: str, value: timedelta) -> None:
    # Callers without a type checker may pass a number of seconds instead.
    if not isinstance(value, timedelta):
        raise TypeError(f"{name} must be a timedelta, but was {type(value).__name__}.")
    if value <= timedelta(0):
        raise ValueError(f"{name} must be positive, but was {value}.")
