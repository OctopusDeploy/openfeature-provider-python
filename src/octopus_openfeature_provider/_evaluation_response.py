"""The parsed body of a v4 evaluations response, with its content hash."""

import json
from dataclasses import dataclass

from openfeature.exception import ParseError

from octopus_openfeature_provider._v4.server_side_evaluation import (
    ServerSideEvaluation,
    parse_evaluation,
)


@dataclass(frozen=True)
class EvaluationResponse:
    evaluations: tuple[ServerSideEvaluation, ...]
    content_hash: bytes


def parse_manifest(body: str | bytes, content_hash: bytes) -> EvaluationResponse:
    """Parse the body of an evaluations response."""
    try:
        entries: object = json.loads(body)
    except ValueError as e:
        raise ParseError("The manifest is not valid JSON.") from e

    if not isinstance(entries, list):
        raise ParseError("The manifest is not a list of flags.")

    evaluations = tuple(
        evaluation
        for entry in entries
        if (evaluation := parse_evaluation(entry)) is not None
    )

    return EvaluationResponse(evaluations=evaluations, content_hash=content_hash)
