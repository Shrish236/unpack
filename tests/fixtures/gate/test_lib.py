import lib


def test_plain_without_source():
    lib.Plain().send(1)


def test_tagged_with_source_keyword():
    lib.Tagged().send(1, source="x")


def test_positional_without():
    lib.Positional().send(1)


def test_splat():
    kw = {"source": 1}
    lib.Splat().send(1, **kw)


def test_rebound():
    lib.Rebound().send(1)


def test_unguarded():
    lib.Unguarded().send(1)


def test_forward():
    lib.Forward().via(1)


def test_truthy_default():
    lib.Truthy().send(1)


def test_conj_one_arg():
    lib.Conj().send(1, source="x")
