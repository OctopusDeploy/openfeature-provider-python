from collections.abc import Sequence


class Widget:
    size: int = 1

    def resize(self, size: int) -> "Widget":
        return self

    def _hidden(self) -> None:
        pass


def combine(
    first: Widget, /, second: int, *rest: int, flag: bool = False, **options: str
) -> Sequence[Widget]:
    return [first]
