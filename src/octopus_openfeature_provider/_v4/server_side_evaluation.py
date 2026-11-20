"""A single flag from the v4 evaluations endpoint.

A flag comes in one of two shapes: resolved by the server (``value`` and
``reason``), or deferred to the client (``evaluationKey`` and ``rules``).
"""

from dataclasses import dataclass
from typing import cast

from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import ParseError
from openfeature.flag_evaluation import FlagResolutionDetails

from octopus_openfeature_provider._v4 import evaluation_reasons
from octopus_openfeature_provider._v4.client_side_evaluation_context import (
    ClientSideEvaluationContext,
)
from octopus_openfeature_provider._v4.client_side_rule import ClientSideRule


@dataclass(frozen=True, slots=True, kw_only=True)
class ServerSideEvaluation:
    slug: str
    value: bool | None
    reason: str | None
    evaluation_key: str | None
    # A rule that wasn't a JSON object is None.
    rules: tuple[ClientSideRule | None, ...] | None

    def evaluate(
        self, context: EvaluationContext | None
    ) -> FlagResolutionDetails[bool]:
        """Resolve the flag, evaluating the client-side rules if the server left
        any.

        The rules are OR'd and the first match wins. A flag deferred to the
        client is enabled when a rule matches, and disabled when none do.

        Raises ``ParseError`` for a flag in neither shape, or with a rule or
        condition the server could not have sent, which the OpenFeature SDK turns
        into the caller's default value.
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

        rule_context = ClientSideEvaluationContext(self.evaluation_key, context)

        for rule in self.rules:
            if rule is None:
                raise ParseError("The flag has a missing rule.")

            if rule.matches(rule_context):
                # matches raises for a rule without a name, so it has one here.
                name = cast("str", rule.name)
                return FlagResolutionDetails(
                    value=True, reason=evaluation_reasons.matched_rule(name)
                )

        return FlagResolutionDetails(
            value=False, reason=evaluation_reasons.DID_NOT_MATCH_ANY_RULES
        )
