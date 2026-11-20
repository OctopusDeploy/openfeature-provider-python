"""The ``type`` discriminators of the client-side conditions.

These mirror the values in the evaluations response, so they must not drift from
the server.
"""

CONTEXT_ATTRIBUTE_IS_NOT_ONE_OF = "context-attribute-is-not-one-of"
CONTEXT_ATTRIBUTE_IS_ONE_OF = "context-attribute-is-one-of"
PERCENTAGE_BY_CONTEXT = "percentage-by-context"
