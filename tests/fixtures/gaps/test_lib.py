import lib


def test_bare_decorator():
    lib.bare_decorated()


def test_factory_decorator():
    lib.factory_decorated()


def test_module_getattr():
    return lib.not_defined_anywhere


def test_untyped_property():
    lib.Holder().describe(lib.Thing())


def test_property_override_through_base_declaration():
    lib.count_sides(lib.Square())


def test_method_reference_is_a_reference():
    lib.get_describer(lib.Thing())()
