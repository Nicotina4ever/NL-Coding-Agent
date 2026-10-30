from catalog.api import bootstrap_catalog


def test_existing_product_api_is_preserved():
    service = bootstrap_catalog()
    assert service.get_product("p1").stock == 5
    assert [product.id for product in service.list_products()] == ["p1", "p2"]
