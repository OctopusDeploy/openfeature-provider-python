"""Client-side evaluation cases the specification fixtures don't cover.

The fixtures exercise missing and null fields, but not fields of the wrong type,
or context attributes that aren't strings.
"""

from datetime import UTC, datetime

import pytest
from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import ErrorCode, ParseError

from octopus_openfeature_provider._v4.parse_server_side_evaluation import (
    parse_evaluation,
)
from octopus_openfeature_provider._v4.server_side_evaluation import (
    ServerSideEvaluation,
)


def deferred_flag(*rules: object) -> ServerSideEvaluation:
    evaluation = parse_evaluation(
        {"slug": "my-feature", "evaluationKey": "evaluation-key", "rules": list(rules)}
    )
    assert evaluation is not None
    return evaluation


def rule_with(*conditions: object) -> dict[str, object]:
    return {"name": "Beta ring", "conditions": list(conditions)}


def is_one_of(values: object) -> dict[str, object]:
    return {"type": "context-attribute-is-one-of", "key": "ring", "values": values}


CONTEXT = EvaluationContext(targeting_key="user-1", attributes={"ring": "beta"})


# Fields of the wrong type


@pytest.mark.parametrize(
    ("rule", "expected_problem"),
    [
        pytest.param(42, "The flag has a missing rule.", id="rule-is-a-number"),
        pytest.param(
            [rule_with(is_one_of(["beta"]))],
            "The flag has a missing rule.",
            id="rule-is-an-array",
        ),
        pytest.param(
            {"name": 42, "conditions": [is_one_of(["beta"])]},
            "A rule has no name.",
            id="rule-name-is-a-number",
        ),
        pytest.param(
            {"name": "Beta ring", "conditions": is_one_of(["beta"])},
            "Rule 'Beta ring' has no conditions.",
            id="conditions-is-an-object",
        ),
        pytest.param(
            rule_with("context-attribute-is-one-of"),
            "Rule 'Beta ring' has a missing condition.",
            id="condition-is-a-string",
        ),
        pytest.param(
            rule_with({"type": 42, "key": "ring", "values": ["beta"]}),
            "A condition is missing a type.",
            id="condition-type-is-a-number",
        ),
        pytest.param(
            rule_with(
                {"type": "context-attribute-is-one-of", "key": 42, "values": ["beta"]}
            ),
            "A condition is missing a key.",
            id="key-is-a-number",
        ),
        pytest.param(
            rule_with(is_one_of("beta")),
            "A condition is missing values.",
            id="values-is-a-string",
        ),
        pytest.param(
            rule_with(is_one_of(["beta", 42])),
            "A condition is missing a value.",
            id="a-value-is-a-number",
        ),
        pytest.param(
            rule_with({"type": "percentage-by-context", "percentage": "100"}),
            "A condition is missing a percentage value.",
            id="percentage-is-a-string",
        ),
        pytest.param(
            rule_with({"type": "percentage-by-context", "percentage": 100.0}),
            "A condition is missing a percentage value.",
            id="percentage-is-a-float",
        ),
        pytest.param(
            rule_with({"type": "percentage-by-context", "percentage": True}),
            "A condition is missing a percentage value.",
            id="percentage-is-a-bool",
        ),
    ],
)
def test_a_field_of_the_wrong_type_raises_a_parse_error(
    rule: object, expected_problem: str
) -> None:
    with pytest.raises(ParseError) as raised:
        deferred_flag(rule).evaluate(CONTEXT)

    assert raised.value.error_code == ErrorCode.PARSE_ERROR
    assert raised.value.error_message == expected_problem


# Context attributes that aren't strings


@pytest.mark.parametrize(
    ("attribute", "values"),
    [
        pytest.param(5, ["5"], id="int"),
        pytest.param(True, ["true", "True"], id="bool"),
        pytest.param(1.5, ["1.5"], id="float"),
        pytest.param(
            datetime(2026, 1, 1, tzinfo=UTC),
            ["2026-01-01T00:00:00Z", "2026-01-01 00:00:00+00:00"],
            id="datetime",
        ),
        pytest.param(["beta"], ["beta"], id="sequence"),
        pytest.param({"ring": "beta"}, ["beta"], id="mapping"),
    ],
)
def test_a_context_attribute_that_is_not_a_string_counts_as_absent(
    attribute: object, values: list[str]
) -> None:
    # Constructed without the type checker, as an untyped caller can.
    context = EvaluationContext(
        targeting_key="user-1",
        attributes={"ring": attribute},  # type: ignore[dict-item]
    )

    is_one_of_result = deferred_flag(rule_with(is_one_of(values))).evaluate(context)
    is_not_one_of_result = deferred_flag(
        rule_with(
            {"type": "context-attribute-is-not-one-of", "key": "ring", "values": values}
        )
    ).evaluate(context)

    assert is_one_of_result.value is False
    assert is_not_one_of_result.value is True


def test_a_non_string_attribute_does_not_hide_a_matching_case_variant() -> None:
    context = EvaluationContext(attributes={"ring": 5, "RING": "beta"})

    result = deferred_flag(rule_with(is_one_of(["beta"]))).evaluate(context)

    assert result.value is True
    assert result.reason == "Matched rule 'Beta ring'."


@pytest.mark.parametrize("percentage", [99, 100])
def test_a_targeting_key_that_is_not_a_string_counts_as_missing(
    percentage: int,
) -> None:
    context = EvaluationContext(targeting_key=42)  # type: ignore[arg-type]

    result = deferred_flag(
        rule_with({"type": "percentage-by-context", "percentage": percentage})
    ).evaluate(context)

    assert result.value is (percentage == 100)
