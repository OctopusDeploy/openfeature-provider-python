"""Reading a response from the v4 evaluations endpoint."""

import json

from octopus_openfeature_provider._evaluation_response import EvaluationResponse
from octopus_openfeature_provider._v4._json_utils import (
    as_bool,
    as_dict,
    as_int,
    as_list,
    as_str,
)
from octopus_openfeature_provider._v4.client_side_rule import ClientSideRule
from octopus_openfeature_provider._v4.conditions import condition_type_names
from octopus_openfeature_provider._v4.conditions.client_side_condition import (
    ClientSideCondition,
)
from octopus_openfeature_provider._v4.conditions.context_attribute_is_not_one_of_condition import (
    ContextAttributeIsNotOneOfCondition,
)
from octopus_openfeature_provider._v4.conditions.context_attribute_is_one_of_condition import (
    ContextAttributeIsOneOfCondition,
)
from octopus_openfeature_provider._v4.conditions.percentage_by_context_condition import (
    PercentageByContextCondition,
)
from octopus_openfeature_provider._v4.conditions.unknown_condition import (
    UnknownCondition,
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

    rules = as_list(entry.get("rules"))

    return ServerSideEvaluation(
        slug=slug,
        value=as_bool(entry.get("value")),
        reason=as_str(entry.get("reason")),
        evaluation_key=as_str(entry.get("evaluationKey")),
        rules=tuple(parse_rule(rule) for rule in rules) if rules is not None else None,
    )


def parse_rule(raw: object) -> ClientSideRule | None:
    """Parse one client-side rule, or None if it isn't a JSON object."""
    rule = as_dict(raw)
    if rule is None:
        return None

    conditions = as_list(rule.get("conditions"))

    return ClientSideRule(
        name=as_str(rule.get("name")),
        conditions=tuple(parse_condition(condition) for condition in conditions)
        if conditions is not None
        else None,
    )


def parse_condition(raw: object) -> ClientSideCondition | None:
    """Parse one condition of a client-side rule, or None if it isn't a JSON
    object.

    An unrecognised or missing ``type`` parses to ``UnknownCondition`` rather
    than failing, so a condition type introduced by a newer server degrades
    safely on an older provider.
    """
    condition = as_dict(raw)
    if condition is None:
        return None

    match condition_type := as_str(condition.get("type")):
        case condition_type_names.PERCENTAGE_BY_CONTEXT:
            return PercentageByContextCondition(
                percentage=as_int(condition.get("percentage"))
            )
        case condition_type_names.CONTEXT_ATTRIBUTE_IS_ONE_OF:
            return ContextAttributeIsOneOfCondition(
                key=as_str(condition.get("key")),
                values=_parse_values(condition.get("values")),
            )
        case condition_type_names.CONTEXT_ATTRIBUTE_IS_NOT_ONE_OF:
            return ContextAttributeIsNotOneOfCondition(
                key=as_str(condition.get("key")),
                values=_parse_values(condition.get("values")),
            )
        case _:
            return UnknownCondition(type=condition_type)


def _parse_values(raw: object) -> tuple[str | None, ...] | None:
    values = as_list(raw)
    return tuple(as_str(value) for value in values) if values is not None else None
