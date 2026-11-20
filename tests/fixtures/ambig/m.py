class Client:
    def get(self):
        pass

    def only_here(self):
        pass


class AsyncClient:
    def get(self):
        pass


class Headers:
    def get(self):
        pass


def f(x):
    x.get()
    x.only_here()
    x.nothing_like_this()


def g():
    c = Client()
    c.get()
