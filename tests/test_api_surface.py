from pathlib import Path

import pytest
from api_surface import analyse_api_surface

_FIXTURES = Path(__file__).with_name("api_surface_fixtures")


def test_renders_exports_by_their_public_path() -> None:
    surface = analyse_api_surface("clean_package", _FIXTURES)

    assert surface.text == (
        "class Box(typing.Generic[T]):\n"
        "    def get(self) -> T\n"
        "\n"
        "class Colour(enum.Enum):\n"
        "    RED = 1\n"
        "\n"
        "Number = int | float\n"
        "\n"
        "Sequence = collections.abc.Sequence\n"
        "\n"
        "class Widget(fixture_library.Base):\n"
        "    size: int = 1\n"
        "    class Part:\n"
        "        ...\n"
        "    def resize(\n"
        "        self,\n"
        "        size: int,\n"
        "    ) -> clean_package.Widget\n"
        "    def part(self) -> clean_package.Widget.Part\n"
        "    # Inherited from fixture_library.Base\n"
        "    def describe(self) -> str\n"
        "\n"
        "def combine(\n"
        "    first: clean_package.Widget,\n"
        "    /,\n"
        "    second: int,\n"
        "    *rest: int,\n"
        "    flag: bool = False,\n"
        "    **options: str,\n"
        ") -> collections.abc.Sequence[clean_package.Widget]\n"
        "\n"
        "@typing.overload\n"
        "def convert(value: int) -> int\n"
        "@typing.overload\n"
        "def convert(value: str) -> str\n"
        "def convert(value: int | str) -> int | str\n"
        "\n"
        "async def paint(colour: typing.Literal[clean_package.Colour.RED]) -> None\n"
    )
    assert surface.leaks == []


def test_reports_private_names_consumers_cannot_import() -> None:
    surface = analyse_api_surface("leaky_package", _FIXTURES)

    assert surface.leaks == [
        "Gadget base class: leaky_package._hidden.HiddenBase",
        "Gadget.part type: leaky_package._hidden.Hidden",
        "Gadget.use parameter value: leaky_package._hidden.Hidden",
        "Gadget.use return type: leaky_package._hidden.HiddenNumber",
        "Gadget.measure return type: _collections_abc.Sized",
        "Gadget.reveal return type: leaky_package._hidden.Hidden",
        "HiddenAlias value: leaky_package._hidden.Hidden",
        "build decorator: leaky_package._hidden.hidden_decorator",
        "build parameter source default: leaky_package._hidden.DEFAULT",
        "build return type: leaky_package._hidden.Hidden",
        "pick parameter value: leaky_package._hidden.Hidden",
        "pick return type: leaky_package._hidden.Hidden",
    ]


def test_requires_the_package_to_define_all() -> None:
    with pytest.raises(ValueError, match="must define __all__"):
        analyse_api_surface("package_without_all", _FIXTURES)
