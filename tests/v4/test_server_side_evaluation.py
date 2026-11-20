import pytest
from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import ErrorCode, ParseError

from octopus_openfeature_provider._v4.client_side_rule import ClientSideRule
from octopus_openfeature_provider._v4.conditions.context_attribute_is_one_of_condition import (
    ContextAttributeIsOneOfCondition,
)
from octopus_openfeature_provider._v4.server_side_evaluation import (
    ServerSideEvaluation,
)

RULE = ClientSideRule(
    name="Beta ring",
    conditions=(ContextAttributeIsOneOfCondition(key="ring", values=("beta",)),),
)

# Satisfies RULE, so a flag that failed to raise would visibly turn on.
CONTEXT = EvaluationContext(targeting_key="user-1", attributes={"ring": "beta"})


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
    ],
)
def test_a_malformed_flag_raises_a_parse_error(
    evaluation: ServerSideEvaluation, expected_problem: str
) -> None:
    with pytest.raises(ParseError) as raised:
        evaluation.evaluate(CONTEXT)

    assert raised.value.error_code == ErrorCode.PARSE_ERROR
    assert raised.value.error_message == expected_problem
