"""A single flag from the v4 evaluations endpoint.

A flag comes in one of two shapes: resolved by the server (``value`` and
``reason``), or deferred to the client (``evaluationKey`` and ``rules``).
"""

from dataclasses import dataclass

from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import GeneralError, ParseError
from openfeature.flag_evaluation import FlagResolutionDetails


@dataclass(frozen=True)
class ServerSideEvaluation:
    slug: str
    value: bool | None
    reason: str | None
    evaluation_key: str | None
    # TODO: Replace with ClientSideRule in following tuple when client-side rules is implemented.
    rules: tuple[object, ...] | None

    def evaluate(
        self, context: EvaluationContext | None
    ) -> FlagResolutionDetails[bool]:
        """Resolve the flag.

        Raises ``ParseError`` for a flag in neither shape, which the OpenFeature
        SDK turns into the caller's default value.
        """
        if self.value is not None:
            if self.reason is None:
                raise ParseError("The flag has a value but has no reason.")

            if self.evaluation_key is not None or self.rules is not None:
                raise ParseError(
                    "The flag has both a server-resolved value and client-side rules."
                )

            return FlagResolutionDetails(value=self.value, reason=self.reason)

        if self.rules is None:
            raise ParseError("The flag has neither a value nor rules.")

        if self.evaluation_key is None:
            raise ParseError("The flag defers to the client but has no evaluation key.")

        if not self.rules:
            raise ParseError("The flag defers to the client with no rules.")

        # TODO: rule evaluation to be implemented.
        raise GeneralError("Client-side rules are not supported yet.")

