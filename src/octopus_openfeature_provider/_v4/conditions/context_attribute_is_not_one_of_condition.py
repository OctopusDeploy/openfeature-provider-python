"""The ``context-attribute-is-not-one-of`` condition."""

from dataclasses import dataclass

from octopus_openfeature_provider._v4.client_side_evaluation_context import (
    ClientSideEvaluationContext,
)
from octopus_openfeature_provider._v4.conditions.client_side_condition import (
    ClientSideCondition,
)
from octopus_openfeature_provider._v4.conditions.context_attributes import is_one_of


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextAttributeIsNotOneOfCondition(ClientSideCondition):
    """Matches when the context attribute ``key`` is not one of ``values``.

    The exact negation of ``context-attribute-is-one-of``, so a missing attribute
    matches.
    """

    key: str | None
    values: tuple[str | None, ...] | None

    def matches(self, context: ClientSideEvaluationContext) -> bool:
        return not is_one_of(context, self.key, self.values)
