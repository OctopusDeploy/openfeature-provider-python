"""The ``percentage-by-context`` condition."""

from dataclasses import dataclass

from openfeature.exception import ParseError

from octopus_openfeature_provider._v4.client_side_evaluation_context import (
    ClientSideEvaluationContext,
)
from octopus_openfeature_provider._v4.conditions import percentage_rollout
from octopus_openfeature_provider._v4.conditions.client_side_condition import (
    ClientSideCondition,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class PercentageByContextCondition(ClientSideCondition):
    """Matches when the targeting key falls within the ``percentage``% rollout."""

    # 0 to 100. None when it was missing or not an integer, which stays
    # distinguishable from an explicit 0, a legitimate "nobody".
    percentage: int | None

    def matches(self, context: ClientSideEvaluationContext) -> bool:
        percentage = self.percentage
        if percentage is None:
            raise ParseError("A condition is missing a percentage value.")

        # Rejected rather than clamped: reading 101 as "everyone" would turn a
        # flag on off the back of a bad payload.
        if not 0 <= percentage <= 100:
            raise ParseError(f"A condition has a percentage of {percentage}.")

        open_feature_context = context.open_feature_context
        targeting_key = (
            open_feature_context.targeting_key if open_feature_context else None
        )

        # Nothing to bucket, so only a full rollout matches, as the server treats
        # an untenanted caller. Checked with isinstance as well, since a caller
        # without a type checker can pass a targeting key that isn't a str.
        if not targeting_key or not isinstance(targeting_key, str):
            return percentage >= 100

        return percentage_rollout.includes(
            context.evaluation_key, targeting_key, percentage
        )
