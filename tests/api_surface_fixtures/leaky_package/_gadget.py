from _collections_abc import Sized
from typing import overload

from leaky_package._hidden import (
    DEFAULT,
    Hidden,
    HiddenBase,
    HiddenNumber,
    hidden_decorator,
)

HiddenAlias = Hidden


class Gadget(HiddenBase):
    part: Hidden

    def use(self, value: Hidden | None) -> list[HiddenNumber]:
        return []

    def measure(self) -> Sized:
        return []


@hidden_decorator
def build(source: object = DEFAULT) -> Hidden:
    return Hidden()


@overload
def pick(value: int) -> int: ...


@overload
def pick(value: Hidden) -> Hidden: ...


def pick(value: object) -> object:
    return value
