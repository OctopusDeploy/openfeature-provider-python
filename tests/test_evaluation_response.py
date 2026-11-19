import pytest
from openfeature.exception import ErrorCode, ParseError

from octopus_openfeature_provider._evaluation_response import parse_manifest
from octopus_openfeature_provider._v4.server_side_evaluation import (
    ServerSideEvaluation,
)

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
def test_a_body_that_is_not_a_json_array_raises_a_parse_error(
    body: str | bytes, expected_problem: str
) -> None:
    with pytest.raises(ParseError) as raised:
        parse_manifest(body, CONTENT_HASH)

    assert raised.value.error_code == ErrorCode.PARSE_ERROR
    assert raised.value.error_message == expected_problem
