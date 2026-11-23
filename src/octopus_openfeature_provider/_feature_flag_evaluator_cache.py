import logging

from octopus_openfeature_provider._feature_flag_api_client import FeatureFlagApiClient
from octopus_openfeature_provider._feature_flag_evaluator import FeatureFlagEvaluator

_logger = logging.getLogger(__name__)


class FeatureFlagEvaluatorCache:
    """Holds the evaluator the provider resolves flags against.

    Until a fetch succeeds it holds an empty evaluator, so every flag is
    missing.
    """

    def __init__(self, client: FeatureFlagApiClient) -> None:
        self._client = client
        self._evaluator = FeatureFlagEvaluator.empty()

    def get_evaluator(self) -> FeatureFlagEvaluator:
        return self._evaluator

    def initialize(self) -> None:
        """Fetch the evaluations. Never raises."""
        try:
            response = self._client.get_server_side_evaluations()
        except Exception:
            _logger.exception(
                "Failed to retrieve feature manifest during initialization. Falling back to no evaluations, defaults will be used during evaluation."
            )
            self._evaluator = FeatureFlagEvaluator.empty()
            return

        self._evaluator = (
            FeatureFlagEvaluator(response)
            if response is not None
            else FeatureFlagEvaluator.empty()
        )
