from __future__ import annotations

from catalog.models import Product, Reservation


class CatalogRepository:
    """In-memory storage used by the service and integration tests."""

    def __init__(self):
        self._products: dict[str, Product] = {}
        self._reservations: dict[str, Reservation] = {}

    def add_product(self, product: Product) -> Product:
        self._products[product.id] = product
        return product

    def get_product(self, product_id: str) -> Product | None:
        return self._products.get(product_id)

    def list_products(self) -> list[Product]:
        return list(self._products.values())

    def save_reservation(self, product_id: str, quantity: int,
                         created_at: float, expires_at: float) -> Reservation:
        raise NotImplementedError("reservation persistence is not implemented")

    def get_reservation(self, reservation_id: str) -> Reservation | None:
        raise NotImplementedError("reservation lookup is not implemented")

    def delete_reservation(self, reservation_id: str) -> bool:
        raise NotImplementedError("reservation deletion is not implemented")

    def list_reservations(self) -> list[Reservation]:
        raise NotImplementedError("reservation listing is not implemented")
