import pytest
from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import ParseError

from octopus_openfeature_provider._v4.parse_server_side_evaluation import (
    InvalidManifestError,
    parse_evaluation,
    parse_manifest,
)
from octopus_openfeature_provider._v4.server_side_evaluation import (
    ServerSideEvaluation,
)

RULE = {
    "name": "Beta ring",
    "conditions": [
        {"type": "context-attribute-is-one-of", "key": "ring", "values": ["beta"]}
    ],
}

CONTEXT = EvaluationContext(targeting_key="user-1", attributes={"ring": "beta"})


def parse(entry: object) -> ServerSideEvaluation:
    evaluation = parse_evaluation(entry)
    assert evaluation is not None
    return evaluation


# A single flag


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


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        pytest.param(
            {"slug": "my-feature", "value": "true", "reason": "Enabled."},
            ServerSideEvaluation(
                slug="my-feature",
                value=None,
                reason="Enabled.",
                evaluation_key=None,
                rules=None,
            ),
            id="value-is-a-string",
        ),
        pytest.param(
            {"slug": "my-feature", "value": 1, "reason": "Enabled."},
            ServerSideEvaluation(
                slug="my-feature",
                value=None,
                reason="Enabled.",
                evaluation_key=None,
                rules=None,
            ),
            id="value-is-a-number",
        ),
        pytest.param(
            {"slug": "my-feature", "value": True, "reason": 42},
            ServerSideEvaluation(
                slug="my-feature",
                value=True,
                reason=None,
                evaluation_key=None,
                rules=None,
            ),
            id="reason-is-a-number",
        ),
        pytest.param(
            {"slug": "my-feature", "evaluationKey": 42, "rules": [RULE]},
            ServerSideEvaluation(
                slug="my-feature",
                value=None,
                reason=None,
                evaluation_key=None,
                rules=(RULE,),
            ),
            id="evaluation-key-is-a-number",
        ),
        pytest.param(
            {"slug": "my-feature", "evaluationKey": "evaluation-key", "rules": {}},
            ServerSideEvaluation(
                slug="my-feature",
                value=None,
                reason=None,
                evaluation_key="evaluation-key",
                rules=None,
            ),
            id="rules-is-an-object",
        ),
    ],
)
def test_a_field_of_the_wrong_type_is_treated_as_absent(
    entry: dict[str, object], expected: ServerSideEvaluation
) -> None:
    evaluation = parse(entry)

    assert evaluation == expected
    with pytest.raises(ParseError):
        evaluation.evaluate(CONTEXT)


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


# The whole manifest


CONTENT_HASH = b"\x01\x02\x03\x04"


def test_parses_every_flag_in_order() -> None:
    response = parse_manifest(
        """
        [
            { "slug": "resolved-feature", "value": false, "reason": "The flag is disabled for this environment." },
            { "slug": "deferred-feature", "evaluationKey": "evaluation-key", "rules": [ { "name": "Rule 1" } ] }
        ]
        """,
        CONTENT_HASH,
    )

    assert [evaluation.slug for evaluation in response.evaluations] == [
        "resolved-feature",
        "deferred-feature",
    ]
    assert response.evaluations[0] == ServerSideEvaluation(
        slug="resolved-feature",
        value=False,
        reason="The flag is disabled for this environment.",
        evaluation_key=None,
        rules=None,
    )


def test_keeps_the_content_hash() -> None:
    response = parse_manifest("[]", CONTENT_HASH)

    assert response.content_hash == CONTENT_HASH


def test_a_malformed_flag_does_not_affect_the_rest_of_the_manifest() -> None:
    response = parse_manifest(
        """
        [
            { "slug": "wrongly-typed-feature", "value": "yes" },
            { "slug": "shapeless-feature" },
            { "slug": "well-formed-feature", "value": true, "reason": "The flag is enabled for this environment." }
        ]
        """,
        CONTENT_HASH,
    )

    wrongly_typed, shapeless, well_formed = response.evaluations

    with pytest.raises(ParseError):
        wrongly_typed.evaluate(None)

    with pytest.raises(ParseError):
        shapeless.evaluate(None)

    result = well_formed.evaluate(None)
    assert result.value is True
    assert result.reason == "The flag is enabled for this environment."
    assert result.error_code is None


def test_skips_entries_without_a_string_slug() -> None:
    response = parse_manifest(
        """
        [
            null,
            {},
            { "slug": 42, "value": true, "reason": "Enabled." },
            { "slug": "my-feature", "value": true, "reason": "Enabled." }
        ]
        """,
        CONTENT_HASH,
    )

    assert [evaluation.slug for evaluation in response.evaluations] == ["my-feature"]


def test_keeps_flags_with_duplicate_slugs() -> None:
    # Choosing between them is the evaluator's job.
    response = parse_manifest(
        """
        [
            { "slug": "my-feature", "value": true, "reason": "First." },
            { "slug": "MY-FEATURE", "value": false, "reason": "Second." }
        ]
        """,
        CONTENT_HASH,
    )

    assert len(response.evaluations) == 2


@pytest.mark.parametrize(
    ("body", "expected_problem"),
    [
        pytest.param("[ { ", "The manifest is not valid JSON.", id="truncated"),
        pytest.param("null", "The manifest is not a list of flags.", id="null"),
        pytest.param(
            '{ "slug": "my-feature", "value": true, "reason": "Enabled." }',
            "The manifest is not a list of flags.",
            id="single-object",
        ),
    ],
)
def test_a_body_that_is_not_a_json_array_raises_invalid_manifest_error(
    body: str | bytes, expected_problem: str
) -> None:
    with pytest.raises(InvalidManifestError) as raised:
        parse_manifest(body, CONTENT_HASH)

    assert str(raised.value) == expected_problem
