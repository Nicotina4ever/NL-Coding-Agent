from __future__ import annotations

from catalog.models import Product
from catalog.repository import CatalogRepository


class CatalogService:
    def __init__(self, repository: CatalogRepository):
        self.repository = repository

    def create_product(self, product_id: str, name: str, stock: int) -> Product:
        if stock < 0:
            raise ValueError("stock must be non-negative")
        return self.repository.add_product(Product(product_id, name, stock))

    def get_product(self, product_id: str) -> Product:
        product = self.repository.get_product(product_id)
        if product is None:
            raise KeyError(product_id)
        return product

    def list_products(self) -> list[Product]:
        return self.repository.list_products()
