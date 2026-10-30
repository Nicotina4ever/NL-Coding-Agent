from __future__ import annotations

from catalog.models import InsufficientStock, Product, Reservation
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

    def available(self, product_id: str, now: float | None = None) -> int:
        return self.get_product(product_id).stock

    def reserve(self, product_id: str, quantity: int,
                now: float | None = None, ttl: float = 30.0) -> Reservation:
        raise NotImplementedError("reservation support is not implemented")

    def release(self, reservation_id: str) -> bool:
        raise NotImplementedError("reservation release is not implemented")

    def expire(self, now: float | None = None) -> int:
        raise NotImplementedError("reservation expiry is not implemented")
