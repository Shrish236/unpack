class A:
    def __init__(self):
        pass

    def only_on_a(self):
        pass

    def shared(self):
        pass


class B(A):
    def shared(self):
        super().shared()


class C(B):
    def use(self):
        self.only_on_a()      # defined only on the grandparent
        self.shared()         # defined on B (parent), also on A

    @classmethod
    def make(cls):
        cls.only_on_a(None)
        return cls()          # inherits A.__init__

    def init_chain(self):
        super().only_on_a()


class D(C):
    def __init__(self):
        super().__init__()
