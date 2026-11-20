from typing import Optional


class Cls:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def m(self):
        pass

    def helper(self) -> "Cls":
        return self


class ACls:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def am(self):
        pass


class Holder:
    def __init__(self, c: Cls, o: Optional[Cls] = None):
        self.c = c
        self.made = Cls()

    def run(self):
        self.c.m()
        self.made.m()


def f1():
    x = Cls()
    x.m()


def f2():
    with Cls() as x:
        x.m()


async def f3():
    async with ACls() as x:
        await x.am()


def f4(p: Cls):
    p.m()


def f5(o: Optional[Cls]):
    o.m()


def f6(u: Cls | None):
    u.m()


def f7():
    c = Cls()
    c.helper().m()


def f8():
    Cls().helper().m()


def f9(h: Holder):
    h.c.m()
    h.made.m()


def f10(unknown):
    unknown.m()      # receiver untyped: unique-name fallback
