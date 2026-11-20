from m import Walker


def test_visit():
    Walker().visit("one")


def test_literal():
    Walker().visit_literal()
