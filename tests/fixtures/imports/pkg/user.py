import typing
import types
import json
import pkg
from pkg import Core, Deep, helper, Thing
from pkg.core import *
from .core import not_exported
from pkg.nothing import *


def use():
    typing.cast(int, 1)          # must NOT resolve to pkg/typing.py
    types.SimpleNamespace()      # must stay external
    json.dumps({})
    pkg.Core()
    pkg.helper()
    pkg.sub.Deep().run()
    Core().run()
    Deep()
    helper()
    Thing()
    not_exported()
    pkg.r1.Thing()
