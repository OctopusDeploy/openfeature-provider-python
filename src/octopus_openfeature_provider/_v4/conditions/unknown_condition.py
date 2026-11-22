"""A condition whose ``type`` this version of the provider doesn't recognise."""

from dataclasses import dataclass

from openfeature.exception import ParseError

from octopus_openfeature_provider._v4.client_side_evaluation_context import (
    ClientSideEvaluationContext,
)
from octopus_openfeature_provider._v4.conditions.client_side_condition import (
    ClientSideCondition,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class UnknownCondition(ClientSideCondition):
    """Never matches, so a newer server's capability is treated as "not met" by
    an older provider rather than failing the flag."""

    # The unrecognised discriminator, or None if it was missing or not a string.
    type: str | None

    def matches(self, context: ClientSideEvaluationContext) -> bool:
        # No server version emits a condition without a type, so unlike an
        # unrecognised type this is a response that could not have been sent.
        if self.type is None:
            raise ParseError("A condition is missing a type.")

        return False
