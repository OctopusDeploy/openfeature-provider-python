"""Reading a response from the v4 evaluations endpoint."""

import json

from octopus_openfeature_provider._evaluation_response import EvaluationResponse
from octopus_openfeature_provider._v4._json_utils import (
    as_bool,
    as_dict,
    as_list,
    as_str,
)
from octopus_openfeature_provider._v4.server_side_evaluation import (
    ServerSideEvaluation,
)


class InvalidManifestError(ValueError):
    """The body of an evaluations response is not a JSON array."""


def parse_manifest(body: str | bytes, content_hash: bytes) -> EvaluationResponse:
    """Parse the body of an evaluations response.

    Raises:
        InvalidManifestError: If the body is not a JSON array.
    """
    try:
        entries: object = json.loads(body)
    except ValueError as e:
        raise InvalidManifestError("The manifest is not valid JSON.") from e

    entries_list = as_list(entries)
    if entries_list is None:
        raise InvalidManifestError("The manifest is not a list of flags.")

    evaluations = tuple(
        evaluation
        for entry in entries_list
        if (evaluation := parse_evaluation(entry)) is not None
    )

    return EvaluationResponse(evaluations=evaluations, content_hash=content_hash)


def parse_evaluation(raw: object) -> ServerSideEvaluation | None:
    """Parse one entry of the manifest array."""
    entry = as_dict(raw)
    if entry is None:
        return None

    slug = as_str(entry.get("slug"))
    if slug is None:
        return None

    # TODO: we probably want to parse the client side rules here later instead of plain list.
    rules = as_list(entry.get("rules"))

    return ServerSideEvaluation(
        slug=slug,
        value=as_bool(entry.get("value")),
        reason=as_str(entry.get("reason")),
        evaluation_key=as_str(entry.get("evaluationKey")),
        rules=tuple(rules) if rules is not None else None,
    )
