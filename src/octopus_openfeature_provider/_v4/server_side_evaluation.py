"""A single flag from the v4 evaluations endpoint.

A flag comes in one of two shapes: resolved by the server (``value`` and
``reason``), or deferred to the client (``evaluationKey`` and ``rules``).
"""

from dataclasses import dataclass
from typing import TypeAlias

from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import GeneralError, ParseError
from openfeature.flag_evaluation import FlagResolutionDetails


@dataclass(frozen=True, slots=True, kw_only=True)
class ServerSideEvaluation:
    slug: str
    value: bool | None
    reason: str | None
    evaluation_key: str | None
    # TODO: Hold ClientSideRule in this tuple once client-side rules are
    # implemented.
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


@dataclass(frozen=True, slots=True)
class MalformedEvaluation:
    """A flag with a slug but a field of the wrong JSON type.

    Every evaluation fails with ``ParseError``.
    """

    slug: str
    problem: str

    def evaluate(
        self, context: EvaluationContext | None
    ) -> FlagResolutionDetails[bool]:
        raise ParseError(self.problem)


Evaluation: TypeAlias = ServerSideEvaluation | MalformedEvaluation


def parse_evaluation(entry: object) -> Evaluation | None:
    """Parse one entry of the manifest array."""
    if not isinstance(entry, dict):
        return None

    slug = entry.get("slug")
    if not isinstance(slug, str):
        return None

    value = entry.get("value")
    if value is not None and not isinstance(value, bool):
        return MalformedEvaluation(slug, "The flag's value is not a boolean.")

    reason = entry.get("reason")
    if reason is not None and not isinstance(reason, str):
        return MalformedEvaluation(slug, "The flag's reason is not a string.")

    evaluation_key = entry.get("evaluationKey")
    if evaluation_key is not None and not isinstance(evaluation_key, str):
        return MalformedEvaluation(slug, "The flag's evaluation key is not a string.")

    rules = entry.get("rules")
    if rules is not None and not isinstance(rules, list):
        return MalformedEvaluation(slug, "The flag's rules are not a list.")

    return ServerSideEvaluation(
        slug=slug,
        value=value,
        reason=reason,
        evaluation_key=evaluation_key,
        rules=tuple(rules) if rules is not None else None,
    )
