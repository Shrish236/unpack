"""Incremental update must equal a full rebuild, for every kind of change.

Each scenario builds a small git history, applies one kind of change in a second commit, and
compares the incrementally updated graph with a graph built from scratch at the head commit.
"""

import os
import subprocess

import pytest

from unpack_graph.diff import name_status
from unpack_graph.graph import build_graph
from unpack_graph.incremental import graph_fingerprint, update_graph
from unpack_graph.source import GitSource

BASE_FILES = {
    "pkg/__init__.py": "",
    "pkg/core.py": '''class Base:
    def run(self, x):
        return x


class Impl(Base):
    def run(self, x):
        return helper(x) + 1


def helper(x):
    return x * 2


def gone():
    return 3
''',
    "pkg/user.py": '''from pkg import core


def use():
    return core.helper(1) + core.Impl().run(2)
''',
    "pkg/leaf.py": "def leaf():\n    return 1\n",
    # an unchanged caller whose name-based sites find nothing until a repository method appears
    "pkg/reader.py": "def read(x):\n    return x.get('k') + x.size\n",
    "pkg/unused.py": "def unused():\n    return 9\n",
    "pkg/base.py": "class Base:\n    pass\n",
    # a chain of re-exports: child.py is three import hops from base.py, beyond the two-hop closure
    "pkg/top.py": "from pkg.base import Base\n",
    "pkg/mid.py": "from pkg.top import Base\n",
    "pkg/child.py": (
        "from pkg.mid import Base\n\n\n"
        "class Child(Base):\n"
        "    def visit(self, n):\n"
        "        return getattr(self, 'v_' + n)()\n\n"
        "    def v_a(self):\n"
        "        return 1\n"
    ),
    "tests/test_core.py": '''from pkg import core, user


def test_use():
    assert user.use() == 6


def test_helper():
    assert core.helper(2) == 4
''',
}


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


def _commit(root, message):
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()


def _write(root, files):
    for path, text in files.items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)


def _changed_and_deleted(root, base, head):
    changed, deleted = set(), set()
    for status, old, new in name_status(str(root), base, head):
        if not (old.endswith(".py") or new.endswith(".py")):
            continue
        if status == "D":
            deleted.add(old)
        elif status == "R":
            deleted.add(old)
            changed.add(new)
        else:
            changed.add(new)
    return changed, deleted


def _history(tmp_path, change):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _write(root, BASE_FILES)
    base = _commit(root, "base")
    change(root)
    head = _commit(root, "head")
    return root, base, head


def _body_change(root):
    _write(root, {"pkg/core.py": BASE_FILES["pkg/core.py"].replace("return x * 2", "return x * 3")})


def _add_module(root):
    _write(root, {"pkg/extra.py": "from pkg import core\n\n\ndef f():\n    return core.helper(4)\n"})


def _delete_module(root):
    os.remove(os.path.join(root, "pkg/unused.py"))


def _rename_module(root):
    os.rename(os.path.join(root, "pkg/leaf.py"), os.path.join(root, "pkg/leaf_renamed.py"))


def _override_signature_change(root):
    _write(root, {"pkg/core.py": BASE_FILES["pkg/core.py"].replace(
        "class Base:\n    def run(self, x):", "class Base:\n    def run(self, x, y=0):")})


def _reexport(root):
    _write(root, {"pkg/__init__.py": "from .core import helper\n"})


def _ancestor_gains_handler(root):
    # child.py is not changed, but its getattr-dispatched site now reaches the new handler
    _write(root, {"pkg/base.py": "class Base:\n    def v_b(self):\n        return 2\n"})


def _delete_callee_keep_caller(root):
    _write(root, {"pkg/core.py": BASE_FILES["pkg/core.py"].replace("def helper(x):\n    return x * 2\n", "")})


def _new_methods_named_like_untyped_calls(root):
    # `x.get(...)` and `x.size` in pkg/reader.py were external (no repository method or property
    # by that name); this file adds both, so those sites now resolve by name
    _write(root, {"pkg/store.py": (
        "class Store:\n"
        "    def get(self, k):\n"
        "        return k\n\n"
        "    @property\n"
        "    def size(self):\n"
        "        return 0\n")})


SCENARIOS = {
    "new_methods_named_like_untyped_calls": _new_methods_named_like_untyped_calls,
    "body_change": _body_change,
    "add_module": _add_module,
    "delete_module": _delete_module,
    "rename_module": _rename_module,
    "override_signature_change": _override_signature_change,
    "reexport_added": _reexport,
    "callee_deleted": _delete_callee_keep_caller,
    "ancestor_gains_dispatch_target": _ancestor_gains_handler,
}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_incremental_equals_full_rebuild(tmp_path, name):
    root, base, head = _history(tmp_path, SCENARIOS[name])
    changed, deleted = _changed_and_deleted(root, base, head)
    gb = build_graph(GitSource(str(root), base))
    gi, _stats = update_graph(gb, GitSource(str(root), head), changed, deleted)
    gf = build_graph(GitSource(str(root), head))
    assert graph_fingerprint(gi) == graph_fingerprint(gf)


def test_unrelated_change_re_resolves_only_the_changed_file(tmp_path):
    root, base, head = _history(tmp_path, _body_change_leaf)
    changed, deleted = _changed_and_deleted(root, base, head)
    gb = build_graph(GitSource(str(root), base))
    gi, stats = update_graph(gb, GitSource(str(root), head), changed, deleted)
    # pkg/leaf.py has no importers and no subclasses, so nothing else needs re-resolution
    assert stats["changed"] == 1
    assert stats["affected"] == 1
    assert graph_fingerprint(gi) == graph_fingerprint(build_graph(GitSource(str(root), head)))


def _body_change_leaf(root):
    _write(root, {"pkg/leaf.py": "def leaf():\n    return 2\n"})
