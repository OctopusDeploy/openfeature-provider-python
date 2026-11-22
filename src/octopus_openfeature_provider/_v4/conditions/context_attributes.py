"""The attribute lookup shared by both attribute conditions."""

from openfeature.exception import ParseError

from octopus_openfeature_provider._v4.client_side_evaluation_context import (
    ClientSideEvaluationContext,
)


def is_one_of(
    context: ClientSideEvaluationContext,
    key: str | None,
    values: tuple[str | None, ...] | None,
) -> bool:
    """Whether the context holds an attribute named ``key`` with one of ``values``.

    Keys and values compare case-insensitively, and a non-string attribute counts
    as absent. The SDK passes the context un-flattened, so an attribute can be an
    int, bool, float, datetime, sequence or mapping. Every attribute whose key
    matches is checked, not just the first, as a context can hold several case
    variants of one key.

    Raises:
        ParseError: If the condition is missing its key or values.
    """
    if key is None:
        raise ParseError("A condition is missing a key.")

    if not values:
        raise ParseError("A condition is missing values.")

    if any(value is None for value in values):
        raise ParseError("A condition is missing a value.")

    open_feature_context = context.open_feature_context
    if open_feature_context is None:
        return False

    # The providers agree on ASCII. Beyond it, str.upper expands characters such
    # as "ß" to "SS" as the browser provider does, where .NET and Java don't.
    upper_key = key.upper()
    upper_values = {value.upper() for value in values if value is not None}

    return any(
        isinstance(attribute_key, str)
        and attribute_key.upper() == upper_key
        and isinstance(attribute, str)
        and attribute.upper() in upper_values
        for attribute_key, attribute in open_feature_context.attributes.items()
    )
