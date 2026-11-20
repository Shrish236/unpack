class Plain:
    def send(self, req, source=None):
        if source is not None:
            req = self._stamp(req, source)
        return req

    def _stamp(self, req, source):
        return req


class Tagged(Plain):
    pass


class Positional:
    def send(self, req, source=None):
        if source:
            self._stamp(source)
        return req

    def _stamp(self, source):
        return source


class Splat:
    def send(self, req, source=None):
        if source is not None:
            self._stamp()
        return req

    def _stamp(self):
        pass


class Rebound:
    def send(self, req, source=None):
        source = source or "default"
        if source:
            self._stamp()
        return req

    def _stamp(self):
        pass


class Unguarded:
    def send(self, req, flag=None):
        self._always()
        return req

    def _always(self):
        pass


class Forward:
    def send(self, req, source=None):
        if source is not None:
            self._stamp()

    def _stamp(self):
        pass

    def via(self, req, source=None):
        return self.send(req, source=source)


class Truthy:
    def send(self, req, source="on"):
        if source:
            self._stamp()

    def _stamp(self):
        pass


class Conj:
    def send(self, req, source=None, extra=None):
        if source is not None and extra is not None:
            self._both()

    def _both(self):
        pass
