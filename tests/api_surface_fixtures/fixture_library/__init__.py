"""Stands in for a third-party library that a package's classes inherit from."""


class Base:
    def describe(self) -> str:
        return ""

    def _internal(self) -> None:
        pass
