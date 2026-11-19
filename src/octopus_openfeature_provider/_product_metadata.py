import re
from dataclasses import dataclass

# Anything outside the RFC 9110 tchar set: https://www.rfc-editor.org/rfc/rfc9110.html#name-tokens
_UNSUPPORTED_CHARACTERS = re.compile(r"[^a-zA-Z0-9!#$%&'*+\-.^_`|~]")


def _clean(value: str) -> str:
    return _UNSUPPORTED_CHARACTERS.sub("", value)


@dataclass(frozen=True, init=False)
class ProductMetadata:
    """Describes the product using the provider.

    The feature flags service receives it with each request, for telemetry.
    Characters that aren't valid in an HTTP token are removed from the name
    and version.

    Raises:
        ValueError: If the name, or a supplied version, has no valid
            characters left after cleaning.
    """

    name: str
    version: str | None

    def __init__(self, name: str, version: str | None = None) -> None:
        cleaned_name = _clean(name)
        if not cleaned_name:
            raise ValueError(
                "Product name must contain at least one valid token character."
            )

        cleaned_version = None if version is None else _clean(version)
        if cleaned_version == "":
            raise ValueError(
                "Product version must contain at least one valid token character."
            )

        # The dataclass is frozen, so the fields can only be set this way.
        object.__setattr__(self, "name", cleaned_name)
        object.__setattr__(self, "version", cleaned_version)
