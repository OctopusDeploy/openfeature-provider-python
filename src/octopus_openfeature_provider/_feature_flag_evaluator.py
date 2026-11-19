"""Resolves flags from one evaluations response."""

import logging
import threading
from typing import Self

from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import FlagNotFoundError
from openfeature.flag_evaluation import FlagResolutionDetails

from octopus_openfeature_provider._evaluation_response import EvaluationResponse
from octopus_openfeature_provider._v4.server_side_evaluation import ServerSideEvaluation

_logger = logging.getLogger(__name__)

FLAG_NOT_FOUND_MESSAGE = "The slug provided did not match any of your Octopus Feature Flags. Please double check your slug and try again."


class FeatureFlagEvaluator:
    def __init__(self, evaluation_response: EvaluationResponse) -> None:
        self._evaluation_response = evaluation_response

        # Keyed case-insensitively. setdefault keeps the first flag for a slug.
        self._evaluations_by_slug: dict[str, ServerSideEvaluation] = {}
        for evaluation in evaluation_response.evaluations:
            self._evaluations_by_slug.setdefault(evaluation.slug.lower(), evaluation)

        self._warned_slugs: set[str] = set()
        self._warned_slugs_lock = threading.Lock()

    @classmethod
    def empty(cls) -> Self:
        return cls(EvaluationResponse(evaluations=(), content_hash=b""))

    @property
    def content_hash(self) -> bytes:
        return self._evaluation_response.content_hash

    def find_evaluation_by_slug(self, slug: str) -> ServerSideEvaluation | None:
        return self._evaluations_by_slug.get(slug.lower())

    def evaluate(
        self, slug: str, context: EvaluationContext | None
    ) -> FlagResolutionDetails[bool]:
        evaluation = self.find_evaluation_by_slug(slug)

        if evaluation is None:
            self._warn_once(slug)
            raise FlagNotFoundError(FLAG_NOT_FOUND_MESSAGE)

        return evaluation.evaluate(context)

    def _warn_once(self, slug: str) -> None:
        key = slug.lower()
        with self._warned_slugs_lock:
            if key in self._warned_slugs:
                return
            self._warned_slugs.add(key)

        # Logged outside the lock, so slow log handlers don't hold it.
        _logger.warning(
            "The slug %s did not match any of your Octopus Feature Flags. Please double check your slug and try again.",
            slug,
        )
