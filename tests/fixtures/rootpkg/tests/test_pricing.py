from shop.app.pricing import apply_discount


def test_discount():
    assert apply_discount(10, 50) == 5
