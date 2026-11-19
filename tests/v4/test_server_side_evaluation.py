import pytest
from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import ErrorCode, GeneralError, ParseError

from octopus_openfeature_provider._v4.server_side_evaluation import (
    Evaluation,
    MalformedEvaluation,
    ServerSideEvaluation,
    parse_evaluation,
)

RULE = {
    "name": "Beta ring",
    "conditions": [
        {"type": "context-attribute-is-one-of", "key": "ring", "values": ["beta"]}
    ],
}

# Satisfies RULE, so a flag that failed to raise would visibly turn on.
CONTEXT = EvaluationContext(targeting_key="user-1", attributes={"ring": "beta"})


def parse(entry: object) -> Evaluation:
    evaluation = parse_evaluation(entry)
    assert evaluation is not None
    return evaluation


# Parsing


def test_server_resolved_flag_parses_slug_value_and_reason() -> None:
    entry = {"slug": "my-feature", "value": True, "reason": "Enabled."}

    assert parse(entry) == ServerSideEvaluation(
        slug="my-feature",
        value=True,
        reason="Enabled.",
        evaluation_key=None,
        rules=None,
    )


def test_deferred_flag_parses_evaluation_key_and_rules() -> None:
    entry = {"slug": "my-feature", "evaluationKey": "evaluation-key", "rules": [RULE]}

    assert parse(entry) == ServerSideEvaluation(
        slug="my-feature",
        value=None,
        reason=None,
        evaluation_key="evaluation-key",
        rules=(RULE,),
    )


def test_null_fields_are_treated_as_absent() -> None:
    entry = {
        "slug": "my-feature",
        "value": True,
        "reason": "Enabled.",
        "evaluationKey": None,
        "rules": None,
    }

    assert parse(entry) == ServerSideEvaluation(
        slug="my-feature",
        value=True,
        reason="Enabled.",
        evaluation_key=None,
        rules=None,
    )


@pytest.mark.parametrize(
    ("entry", "expected_problem"),
    [
        pytest.param(
            {"slug": "my-feature", "value": "true", "reason": "Enabled."},
            "The flag's value is not a boolean.",
            id="value-is-a-string",
        ),
        pytest.param(
            {"slug": "my-feature", "value": 1, "reason": "Enabled."},
            "The flag's value is not a boolean.",
            id="value-is-a-number",
        ),
        pytest.param(
            {"slug": "my-feature", "value": True, "reason": 42},
            "The flag's reason is not a string.",
            id="reason-is-a-number",
        ),
        pytest.param(
            {"slug": "my-feature", "evaluationKey": 42, "rules": [RULE]},
            "The flag's evaluation key is not a string.",
            id="evaluation-key-is-a-number",
        ),
        pytest.param(
            {"slug": "my-feature", "evaluationKey": "evaluation-key", "rules": {}},
            "The flag's rules are not a list.",
            id="rules-is-an-object",
        ),
    ],
)
def test_a_field_of_the_wrong_type_gives_a_malformed_evaluation(
    entry: dict[str, object], expected_problem: str
) -> None:
    assert parse(entry) == MalformedEvaluation("my-feature", expected_problem)


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param(None, id="null"),
        pytest.param("my-feature", id="string"),
        pytest.param([], id="array"),
        pytest.param({"value": True, "reason": "Enabled."}, id="no-slug"),
        pytest.param({"slug": None, "value": True}, id="null-slug"),
        pytest.param({"slug": 42, "value": True}, id="number-slug"),
    ],
)
def test_an_entry_without_a_string_slug_is_skipped(entry: object) -> None:
    assert parse_evaluation(entry) is None


# Evaluating


@pytest.mark.parametrize("value", [True, False])
def test_server_resolved_flag_returns_the_server_value_and_reason(value: bool) -> None:
    evaluation = ServerSideEvaluation(
        slug="my-feature",
        value=value,
        reason="the server said so",
        evaluation_key=None,
        rules=None,
    )

    result = evaluation.evaluate(CONTEXT)

    assert result.value is value
    assert result.reason == "the server said so"
    assert result.error_code is None


@pytest.mark.parametrize(
    ("evaluation", "expected_problem"),
    [
        pytest.param(
            ServerSideEvaluation(
                slug="my-feature",
                value=True,
                reason=None,
                evaluation_key=None,
                rules=None,
            ),
            "The flag has a value but has no reason.",
            id="value-without-reason",
        ),
        pytest.param(
            ServerSideEvaluation(
                slug="my-feature",
                value=None,
                reason=None,
                evaluation_key=None,
                rules=None,
            ),
            "The flag has neither a value nor rules.",
            id="neither-shape",
        ),
        pytest.param(
            ServerSideEvaluation(
                slug="my-feature",
                value=True,
                reason="Enabled.",
                evaluation_key="evaluation-key",
                rules=(RULE,),
            ),
            "The flag has both a server-resolved value and client-side rules.",
            id="both-shapes",
        ),
        pytest.param(
            ServerSideEvaluation(
                slug="my-feature",
                value=None,
                reason=None,
                evaluation_key=None,
                rules=(RULE,),
            ),
            "The flag defers to the client but has no evaluation key.",
            id="deferred-without-evaluation-key",
        ),
        pytest.param(
            ServerSideEvaluation(
                slug="my-feature",
                value=None,
                reason=None,
                evaluation_key="evaluation-key",
                rules=(),
            ),
            "The flag defers to the client with no rules.",
            id="deferred-with-no-rules",
        ),
        pytest.param(
            MalformedEvaluation("my-feature", "The flag's value is not a boolean."),
            "The flag's value is not a boolean.",
            id="malformed-evaluation",
        ),
    ],
)
def test_a_malformed_flag_raises_a_parse_error(
    evaluation: Evaluation, expected_problem: str
) -> None:
    with pytest.raises(ParseError) as raised:
        evaluation.evaluate(CONTEXT)

    assert raised.value.error_code == ErrorCode.PARSE_ERROR
    assert raised.value.error_message == expected_problem
