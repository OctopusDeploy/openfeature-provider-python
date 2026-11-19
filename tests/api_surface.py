"""Renders a package's public API as text, and finds the private types it exposes.

The package is read from source with griffe rather than imported, so the result
is the same on every Python version and keeps type aliases as they're written.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import griffe


@dataclass(frozen=True)
class ApiSurface:
    """The rendered public API of a package, and the private types it exposes.

    Attributes:
        text: Every name in the package's `__all__`, with its signature,
            attributes, base classes and decorators. Names are written as the
            path a consumer imports them from.
        leaks: Each place the public API exposes a type consumers can't
            import, as `<where>: <type path>`. A type from the package is
            importable only when the package's `__all__` exports it, and a type
            from anywhere else only when no part of its path is private.
    """

    text: str
    leaks: list[str]


def analyse_api_surface(package_name: str, search_path: Path) -> ApiSurface:
    package = griffe.load(
        package_name,
        search_paths=[search_path],
        allow_inspection=False,
        resolve_aliases=True,
    )
    if not isinstance(package, griffe.Module):
        raise TypeError(f"{package_name} isn't a package.")
    return _Analyser(package).analyse()


class _Analyser:
    def __init__(self, package: griffe.Module) -> None:
        if package.exports is None:
            raise ValueError(f"{package.path} must define __all__.")
        self._package = package
        self._exports = sorted(str(name) for name in package.exports)
        # Maps each exported object's definition, and its public path, to its
        # public path.
        self._public_paths: dict[str, str] = {}
        for name in self._exports:
            public_path = f"{package.path}.{name}"
            definition = package[name]
            if definition.is_alias:
                definition = definition.final_target
            self._public_paths[definition.path] = public_path
            self._public_paths[public_path] = public_path
        self._lines: list[str] = []
        self._leaks: list[str] = []

    def analyse(self) -> ApiSurface:
        for index, name in enumerate(self._exports):
            if index:
                self._lines.append("")
            member = self._package[name]
            if member.is_alias:
                member = member.final_target
            self._render_member(name, member, indent="")
        return ApiSurface(text="\n".join(self._lines) + "\n", leaks=self._leaks)

    def _render_member(self, name: str, member: griffe.Object, indent: str) -> None:
        if isinstance(member, griffe.Class):
            self._render_class(name, member, indent)
        elif isinstance(member, griffe.Function):
            self._render_function(name, member, indent)
        elif isinstance(member, griffe.Attribute):
            self._render_attribute(name, member, indent)
        else:
            raise TypeError(
                f"Can't render {member.path}, a {member.kind.value}, in the public API."
            )

    def _render_class(self, name: str, cls: griffe.Class, indent: str) -> None:
        where = self._where(cls)
        self._render_decorators(cls.decorators, indent)
        bases = [self._type(base, f"{where} base class") for base in cls.bases]
        self._lines.append(
            f"{indent}class {name}({', '.join(bases)}):"
            if bases
            else f"{indent}class {name}:"
        )
        members = [
            (member_name, member)
            for member_name, member in cls.members.items()
            if isinstance(member, griffe.Object) and member.is_public
        ]
        if not members:
            self._lines.append(f"{indent}    ...")
        for member_name, member in members:
            self._render_member(member_name, member, indent + "    ")

    def _render_function(
        self, name: str, function: griffe.Function, indent: str
    ) -> None:
        where = self._where(function)
        self._render_decorators(function.decorators, indent)
        parameters = self._render_parameters(function, where)
        returns = (
            ""
            if function.returns is None
            else f" -> {self._type(function.returns, f'{where} return type')}"
        )
        if len(parameters) <= 1:
            self._lines.append(f"{indent}def {name}({''.join(parameters)}){returns}")
            return
        self._lines.append(f"{indent}def {name}(")
        self._lines.extend(f"{indent}    {parameter}," for parameter in parameters)
        self._lines.append(f"{indent}){returns}")

    def _render_parameters(self, function: griffe.Function, where: str) -> list[str]:
        rendered: list[str] = []
        kinds = [parameter.kind for parameter in function.parameters]
        for index, parameter in enumerate(function.parameters):
            if (
                parameter.kind is griffe.ParameterKind.keyword_only
                and griffe.ParameterKind.var_positional not in kinds
                and kinds.index(griffe.ParameterKind.keyword_only) == index
            ):
                rendered.append("*")

            text = parameter.name
            variadic = parameter.kind in {
                griffe.ParameterKind.var_positional,
                griffe.ParameterKind.var_keyword,
            }
            if parameter.kind is griffe.ParameterKind.var_positional:
                text = f"*{text}"
            elif parameter.kind is griffe.ParameterKind.var_keyword:
                text = f"**{text}"
            if parameter.annotation is not None:
                annotation = self._type(
                    parameter.annotation, f"{where} parameter {parameter.name}"
                )
                text = f"{text}: {annotation}"
            # griffe gives *args and **kwargs the defaults () and {}.
            if parameter.default is not None and not variadic:
                separator = " = " if parameter.annotation is not None else "="
                text = f"{text}{separator}{self._value(parameter.default)}"
            rendered.append(text)

            if (
                parameter.kind is griffe.ParameterKind.positional_only
                and griffe.ParameterKind.positional_only not in kinds[index + 1 :]
            ):
                rendered.append("/")
        return rendered

    def _render_attribute(
        self, name: str, attribute: griffe.Attribute, indent: str
    ) -> None:
        text = f"{indent}{name}"
        if attribute.annotation is not None:
            annotation = self._type(
                attribute.annotation, f"{self._where(attribute)} type"
            )
            text = f"{text}: {annotation}"
        # Module constants such as __version__ change with every release, so
        # only class attributes, like dataclass field defaults, show a value.
        if attribute.value is not None and isinstance(attribute.parent, griffe.Class):
            text = f"{text} = {self._value(attribute.value)}"
        self._lines.append(text)

    def _render_decorators(
        self, decorators: Iterable[griffe.Decorator], indent: str
    ) -> None:
        self._lines.extend(
            f"{indent}@{self._value(decorator.value)}" for decorator in decorators
        )

    def _type(self, expression: str | griffe.Expr, where: str) -> str:
        """Renders a type, and records any private type it refers to."""

        def check(path: str) -> None:
            if not self._is_importable(path):
                self._leaks.append(f"{where}: {path}")

        return self._render(expression, check)

    def _value(self, expression: str | griffe.Expr) -> str:
        return self._render(expression, lambda _: None)

    def _render(
        self, expression: str | griffe.Expr, on_name: Callable[[str], None]
    ) -> str:
        if isinstance(expression, str):
            return expression
        # An attribute such as httpx.Client is a single name.
        if isinstance(expression, griffe.ExprAttribute | griffe.ExprName):
            path = expression.canonical_path
            on_name(path)
            return self._public_paths.get(path, path)
        return "".join(
            self._render(part, on_name) for part in expression.iterate(flat=False)
        )

    def _is_importable(self, path: str) -> bool:
        if path in self._public_paths:
            return True
        if path == self._package.path or path.startswith(f"{self._package.path}."):
            return False
        return not any(
            part.startswith("_") and not part.startswith("__")
            for part in path.split(".")
        )

    def _where(self, member: griffe.Object) -> str:
        # The path relative to the package's public names, for example
        # OctopusFeatureProvider.resolve_boolean_details.
        parts: list[str] = []
        current: griffe.Object | None = member
        while current is not None and not isinstance(current, griffe.Module):
            parts.append(current.name)
            current = current.parent
        return ".".join(reversed(parts))
