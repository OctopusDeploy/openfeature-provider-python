from pathlib import Path

import pytest
from api_surface import analyse_api_surface

_FIXTURES = Path(__file__).with_name("api_surface_fixtures")


def test_renders_exports_by_their_public_path() -> None:
    surface = analyse_api_surface("clean_package", _FIXTURES)

    assert surface.text == (
        "class Widget:\n"
        "    size: int = 1\n"
        "    def resize(\n"
        "        self,\n"
        "        size: int,\n"
        "    ) -> clean_package.Widget\n"
        "\n"
        "def combine(\n"
        "    first: clean_package.Widget,\n"
        "    /,\n"
        "    second: int,\n"
        "    *rest: int,\n"
        "    flag: bool = False,\n"
        "    **options: str,\n"
        ") -> collections.abc.Sequence[clean_package.Widget]\n"
    )
    assert surface.leaks == []


def test_reports_types_consumers_cannot_import() -> None:
    surface = analyse_api_surface("leaky_package", _FIXTURES)

    assert surface.leaks == [
        "Gadget base class: leaky_package._hidden.HiddenBase",
        "Gadget.part type: leaky_package._hidden.Hidden",
        "Gadget.use parameter value: leaky_package._hidden.Hidden",
        "Gadget.use return type: leaky_package._hidden.HiddenNumber",
        "Gadget.measure return type: _collections_abc.Sized",
        "build return type: leaky_package._hidden.Hidden",
    ]


def test_requires_the_package_to_define_all() -> None:
    with pytest.raises(ValueError, match="must define __all__"):
        analyse_api_surface("package_without_all", _FIXTURES)
