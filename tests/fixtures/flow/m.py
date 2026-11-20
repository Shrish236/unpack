import typing


class Req:
    pass


class Resp:
    def ok(self):
        pass

    @property
    def cookies(self):
        return 1


class Err(Exception):
    def hook(self):
        pass

    @property
    def request(self):
        return 1

    @request.setter
    def request(self, v):
        pass


def auth_flow(req: Req) -> typing.Generator[Req, Resp, None]:
    response = yield req
    response.ok()
    if response.cookies:
        pass


def guarded():
    try:
        pass
    except (Err, ValueError) as exc:
        exc.request = 1
        exc.hook()
    except Err as other:
        other.hook()


import pytest


def test_excinfo():
    with pytest.raises(Err) as info:
        raise Err()
    info.value.hook()
