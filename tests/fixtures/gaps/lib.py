import functools

_registry = []
_lazy = {}


def register(f):
    _registry.append(f)
    return f


import typing


def factory(tag: str) -> typing.Callable[[typing.Any], typing.Any]:
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args):
            return f(*args)
        return wrapper
    return decorator


def __getattr__(name):
    return _lazy[name]


class Thing:
    @property
    def label(self):
        return "x"

    def describe_me(self):
        return "me"


@register
def bare_decorated():
    return 1


@factory("t")
def factory_decorated():
    return 2


class Holder:
    def describe(self, obj):
        return obj.label          # obj has no known type: the repository's property `label`


class Shape:
    @property
    def sides(self):
        return 0


class Square(Shape):
    @property
    def sides(self):
        return 4


def count_sides(s: Shape):
    return s.sides               # declared as Shape: a Square can be passed


def get_describer(t: "Thing"):
    return t.describe_me         # a method reference, returned and called later
