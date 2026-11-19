"""The parsed body of a v4 evaluations response, with its content hash."""

from dataclasses import dataclass

from octopus_openfeature_provider._v4.server_side_evaluation import (
    ServerSideEvaluation,
)


@dataclass(frozen=True)
class EvaluationResponse:
    evaluations: tuple[ServerSideEvaluation, ...]
    content_hash: bytes
