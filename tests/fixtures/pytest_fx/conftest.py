import pytest

import lib


@pytest.fixture
def client():
    return lib.Client()


@pytest.fixture
def client2(client):
    return client
