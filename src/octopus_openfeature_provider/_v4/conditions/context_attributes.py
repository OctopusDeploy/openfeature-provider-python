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

    upper_key = _ordinal_upper(key)
    upper_values = {_ordinal_upper(value) for value in values if value is not None}

    return any(
        isinstance(attribute_key, str)
        and _ordinal_upper(attribute_key) == upper_key
        and isinstance(attribute, str)
        and _ordinal_upper(attribute) in upper_values
        for attribute_key, attribute in open_feature_context.attributes.items()
    )


def _ordinal_upper(text: str) -> str:
    """``text`` uppercased one character at a time, so two strings compare as
    .NET's ``OrdinalIgnoreCase`` and Java's ``equalsIgnoreCase`` compare them.

    ``str.upper`` applies Unicode's full case mappings, some of which expand a
    character, so "Straße" would equal "STRASSE" where .NET and Java say it
    doesn't. A character that expands is kept as it is instead. That agrees with
    .NET on ASCII and on expansions such as "ß" and "ﬁ", but not on the few Greek
    letters with an iota subscript, which .NET maps to their titlecase form.
    """
    upper = text.upper()

    # Nothing expanded, so every character mapped one to one.
    if len(upper) == len(text):
        return upper

    return "".join(
        upper_char if len(upper_char := char.upper()) == 1 else char for char in text
    )
