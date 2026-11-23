"""Runs the shared specification fixtures through the real provider and the SDK.

Each case is served from the fake feature flags server, so it covers the HTTP
decode, the SDK's context merge and error handling, and the provider's boolean
wiring as well as the evaluator.
"""

from collections.abc import Iterator

import pytest
from fake_feature_flags_server import FakeFeatureFlagsServer, configuration_for
from openfeature import api
from openfeature.flag_evaluation import FlagEvaluationDetails
from specification_fixtures import (
    FixtureCase,
    parametrize_fixture_cases,
    run_fixture_case,
)

from octopus_openfeature_provider import OctopusFeatureProvider


@pytest.fixture(autouse=True)
def reset_the_sdk() -> Iterator[None]:
    yield
    api.shutdown()


@parametrize_fixture_cases()
def test_specification_fixture(
    feature_flags_server: FakeFeatureFlagsServer, case: FixtureCase
) -> None:
    def evaluate(case: FixtureCase) -> FlagEvaluationDetails[bool]:
        feature_flags_server.evaluations.body = case.response
        api.set_provider_and_wait(
            OctopusFeatureProvider(configuration_for(feature_flags_server))
        )
        return api.get_client().get_boolean_details(
            case.slug, case.default_value, case.evaluation_context()
        )

    run_fixture_case(case, evaluate)
