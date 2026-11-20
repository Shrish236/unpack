from ..core import helper as h
from ..core import Core
from .. import types as pkg_types
from . import sibling
import pkg.core
import pkg.sub.deep as dd
import pkg.core as c


def use_relative():
    h()
    Core()
    pkg_types.mine()
    sibling.sib()
    pkg.core.helper()
    dd.Deep().run()
    c.Core().run()


import sibling as sib_abs      # only resolvable because pkg/a is an ancestor dir of this module


def use_abs_sibling():
    sib_abs.sib()
