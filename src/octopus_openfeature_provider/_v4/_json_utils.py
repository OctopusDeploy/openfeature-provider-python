"""Reading values out of a parsed v4 evaluations response.

A value of the wrong JSON type reads as absent, so a malformed flag is reported
when it is evaluated and costs only itself.
"""


def as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def as_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def as_int(value: object) -> int | None:
    # bool is a subclass of int, but true isn't a JSON integer. A float such as
    # 50.0 isn't either, as .NET would reject it.
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def as_list(value: object) -> list[object] | None:
    return value if isinstance(value, list) else None


def as_dict(value: object) -> dict[str, object] | None:
    # JSON objects always have string keys.
    return value if isinstance(value, dict) else None
