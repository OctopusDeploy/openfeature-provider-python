"""The ``context-attribute-is-one-of`` condition."""

from dataclasses import dataclass

from octopus_openfeature_provider._v4.client_side_evaluation_context import (
    ClientSideEvaluationContext,
)
from octopus_openfeature_provider._v4.conditions.client_side_condition import (
    ClientSideCondition,
)
from octopus_openfeature_provider._v4.conditions.context_attributes import is_one_of


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextAttributeIsOneOfCondition(ClientSideCondition):
    """Matches when the context attribute ``key`` is one of ``values``.

    A missing attribute does not match.
    """

    key: str | None
    values: tuple[str | None, ...] | None

    def matches(self, context: ClientSideEvaluationContext) -> bool:
        return is_one_of(context, self.key, self.values)
