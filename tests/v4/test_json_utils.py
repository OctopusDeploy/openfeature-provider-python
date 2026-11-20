import pytest

from octopus_openfeature_provider._v4._json_utils import (
    as_bool,
    as_dict,
    as_int,
    as_list,
    as_str,
)


@pytest.mark.parametrize("value", ["", "my-feature"])
def test_as_str_returns_a_string(value: str) -> None:
    assert as_str(value) == value


@pytest.mark.parametrize("value", [None, 42, True, [], {}])
def test_as_str_reads_any_other_type_as_absent(value: object) -> None:
    assert as_str(value) is None


@pytest.mark.parametrize("value", [True, False])
def test_as_bool_returns_a_boolean(value: bool) -> None:
    assert as_bool(value) is value


@pytest.mark.parametrize("value", [None, 0, 1, "true", [], {}])
def test_as_bool_reads_any_other_type_as_absent(value: object) -> None:
    assert as_bool(value) is None


@pytest.mark.parametrize("value", [0, 50, -1, 101])
def test_as_int_returns_an_integer(value: int) -> None:
    assert as_int(value) == value


@pytest.mark.parametrize("value", [None, True, False, 50.0, "50", [], {}])
def test_as_int_reads_any_other_type_as_absent(value: object) -> None:
    assert as_int(value) is None


@pytest.mark.parametrize("value", [[], [1, "two", None]])
def test_as_list_returns_a_list(value: list[object]) -> None:
    assert as_list(value) is value


@pytest.mark.parametrize("value", [None, "[]", {}, (1, 2)])
def test_as_list_reads_any_other_type_as_absent(value: object) -> None:
    assert as_list(value) is None


@pytest.mark.parametrize("value", [{}, {"slug": "my-feature"}])
def test_as_dict_returns_a_dict(value: dict[str, object]) -> None:
    assert as_dict(value) is value


@pytest.mark.parametrize("value", [None, "{}", [], [{"slug": "my-feature"}]])
def test_as_dict_reads_any_other_type_as_absent(value: object) -> None:
    assert as_dict(value) is None
