"""Loads the shared specification fixtures and checks results against them.

Each file in `specification/Fixtures/` is one simulated evaluations response
plus the cases evaluated against it. The fixtures are shared with every other
Octopus provider, so passing them shows this provider evaluates flags the same
way. How a case is evaluated is left to the caller, so loading, naming and
assertions stay separate from it.
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import ErrorCode
from openfeature.flag_evaluation import FlagEvaluationDetails

FIXTURES_DIRECTORY = Path(__file__).parent.parent / "specification" / "Fixtures"

# The OpenFeature targeting key, not a custom attribute.
TARGETING_KEY = "targetingKey"


@dataclass(frozen=True)
class FixtureCase:
    file_name: str
    description: str
    # The fixture's simulated evaluations response, as JSON.
    response: str
    slug: str
    default_value: bool
    # A null attribute is present with a None value, not absent.
    context: Mapping[str, str | None] | None
    expected_value: bool
    # None when the fixture doesn't state a reason.
    expected_reason: str | None
    # None when the evaluation returns no error.
    expected_error_code: ErrorCode | None

    @property
    def id(self) -> str:
        return f"{self.file_name} - {self.description}"

    def evaluation_context(self) -> EvaluationContext | None:
        if self.context is None:
            return None
        attributes = {
            key: value for key, value in self.context.items() if key != TARGETING_KEY
        }
        return EvaluationContext(
            targeting_key=self.context.get(TARGETING_KEY),
            # None isn't an EvaluationContextAttribute, but a fixture's null
            # attribute has to reach the provider as present with no value.
            attributes=cast(Any, attributes),
        )


def load_fixture_cases(directory: Path = FIXTURES_DIRECTORY) -> list[FixtureCase]:
    """Every case in every fixture file in directory.

    Raises:
        RuntimeError: If there are no fixture files, so a missing submodule
            fails the run rather than passing with nothing tested.
    """
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise RuntimeError(
            f"No specification fixtures found in {directory}. Initialise the "
            "submodule with: git submodule update --init"
        )
    return [case for path in paths for case in _load_fixture_file(path)]


def _load_fixture_file(path: Path) -> list[FixtureCase]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    response = json.dumps(fixture["response"])
    return [_case(path.name, response, case) for case in fixture["cases"]]


def _case(file_name: str, response: str, case: dict[str, Any]) -> FixtureCase:
    configuration = case["configuration"]
    expected = case["expected"]
    error_code = expected.get("errorCode")
    return FixtureCase(
        file_name=file_name,
        description=case["description"],
        response=response,
        slug=configuration["slug"],
        default_value=configuration["defaultValue"],
        context=configuration.get("context"),
        expected_value=expected["value"],
        expected_reason=expected.get("reason"),
        expected_error_code=None if error_code is None else ErrorCode(error_code),
    )


def parametrize_fixture_cases() -> pytest.MarkDecorator:
    """Parametrises a test's `case` argument with every fixture case, named
    `<fixture file> - <case description>`."""
    cases = load_fixture_cases()
    return pytest.mark.parametrize("case", cases, ids=[case.id for case in cases])


def run_fixture_case(
    case: FixtureCase,
    evaluate: Callable[[FixtureCase], FlagEvaluationDetails[bool]],
) -> None:
    """Evaluate case and assert the result matches what the fixture expects.

    The reason is only checked where the fixture states one.
    """
    details = evaluate(case)

    assert details.value is case.expected_value
    assert details.error_code == case.expected_error_code
    if case.expected_reason is not None:
        assert details.reason == case.expected_reason
