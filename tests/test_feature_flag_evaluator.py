import logging

import pytest
from openfeature.exception import ErrorCode, FlagNotFoundError, ParseError

from octopus_openfeature_provider._evaluation_response import parse_manifest
from octopus_openfeature_provider._feature_flag_evaluator import (
    FLAG_NOT_FOUND_MESSAGE,
    FeatureFlagEvaluator,
)

LOGGER = "octopus_openfeature_provider"

MANIFEST = """
[
    { "slug": "enabled-feature", "value": true, "reason": "The flag is enabled for this environment." },
    { "slug": "disabled-feature", "value": false, "reason": "The flag is disabled for this environment." }
]
"""


def evaluator_for(manifest: str) -> FeatureFlagEvaluator:
    return FeatureFlagEvaluator(parse_manifest(manifest, b"\x01\x02\x03\x04"))


def warnings_in(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.levelno == logging.WARNING]


# Finding flags


@pytest.mark.parametrize(
    ("slug", "value", "reason"),
    [
        ("enabled-feature", True, "The flag is enabled for this environment."),
        ("disabled-feature", False, "The flag is disabled for this environment."),
    ],
)
def test_returns_the_server_value_and_reason(
    slug: str, value: bool, reason: str
) -> None:
    result = evaluator_for(MANIFEST).evaluate(slug, None)

    assert result.value is value
    assert result.reason == reason
    assert result.error_code is None


def test_slug_lookup_ignores_case() -> None:
    result = evaluator_for(MANIFEST).evaluate("Enabled-Feature", None)

    assert result.value is True


def test_when_slugs_differ_only_in_case_the_first_flag_wins() -> None:
    evaluator = evaluator_for(
        """
        [
            { "slug": "my-feature", "value": true, "reason": "First." },
            { "slug": "MY-FEATURE", "value": false, "reason": "Second." }
        ]
        """
    )

    result = evaluator.evaluate("My-Feature", None)

    assert result.value is True
    assert result.reason == "First."


def test_a_malformed_flag_raises_a_parse_error_without_affecting_the_others() -> None:
    evaluator = evaluator_for(
        """
        [
            { "slug": "malformed-feature", "value": "yes" },
            { "slug": "well-formed-feature", "value": true, "reason": "Enabled." }
        ]
        """
    )

    with pytest.raises(ParseError) as raised:
        evaluator.evaluate("malformed-feature", None)
    assert raised.value.error_code == ErrorCode.PARSE_ERROR

    assert evaluator.evaluate("well-formed-feature", None).value is True


# Missing or malformed flags


def test_a_missing_flag_raises_flag_not_found() -> None:
    evaluator = evaluator_for(MANIFEST)

    with pytest.raises(FlagNotFoundError) as raised:
        evaluator.evaluate("missing-feature", None)

    assert raised.value.error_code == ErrorCode.FLAG_NOT_FOUND
    assert raised.value.error_message == FLAG_NOT_FOUND_MESSAGE


def test_a_slug_that_is_not_a_slug_raises_flag_not_found() -> None:
    evaluator = evaluator_for(
        '[ { "slug": "this-is-clearly-not-a-slug", "value": true, "reason": "Enabled." } ]'
    )

    with pytest.raises(FlagNotFoundError):
        evaluator.evaluate("This is clearly not a slug!", None)


def test_a_missing_slug_is_warned_about_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    evaluator = evaluator_for(MANIFEST)

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        for slug in ["missing-feature", "Missing-Feature", "MISSING-FEATURE"]:
            with pytest.raises(FlagNotFoundError):
                evaluator.evaluate(slug, None)

    assert len(warnings_in(caplog)) == 1


def test_each_missing_slug_is_warned_about(caplog: pytest.LogCaptureFixture) -> None:
    evaluator = evaluator_for(MANIFEST)

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        for slug in ["first-missing-feature", "second-missing-feature"]:
            with pytest.raises(FlagNotFoundError):
                evaluator.evaluate(slug, None)

    assert len(warnings_in(caplog)) == 2


def test_a_new_evaluator_warns_again(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        for evaluator in [evaluator_for(MANIFEST), evaluator_for(MANIFEST)]:
            with pytest.raises(FlagNotFoundError):
                evaluator.evaluate("missing-feature", None)

    assert len(warnings_in(caplog)) == 2


# Content hash


def test_content_hash_comes_from_the_response() -> None:
    assert evaluator_for(MANIFEST).content_hash == b"\x01\x02\x03\x04"


def test_an_empty_evaluator_has_no_flags_and_an_empty_content_hash() -> None:
    evaluator = FeatureFlagEvaluator.empty()

    assert evaluator.content_hash == b""
    with pytest.raises(FlagNotFoundError):
        evaluator.evaluate("enabled-feature", None)
