"""The incremental head build equals a full rebuild, base graphs are reused, the process pool agrees with the
in-process path, and the caches stay bounded."""

from __future__ import annotations

import subprocess

import pytest

from server.app.config import settings
from server.app.pipeline import build as build_module
from server.app.pipeline import repos as repos_module
from unpack_graph.graph import build_graph
from unpack_graph.incremental import diff_fingerprints, graph_fingerprint
from unpack_graph.source import GitSource

from .conftest import GIT_ENV, git, write_files

BASE = {
    "pkg/__init__.py": "",
    "pkg/a.py": "from pkg.b import g\n\n\ndef f(x):\n    return g(x) + 1\n\n\nclass Base:\n    def run(self):\n        return f(1)\n",
    "pkg/b.py": "def g(x):\n    return x * 2\n\n\ndef unused():\n    return 0\n",
    "pkg/c.py": "def gone():\n    return 3\n",
    "pkg/old_name.py": "def renamed():\n    return 4\n",
    "tests/test_pkg.py": "from pkg.a import f\n\n\ndef test_f():\n    assert f(1) == 5\n",
}
HEAD = {
    "pkg/__init__.py": "",
    "pkg/a.py": "from pkg.b import g\n\n\ndef f(x):\n    return g(x) + 2\n\n\nclass Base:\n    def run(self):\n        return f(1)\n",
    "pkg/b.py": "def g(x):\n    return x * 2\n\n\ndef unused():\n    return 0\n\n\ndef added_helper():\n    return g(1)\n",
    "pkg/new_name.py": "def renamed():\n    return 4\n",
    "pkg/sub/__init__.py": "",
    "pkg/sub/d.py": "from pkg.a import Base\n\n\nclass Child(Base):\n    def run(self):\n        return 7\n",
    "tests/test_pkg.py": "from pkg.a import f\n\n\ndef test_f():\n    assert f(1) == 6\n",
}


@pytest.fixture
def repo(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    write_files(work, BASE)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "base")
    base_sha = git(work, "rev-parse", "HEAD")
    mirror = tmp_path / "mirror.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(mirror)], check=True, env=GIT_ENV)
    for path in BASE:
        if path not in HEAD:
            (work / path).unlink()
    write_files(work, HEAD)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "change")
    head_sha = git(work, "rev-parse", "HEAD")
    overlay = {p: HEAD[p].encode() for p in HEAD if BASE.get(p) != HEAD[p]}
    removed = [p for p in BASE if p not in HEAD]
    return {"work": work, "mirror": str(mirror), "base": base_sha, "head": head_sha,
            "overlay": overlay, "removed": removed}


def kwargs(r, *, repo_id=1, full_head=False):
    # The full path needs the head commit in the repository, so it reads the working repo (it has both commits).
    mirror = str(r["work"]) if full_head else r["mirror"]
    return dict(repo_id=repo_id, mirror=mirror, base_sha=r["base"], head_sha=r["head"],
                overlay=r["overlay"], removed=r["removed"], diff_text="", full_head=full_head)


def test_incremental_head_equals_full_rebuild(repo):
    build_module.analyze_blocking(**kwargs(repo))
    incremental = repos_module.load_cached_graph(1, repo["head"])
    full = build_graph(GitSource(repo["work"], repo["head"]), reach=True)
    assert diff_fingerprints(graph_fingerprint(full), graph_fingerprint(incremental)) == {}


def test_incremental_output_matches_full_path_output(repo):
    fast, _ = build_module.analyze_blocking(**kwargs(repo))
    slow, _ = build_module.analyze_blocking(**kwargs(repo, repo_id=2, full_head=True))
    assert fast.stats == slow.stats
    assert fast.reading_order == slow.reading_order
    assert fast.impact == slow.impact


def test_base_graph_is_built_once_per_base_commit(repo, monkeypatch):
    calls = []
    real = build_module.build_graph

    def counting(source, *args, **kw):
        calls.append(kw.get("reach", True))
        return real(source, *args, **kw)

    monkeypatch.setattr(build_module, "build_graph", counting)
    build_module.analyze_blocking(**kwargs(repo))
    first = len(calls)
    build_module.analyze_blocking(**kwargs(repo))
    assert first == 1  # the base graph
    assert len(calls) == first  # the second push reuses the cached base and updates incrementally


def test_process_pool_gives_the_same_result(repo, monkeypatch):
    import asyncio

    inline, _ = build_module.analyze_blocking(**kwargs(repo))
    monkeypatch.setattr(settings, "ANALYSIS_PROCESSES", 1)
    try:
        pooled, timings = asyncio.run(build_module.run_analysis(**kwargs(repo, repo_id=3)))
    finally:
        build_module.shutdown_pool()
    assert pooled.stats == inline.stats
    assert pooled.graph == inline.graph
    assert set(timings) == {"base_s", "head_s", "view_s"}


def test_graph_cache_is_pruned(tmp_data_dir, monkeypatch):
    monkeypatch.setattr(repos_module, "GRAPH_CACHE_KEEP", 2)
    for i in range(4):
        repos_module.save_cached_graph(9, f"{i:040d}", {"i": i})
    kept = sorted(p.name for p in repos_module.graph_cache_path(9, "0" * 40).parent.glob("*.pkl"))
    assert len(kept) == 2


def test_graph_lru_returns_the_loaded_object(tmp_data_dir, monkeypatch):
    monkeypatch.setattr(settings, "GRAPH_LRU_SIZE", 1)
    repos_module.save_cached_graph(4, "a" * 40, {"x": 1})
    first = repos_module.load_cached_graph(4, "a" * 40)
    assert repos_module.load_cached_graph(4, "a" * 40) is first  # served from memory, not unpickled again


def test_read_file_at_reads_one_blob(repo):
    text = repos_module.read_file_at(repo_path(repo), repo["base"], "pkg/b.py").decode()
    assert "def g(x)" in text


def repo_path(r):
    from pathlib import Path

    return Path(r["mirror"])
