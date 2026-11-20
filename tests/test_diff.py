"""Change detection (renames, moves, classification) and the region view validated against the GraphView schema."""
import json
import os
import subprocess

import jsonschema
import pytest

from unpack_graph.diff import detect_changes
from unpack_graph.region import build_region

SCHEMA = json.load(open(os.path.join(os.path.dirname(__file__), "..", "schemas", "graphview.schema.json")))


def git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


def commit(root, msg):
    git(root, "add", "-A")
    git(root, "commit", "-qm", msg)
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "r"
    (r / "pkg").mkdir(parents=True)
    (r / "tests").mkdir()
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    (r / "pkg" / "__init__.py").write_text("")
    (r / "pkg" / "core.py").write_text('''"""mod"""
import os


def alpha(x):
    """Doc."""
    # a comment
    return x + 1


def beta(x, y=1):
    return alpha(x) * y


def gone(x):
    return x


def user():
    return gone(2) + beta(1)


def renamed_me(a):
    total = 0
    for i in range(a):
        total += i
    return total


class K:
    def run(self):
        return alpha(1)
''')
    (r / "pkg" / "other.py").write_text("def mover(z):\n    return z * 3 + 1\n")
    (r / "pkg" / "file_to_rename.py").write_text("def inside():\n    return 1\n")
    (r / "tests" / "test_core.py").write_text('''from pkg import core


def test_alpha():
    assert core.alpha(1) == 2


def test_beta():
    assert core.beta(1) == 2
''')
    base = commit(r, "base")
    return r, base


def by_id(cs):
    return {c.id: c for c in cs.functions}


def test_text_only_signature_functional_deleted_renamed_moved(repo):
    r, base = repo
    core = (r / "pkg" / "core.py").read_text()
    core = core.replace('"""Doc."""', '"""New docstring."""').replace("# a comment", "# changed comment\n")
    core = core.replace("def beta(x, y=1):", "def beta(x, y=2):").replace("return alpha(x) * y", "return alpha(x) * y + 0")
    core = core.replace('''def gone(x):
    return x


''', "")
    core = core.replace("def renamed_me(a):", "def renamed_now(a):")
    (r / "pkg" / "core.py").write_text(core)
    # move `mover` to another file unchanged
    (r / "pkg" / "other.py").write_text("")
    (r / "pkg" / "moved.py").write_text("def mover(z):\n    return z * 3 + 1\n")
    # file rename with content change
    subprocess.run(["git", "-C", str(r), "mv", "pkg/file_to_rename.py", "pkg/file_renamed.py"], check=True)
    (r / "pkg" / "file_renamed.py").write_text("def inside():\n    return 2\n")
    head = commit(r, "change")
    cs = detect_changes(str(r), base, head)
    c = by_id(cs)
    assert c["pkg/core.py::alpha"].kind == "modified" and c["pkg/core.py::alpha"].flags == ["text_only"]
    assert set(c["pkg/core.py::beta"].flags) == {"signature", "functional"}       # both at once
    assert c["pkg/core.py::gone"].kind == "deleted"
    assert c["pkg/core.py::gone"].still_called_by == ["pkg/core.py::user"]       # removed, still called by user
    assert c["pkg/core.py::renamed_now"].kind == "renamed" and c["pkg/core.py::renamed_now"].old_id == "pkg/core.py::renamed_me"
    assert c["pkg/moved.py::mover"].kind == "moved" and c["pkg/moved.py::mover"].old_id == "pkg/other.py::mover"
    assert "pkg/core.py::user" not in c                                           # unchanged text -> not listed
    fr = c["pkg/file_renamed.py::inside"]
    assert fr.kind == "modified" and fr.flags == ["functional"] and fr.old_id == "pkg/file_to_rename.py::inside"
    # changed line ranges come from `git diff -U0`
    assert c["pkg/core.py::alpha"].head_lines
    assert all(a >= c["pkg/core.py::alpha"].start and b <= c["pkg/core.py::alpha"].end for a, b in c["pkg/core.py::alpha"].head_lines)
    assert c["pkg/core.py::gone"].base_lines and not c["pkg/core.py::gone"].head_lines


def test_docstring_only_and_whitespace_only(repo):
    r, base = repo
    core = (r / "pkg" / "core.py").read_text().replace('"""Doc."""', '"""Doc, reworded."""')
    core = core.replace("def beta(x, y=1):\n    return", "def beta(x, y=1):\n\n    return")
    (r / "pkg" / "core.py").write_text(core)
    head = commit(r, "doc")
    cs = detect_changes(str(r), base, head)
    kinds = {c.id: (c.kind, c.flags) for c in cs.functions}
    assert kinds == {"pkg/core.py::alpha": ("modified", ["text_only"]), "pkg/core.py::beta": ("modified", ["text_only"])}
    assert cs.modules[0]["module_level_changed"] is False


def test_region_view_schema_tests_and_ghost(repo):
    r, base = repo
    core = (r / "pkg" / "core.py").read_text()
    core = core.replace("return x + 1", "return x + 2")
    core = core.replace('''def gone(x):
    return x


''', "")
    (r / "pkg" / "core.py").write_text(core)
    head = commit(r, "c")
    cs = detect_changes(str(r), base, head)
    view = build_region(cs)
    jsonschema.validate(view, SCHEMA)
    nodes = {n["id"]: n for n in view["nodes"]}
    a = nodes["pkg/core.py::alpha"]
    assert a["role"] == "changed" and a["change"]["flags"] == ["functional"]
    assert a["tests"]["label"] in ("direct",) and a["tests"]["count"] >= 1
    assert any(t["id"].endswith("test_alpha") for t in a["tests"]["tests"])
    assert nodes["pkg/core.py::beta"]["role"] == "neighbor" and nodes["pkg/core.py::beta"]["relation"] == "caller"
    assert nodes["pkg/core.py::K.run"]["role"] == "neighbor" and nodes["pkg/core.py::K.run"]["relation"] == "caller"
    if "pkg/core.py::K" in nodes:
        assert nodes["pkg/core.py::K"]["type"] == "Class"
    g = nodes["pkg/core.py::gone"]
    assert g["ghost"] and g["change"]["kind"] == "deleted" and g["change"]["still_called_by"] == ["pkg/core.py::user"]
    e = [x for x in view["edges"] if x["target"] == "pkg/core.py::gone"]
    assert e and e[0]["via"] == "removed" and e[0]["source"] == "pkg/core.py::user"
    # untested changed function is flagged `none`
    (r / "pkg" / "core.py").write_text((r / "pkg" / "core.py").read_text().replace("return total", "return total + 1"))
    head2 = commit(r, "d")
    cs2 = detect_changes(str(r), head, head2)
    n2 = {n["id"]: n for n in build_region(cs2)["nodes"]}
    assert n2["pkg/core.py::renamed_me"]["tests"]["label"] == "none"
