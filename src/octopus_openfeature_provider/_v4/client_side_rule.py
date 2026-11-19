"""A named rule the provider evaluates on the client side."""

from dataclasses import dataclass

from openfeature.exception import ParseError

from octopus_openfeature_provider._v4.client_side_evaluation_context import (
    ClientSideEvaluationContext,
)
from octopus_openfeature_provider._v4.conditions.client_side_condition import (
    ClientSideCondition,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ClientSideRule:
    """Matches when every one of its conditions matches.

    A field that was missing or of the wrong type in the response is None, and a
    condition that wasn't a JSON object is None in ``conditions``.
    """

    name: str | None
    conditions: tuple[ClientSideCondition | None, ...] | None

    def matches(self, context: ClientSideEvaluationContext) -> bool:
        # The server only defers a named rule carrying at least one condition, so
        # anything else is a response it could not have sent.
        if self.name is None:
            raise ParseError("A rule has no name.")

        if not self.conditions:
            raise ParseError(f"Rule '{self.name}' has no conditions.")

        for condition in self.conditions:
            if condition is None:
                raise ParseError(f"Rule '{self.name}' has a missing condition.")

            if not condition.matches(context):
                return False

        return True
