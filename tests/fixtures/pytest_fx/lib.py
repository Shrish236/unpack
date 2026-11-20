class Client:
    def get(self, url):
        return self._request(url)

    def _request(self, url):
        return self._send(url)

    def _send(self, url):
        return self._inner(url)

    def _inner(self, url):
        return url

    def untested(self):
        pass


class AsyncClient:
    async def get(self, url):
        return await self._request(url)

    async def _request(self, url):
        return url


def build():
    return Client()
