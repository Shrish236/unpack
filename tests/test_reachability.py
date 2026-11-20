"""Test reachability: which tests can reach each function, and the `none` flag.

`direct` and `reached` mean a test can reach the call site on a static path; `none` means no path
exists even through ambiguous edges, which is the only red flag. Argument gating and import-time
execution are covered in the tests below.
"""
from tests.helpers import build

# ---------------------------------------------------------------- pytest fixtures + reachability
def test_fixtures_by_parameter_name_and_reach_labels():
    g = build("pytest_fx")
    r = g.reach
    cget, creq, _csend, cinner = ("lib.py::Client.get", "lib.py::Client._request", "lib.py::Client._send", "lib.py::Client._inner")
    assert r[cget].label == "direct"                    # test_direct calls c.get
    assert r[cget].count == 3                            # via fixture, direct, chained fixture
    assert r[creq].label == "reached" and r[creq].min_depth == 2
    assert r[cinner].label == "reached" and r[cinner].min_depth == 4
    assert r[cinner].path[0].startswith("test_a.py::") and r[cinner].path[-1] == cinner
    assert "lib.py::Client.get" in r[cinner].path
    assert r["lib.py::Client.untested"].label == "none"
    assert r["lib.py::AsyncClient.get"].label == "none" and r["lib.py::AsyncClient._request"].label == "none"
    assert r["lib.py::build"].label == "direct"           # called from TestGroup.test_method
    assert r["conftest.py::client"].label == "direct" or r["conftest.py::client"].label == "reached"


def test_reach_depth_is_not_capped_at_two():
    g = build("pytest_fx")
    ri = g.reach["lib.py::Client._inner"]
    assert ri.min_depth == 4 and len(ri.path) == 5


def test_import_time_reachability_and_instance_protocol_labels():
    g = build("containers")
    r = g.reach
    assert r["m.py::A.__init__"].label in ("reached", "direct")
    assert r["m.py::B.__init__"].label == "reached" and r["m.py::B.__init__"].min_depth == 2   # test -> make -> B.__init__
    # SETUP = A() runs on import, so even a function only called at module level is reached by every test
    assert r["m.py::Color.__new__"].label == "reached" and r["m.py::Color.__new__"].path[1] == "m.py"
    # dunders never become a false `none`: AMBIGUOUS edge from the constructor of a class
    assert r["m.py::Pat.__init__"].label == "direct"
    assert r["m.py::Pat.__hash__"].label == "reached_uncertain"
    assert r["m.py::Holder.use"].label == "none"


# ---------------------------------------------------------------- argument-sensitive reachability
def test_guarded_calls_follow_the_supplied_arguments():
    g = build("gate")
    r = g.reach
    # test calls Plain.send(1) without `source`: the `if source is not None:` branch cannot run
    assert r["lib.py::Plain.send"].label == "direct"
    # ...but Tagged (inherits Plain.send) is called with source="x": the helper IS reached
    assert r["lib.py::Plain._stamp"].label == "reached" and r["lib.py::Plain._stamp"].count == 1
    assert r["lib.py::Plain._stamp"].path[0] == "test_lib.py::test_tagged_with_source_keyword"
    # positional-only call without the argument: helper not reached
    assert r["lib.py::Positional._stamp"].label == "none"
    # **kwargs expansion: unknown, so conservatively reached
    assert r["lib.py::Splat._stamp"].label == "reached"
    # parameter re-assigned before the test (`source = source or "default"`): never gated
    assert r["lib.py::Rebound._stamp"].label == "reached"
    # unguarded call is always followed
    assert r["lib.py::Unguarded._always"].label == "reached"
    # explicit forwarding `send(req, source=source)` supplies the argument: conservatively reached
    assert r["lib.py::Forward._stamp"].label == "reached"
    # truthy default: not gated by absence
    assert r["lib.py::Truthy._stamp"].label == "reached"
    # `if a is not None and b is not None`: needs BOTH, only one supplied
    assert r["lib.py::Conj._both"].label == "none"
