from collections.abc import Sequence
from enum import Enum
from typing import Generic, Literal, TypeVar, overload

from fixture_library import Base

T = TypeVar("T")

Number = int | float


class Colour(Enum):
    RED = 1


class Widget(Base):
    size: int = 1

    class Part:
        pass

    def resize(self, size: int) -> "Widget":
        return self

    def part(self) -> "Widget.Part":
        return Widget.Part()

    def _hidden(self) -> None:
        pass


class Box(Generic[T]):
    def get(self) -> T:
        raise NotImplementedError


def combine(
    first: Widget, /, second: int, *rest: int, flag: bool = False, **options: str
) -> Sequence[Widget]:
    return [first]


@overload
def convert(value: int) -> int: ...


@overload
def convert(value: str) -> str: ...


def convert(value: int | str) -> int | str:
    return value


async def paint(colour: Literal[Colour.RED]) -> None:
    pass
