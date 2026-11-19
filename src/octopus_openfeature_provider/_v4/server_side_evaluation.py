"""A single flag from the v4 evaluations endpoint.

A flag comes in one of two shapes: resolved by the server (``value`` and
``reason``), or deferred to the client (``evaluationKey`` and ``rules``).
"""

from dataclasses import dataclass

from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import GeneralError, ParseError
from openfeature.flag_evaluation import FlagResolutionDetails

from octopus_openfeature_provider._v4._json_utils import (
    as_bool,
    as_dict,
    as_list,
    as_str,
)


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


def parse_evaluation(raw: object) -> ServerSideEvaluation | None:
    """Parse one entry of the manifest array."""
    entry = as_dict(raw)
    if entry is None:
        return None

    slug = as_str(entry.get("slug"))
    if slug is None:
        return None

    # TODO: we probably want to parse the client side rules here later instead of plain list.
    rules = as_list(entry.get("rules"))

    return ServerSideEvaluation(
        slug=slug,
        value=as_bool(entry.get("value")),
        reason=as_str(entry.get("reason")),
        evaluation_key=as_str(entry.get("evaluationKey")),
        rules=tuple(rules) if rules is not None else None,
    )
