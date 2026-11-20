class Walker:
    def visit(self, node_type):
        handler = getattr(self, "v_" + node_type)
        return handler()

    def visit_literal(self):
        return getattr(self, "v_one")()

    def visit_unknown(self, name):
        return getattr(self, name)()

    def v_one(self):
        return self._helper()

    def v_two(self):
        return 2

    def _helper(self):
        return 1

    def not_handler(self):
        return 0


class Other:
    def v_three(self):
        return 3
