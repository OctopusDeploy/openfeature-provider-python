"""Renders a package's public API as text, and finds the private types it exposes.

The package is read from source with griffe rather than imported, so the result
is the same on every Python version and keeps type aliases as they're written.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

import griffe

# Calls that create a type variable. Consumers never import one, so a type
# variable is written as its bare name, wherever it's declared.
_TYPE_VARIABLE_FACTORIES = frozenset(
    f"{module}.{factory}"
    for module in ("typing", "typing_extensions")
    for factory in ("TypeVar", "ParamSpec", "TypeVarTuple")
)

_UNRESOLVABLE = (KeyError, griffe.AliasResolutionError, griffe.CyclicAliasError)


@dataclass(frozen=True)
class ApiSurface:
    """The rendered public API of a package, and the private names it exposes.

    Attributes:
        text: Every name in the package's `__all__`, with its signature,
            attributes, base classes, decorators and inherited members. Names
            are written as the path a consumer imports them from.
        leaks: Each place the public API refers to a name consumers can't
            import, in a type, default value, decorator or value, as
            `<where>: <path>`. A name from the package is importable only when
            the package's `__all__` exports it, or it's a public member of an
            export. A name from anywhere else is importable only when no part
            of its path is private.
    """

    text: str
    leaks: list[str]


def analyse_api_surface(package_name: str, search_path: Path) -> ApiSurface:
    # sys.path lets griffe find the libraries the package's classes inherit
    # from. Nothing else is loaded from it.
    loader = griffe.GriffeLoader(
        search_paths=[search_path, *sys.path], allow_inspection=False
    )
    package = loader.load(package_name)
    if not isinstance(package, griffe.Module):
        raise TypeError(f"{package_name} isn't a package.")
    # Only aliases between loaded modules are resolved, so a name imported
    # from elsewhere, such as the standard library, keeps the path it's
    # imported from.
    loader.resolve_aliases(external=False)
    _load_base_class_libraries(loader, package)
    return _Analyser(package).analyse()


def _load_base_class_libraries(
    loader: griffe.GriffeLoader, package: griffe.Module
) -> None:
    """Loads the third-party libraries the exported classes inherit from.

    Without them, members the package inherits from a library, such as the
    OpenFeature SDK, wouldn't be part of the API. The standard library isn't
    loaded, because its source differs between Python versions.
    """
    pending: list[griffe.Object | griffe.Alias] = [
        package[str(name)] for name in package.exports or []
    ]
    seen: set[str] = set()
    while pending:
        cls = pending.pop()
        if isinstance(cls, griffe.Alias):
            try:
                cls = cls.final_target
            except _UNRESOLVABLE:
                continue
        if not isinstance(cls, griffe.Class) or cls.path in seen:
            continue
        seen.add(cls.path)
        for base in cls.bases:
            path = base if isinstance(base, str) else base.canonical_path
            library = path.partition(".")[0]
            if (
                "." in path
                and library not in loader.modules_collection
                and library not in sys.stdlib_module_names
            ):
                try:
                    loader.load(library)
                except ImportError:
                    continue
                loader.resolve_aliases(external=False)
        pending.extend(cls.resolved_bases)


def _in(package_path: str, path: str) -> bool:
    return path == package_path or path.startswith(f"{package_path}.")


def _is_private(path: str) -> bool:
    return any(
        part.startswith("_") and not part.startswith("__") for part in path.split(".")
    )


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
            definition = self._export(name)
            if isinstance(definition, griffe.Object):
                self._public_paths[definition.path] = public_path
            self._public_paths[public_path] = public_path
        self._lines: list[str] = []
        self._leaks: list[str] = []

    def analyse(self) -> ApiSurface:
        for index, name in enumerate(self._exports):
            if index:
                self._lines.append("")
            definition = self._export(name)
            if isinstance(definition, str):
                # A name re-exported from another library.
                self._lines.append(f"{name} = {self._name(definition, name)}")
            else:
                self._render_member(name, definition, indent="", where=name)
        return ApiSurface(text="\n".join(self._lines) + "\n", leaks=self._leaks)

    def _export(self, name: str) -> griffe.Object | str:
        """The definition an export refers to, or its path in another library."""
        return self._follow(self._package[name])

    def _follow(self, member: griffe.Object | griffe.Alias) -> griffe.Object | str:
        """Follows aliases while they stay in the package.

        An alias that leaves the package gives the path it imports from, not
        where the other library defines it, which can be a private module.
        """
        while isinstance(member, griffe.Alias):
            if not _in(self._package.path, member.target_path):
                return member.target_path
            member = member.target
        return member

    def _render_member(
        self, name: str, member: griffe.Object, indent: str, where: str
    ) -> None:
        if isinstance(member, griffe.Class):
            self._render_class(name, member, indent, where)
        elif isinstance(member, griffe.Function):
            self._render_function(name, member, indent, where)
        elif isinstance(member, griffe.Attribute):
            self._render_attribute(name, member, indent, where)
        else:
            raise TypeError(
                f"Can't render {member.path}, a {member.kind.value}, in the public API."
            )

    def _render_class(
        self, name: str, cls: griffe.Class, indent: str, where: str
    ) -> None:
        self._render_decorators(cls.decorators, indent, where)
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
        # Grouped by the class that defines them, base classes first.
        inherited: dict[str, list[tuple[str, griffe.Object]]] = {}
        for member_name, alias in cls.inherited_members.items():
            member = alias.target
            if (
                isinstance(member, griffe.Object)
                and member.parent is not None
                and alias.is_public
            ):
                # A private base class is already recorded as a leak.
                origin = self._public_path(member.parent.path) or member.parent.path
                inherited.setdefault(origin, []).append((member_name, member))
        if not members and not inherited:
            self._lines.append(f"{indent}    ...")
        for member_name, member in members:
            self._render_member(
                member_name, member, indent + "    ", f"{where}.{member_name}"
            )
        for origin, origin_members in inherited.items():
            self._lines.append(f"{indent}    # Inherited from {origin}")
            for member_name, member in origin_members:
                self._render_member(
                    member_name, member, indent + "    ", f"{where}.{member_name}"
                )

    def _render_function(
        self, name: str, function: griffe.Function, indent: str, where: str
    ) -> None:
        # Each @overload signature, then the implementation's.
        for signature in [*(function.overloads or []), function]:
            self._render_signature(name, signature, indent, where)

    def _render_signature(
        self, name: str, function: griffe.Function, indent: str, where: str
    ) -> None:
        self._render_decorators(function.decorators, indent, where)
        parameters = self._render_parameters(function, where)
        returns = (
            ""
            if function.returns is None
            else f" -> {self._type(function.returns, f'{where} return type')}"
        )
        definition = (
            f"{indent}{'async ' if 'async' in function.labels else ''}def {name}"
        )
        if len(parameters) <= 1:
            self._lines.append(f"{definition}({''.join(parameters)}){returns}")
            return
        self._lines.append(f"{definition}(")
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
                default = self._type(
                    parameter.default, f"{where} parameter {parameter.name} default"
                )
                text = f"{text}{separator}{default}"
            rendered.append(text)

            if (
                parameter.kind is griffe.ParameterKind.positional_only
                and griffe.ParameterKind.positional_only not in kinds[index + 1 :]
            ):
                rendered.append("/")
        return rendered

    def _render_attribute(
        self, name: str, attribute: griffe.Attribute, indent: str, where: str
    ) -> None:
        text = f"{indent}{name}"
        if attribute.annotation is not None:
            text = f"{text}: {self._type(attribute.annotation, f'{where} type')}"
        # Module metadata such as __version__ changes with every release, so
        # it shows no value. Everything else does, including type aliases.
        is_metadata = (
            isinstance(attribute.parent, griffe.Module)
            and name.startswith("__")
            and name.endswith("__")
        )
        if attribute.value is not None and not is_metadata:
            text = f"{text} = {self._type(attribute.value, f'{where} value')}"
        self._lines.append(text)

    def _render_decorators(
        self, decorators: list[griffe.Decorator], indent: str, where: str
    ) -> None:
        self._lines.extend(
            f"{indent}@{self._type(decorator.value, f'{where} decorator')}"
            for decorator in decorators
        )

    def _type(self, expression: str | griffe.Expr, where: str) -> str:
        """Renders an expression, and records any private name it refers to."""
        if isinstance(expression, str):
            return expression
        # An attribute such as httpx.Client is a single name.
        if isinstance(expression, griffe.ExprAttribute | griffe.ExprName):
            return self._name(expression.canonical_path, where)
        return "".join(
            self._type(part, where) for part in expression.iterate(flat=False)
        )

    def _name(self, path: str, where: str) -> str:
        """Renders a name by its public path, and records it if it's private."""
        definition = self._definition(path)
        if isinstance(definition, str):
            path = definition
        else:
            if _is_type_variable(definition):
                return definition.name
            path = definition.path
        public_path = self._public_path(path)
        if public_path is not None:
            return public_path
        if _in(self._package.path, path) or _is_private(path):
            self._leaks.append(f"{where}: {path}")
        return path

    def _definition(self, path: str) -> griffe.Object | str:
        """The loaded object a path refers to, or the path if there's none."""
        try:
            member = self._package.modules_collection.get_member(path)
        except _UNRESOLVABLE:
            return path
        if not isinstance(member, griffe.Object | griffe.Alias):
            return path
        if not _in(self._package.path, path):
            # Keep the path another library's name is imported from.
            return member if isinstance(member, griffe.Object) else path
        try:
            return self._follow(member)
        except _UNRESOLVABLE:
            return path

    def _public_path(self, path: str) -> str | None:
        """The path consumers import a name from, if there is one.

        It's the path of an export, or of a public member of one, such as a
        nested class or an enum member.
        """
        parts = path.split(".")
        for length in range(len(parts), 0, -1):
            public_path = self._public_paths.get(".".join(parts[:length]))
            if public_path is not None:
                rest = parts[length:]
                if _is_private(".".join(rest)):
                    return None
                return ".".join([public_path, *rest])
        return None


def _is_type_variable(member: griffe.Object) -> bool:
    return (
        isinstance(member, griffe.Attribute)
        and isinstance(member.value, griffe.ExprCall)
        and member.value.function.canonical_path in _TYPE_VARIABLE_FACTORIES
    )
