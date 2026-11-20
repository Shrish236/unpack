import enum
import typing


class A:
    def __init__(self):
        pass


class B:
    def __init__(self):
        pass


REGISTRY = {"a": A, "b": B}


def make(name):
    cls = REGISTRY[name]
    return cls()


class Pat:
    def __init__(self, k):
        self.k = k

    def __lt__(self, other):
        return self.k < other.k

    def __hash__(self):
        return 1

    def matches(self, u):
        return True


class Holder:
    def __init__(self):
        self.mounts: dict[Pat, A] = {}

    def use(self):
        for pat, a in self.mounts.items():
            pat.matches(1)
        for a2 in self.mounts.values():
            a2.__init__()
        return sorted(self.mounts.items())


class Color(enum.IntEnum):
    RED = 1

    def __new__(cls, v):
        return int.__new__(cls, v)

    def __str__(self):
        return "red"


def show():
    return str(Color.RED)


class Many:
    def build(self) -> typing.List["A"]:
        return [A()]

    def go(self):
        for item in self.build():
            item.__init__()


SETUP = A()        # runs at import time
