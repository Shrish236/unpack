from .core import *
from .sub.deep import *      # no __all__ in deep: every public name is exported


def star_user():
    helper()
    Core()
    not_exported()   # not in core.__all__ -> must not resolve


def local_import():
    from .core import helper as hh
    hh()


def star_without_all():
    Deep().run()
