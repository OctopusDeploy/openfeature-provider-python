"""The base type for a condition of a client-side rule."""

from abc import ABC, abstractmethod

from octopus_openfeature_provider._v4.client_side_evaluation_context import (
    ClientSideEvaluationContext,
)


class ClientSideCondition(ABC):
    __slots__ = ()

    @abstractmethod
    def matches(self, context: ClientSideEvaluationContext) -> bool:
        """Whether this condition is met.

        A condition that did not arrive in a shape its type can evaluate raises
        ``ParseError`` rather than reading a value it was not sent.
        """
