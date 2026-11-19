from _collections_abc import Sized

from leaky_package._hidden import Hidden, HiddenBase, HiddenNumber


class Gadget(HiddenBase):
    part: Hidden

    def use(self, value: Hidden | None) -> list[HiddenNumber]:
        return []

    def measure(self) -> Sized:
        return []


def build() -> Hidden:
    return Hidden()
