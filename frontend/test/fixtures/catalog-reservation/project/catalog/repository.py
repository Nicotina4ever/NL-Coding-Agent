from __future__ import annotations

from catalog.models import Product


class CatalogRepository:
    """Existing product storage; the new reservation modules depend on it."""

    def __init__(self):
        self._products: dict[str, Product] = {}

    def add_product(self, product: Product) -> Product:
        self._products[product.id] = product
        return product

    def get_product(self, product_id: str) -> Product | None:
        return self._products.get(product_id)

    def list_products(self) -> list[Product]:
        return list(self._products.values())
