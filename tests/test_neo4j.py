"""Neo4j integration: region Cypher == in-memory region; delta update == full load. Skipped without Neo4j."""
import subprocess

import pytest

from unpack_graph import neo4j_io as nio
from unpack_graph.diff import detect_changes
from unpack_graph.graph import build_graph
from unpack_graph.region import build_region
from unpack_graph.source import GitSource

try:
    DRIVER = nio.connect(wait_s=3)
except Exception:                      # pragma: no cover - no database available
    DRIVER = None

pytestmark = pytest.mark.skipif(DRIVER is None, reason="Neo4j not reachable (docker compose up -d)")


def _commit(r, msg):
    subprocess.run(["git", "-C", str(r), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", msg], check=True)
    return subprocess.run(["git", "-C", str(r), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "r"
    (r / "pkg").mkdir(parents=True)
    (r / "tests").mkdir()
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    (r / "pkg" / "__init__.py").write_text("")
    (r / "pkg" / "core.py").write_text('''class Base:
    def run(self):
        return 1


class Impl(Base):
    def run(self):
        return helper() + 1


def helper():
    return 2


def gone():
    return 3


def user():
    return gone() + helper()


def untested():
    return 5
''')
    (r / "tests" / "test_core.py").write_text('''from pkg import core


def test_run():
    assert core.Impl().run() == 3
''')
    base = _commit(r, "base")
    core = (r / "pkg" / "core.py").read_text().replace("return 2", "return 7").replace(
        "def gone():\n    return 3\n\n\n", "").replace("return 5", "return 6")
    (r / "pkg" / "core.py").write_text(core)
    (r / "tests" / "test_extra.py").write_text("from pkg import core\n\n\ndef test_helper():\n    assert core.helper() == 7\n")
    head = _commit(r, "head")
    return str(r), base, head


def test_region_cypher_equals_in_memory(repo):
    root, base, head = repo
    cs = detect_changes(root, base, head)
    nio.load_graph(cs.head_graph, DRIVER)
    nio.annotate_changes(DRIVER, cs)
    mem = build_region(cs)
    db = nio.region_query(DRIVER, cs)
    assert db["nodes"] == mem["nodes"]
    assert db["edges"] == mem["edges"]
    ids = {n["id"]: n for n in db["nodes"]}
    assert ids["pkg/core.py::gone"]["ghost"] and ids["pkg/core.py::gone"]["change"]["still_called_by"] == ["pkg/core.py::user"]
    assert ids["pkg/core.py::untested"]["tests"]["label"] == "none"
    assert ids["pkg/core.py::helper"]["tests"]["label"] in ("direct", "reached")


def test_counts_match_after_full_load(repo):
    root, base, head = repo
    g = build_graph(GitSource(root, head))
    nio.load_graph(g, DRIVER)
    c = nio.db_counts(DRIVER)
    assert (c["modules"], c["classes"], c["functions"], c["calls"]) == (len(g.mods), len(g.classes), len(g.funcs),
                                                                       len(g.calls))
