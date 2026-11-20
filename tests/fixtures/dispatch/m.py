import abc


class Base(abc.ABC):
    @abc.abstractmethod
    def run(self):
        ...


class Impl1(Base):
    def run(self):
        pass


class Impl2(Base):
    def run(self):
        pass


class Unrelated:
    def run(self):
        pass


def use(b: Base):
    b.run()


def use_concrete(i: Impl1):
    i.run()
