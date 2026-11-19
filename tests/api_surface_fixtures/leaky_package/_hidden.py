from collections.abc import Callable
from typing import TypeVar

_F = TypeVar("_F", bound=Callable[..., object])


class Hidden:
    pass


class HiddenBase:
    def reveal(self) -> Hidden:
        return Hidden()


HiddenNumber = int

DEFAULT = Hidden()


def hidden_decorator(function: _F) -> _F:
    return function
