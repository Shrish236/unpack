"""Shared test helpers for the extraction tests."""

import os

from unpack_graph.extract import extract_file, module_name_for
from unpack_graph.source import FsSource

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Extracted:
    """Pass-1 results for a tree: modules plus flat id -> record maps."""

    def __init__(self, mods):
        self.mods = mods
        self.funcs = {f.id: f for m in mods.values() for f in m.funcs}
        self.classes = {c.id: c for m in mods.values() for c in m.classes}


def extract_tree(root):
    src = FsSource(root)
    files = src.list_files()
    known = set(files)
    mods = {}
    for p in files:
        name, pkg = module_name_for(p, lambda x: x in known)
        mods[p] = extract_file(p, src.read(p), name, pkg)
    return Extracted(mods)


def build(name):
    return extract_tree(os.path.join(FIX, name))
