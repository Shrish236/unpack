"""module doc: def fake(): pass"""
from __future__ import annotations
import abc
import contextlib
import typing
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .other import Thing

    def only_for_type_checkers() -> Thing:
        raise NotImplementedError


def top():
    def inner():
        def deeper():
            pass

    class LocalCls:
        def m(self):
            pass


class Outer:
    class Inner:
        def im(self):
            pass

    def method(self):
        return "def not_a_function(): pass"

    @property
    def prop(self):
        return 1

    @prop.setter
    def prop(self, v):
        pass

    @staticmethod
    def sm():
        pass

    @classmethod
    def cm(cls):
        pass

    @contextlib.contextmanager
    def ctx(self):
        yield

    @abc.abstractmethod
    def abstract(self):
        pass

    async def am(self):
        pass


if True:
    def in_if():
        pass
else:
    def in_else():
        pass

try:
    def in_try():
        pass
except Exception:
    def in_except():
        pass


def docstring_fn():
    """def not_real(): pass"""
    s = '''
def also_not_real():
    pass
'''
    return s


def decorator(c):
    return c


@decorator
class Decorated:
    pass


@decorator
def decorated_fn():
    pass
