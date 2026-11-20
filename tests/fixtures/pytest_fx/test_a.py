import lib


def test_fixture_user(client):
    client.get("/")


def test_direct():
    c = lib.Client()
    c.get("/")


def test_chained_fixture(client2):
    client2.get("/")


class TestGroup:
    def test_method(self):
        lib.build()
