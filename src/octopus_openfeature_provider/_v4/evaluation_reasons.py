"""Reasons returned alongside a client-side evaluation.

Both match the strings the Feature Flags service produces server-side, so a flag
reads the same whichever side resolved it.
"""


def matched_rule(rule_name: str) -> str:
    return f"Matched rule '{rule_name}'."


DID_NOT_MATCH_ANY_RULES = "Did not match any rules."
