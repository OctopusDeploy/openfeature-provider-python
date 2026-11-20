"""What a flag's rules and conditions are evaluated against."""

from dataclasses import dataclass

from openfeature.evaluation_context import EvaluationContext


@dataclass(frozen=True, slots=True)
class ClientSideEvaluationContext:
    # The key percentage-by-context buckets against.
    evaluation_key: str
    # The caller's context, or None if they supplied none.
    open_feature_context: EvaluationContext | None
