from __future__ import annotations

from catalog.repository import CatalogRepository
from catalog.service import CatalogService


def bootstrap() -> CatalogService:
    repository = CatalogRepository()
    service = CatalogService(repository)
    service.create_product("p1", "Widget", 5)
    service.create_product("p2", "Gadget", 2)
    return service


def api_reserve(service: CatalogService, product_id: str, quantity: int,
                now: float | None = None, ttl: float = 30.0):
    raise NotImplementedError("api reservation helper is not implemented")


def api_release(service: CatalogService, reservation_id: str) -> bool:
    raise NotImplementedError("api release helper is not implemented")


def api_available(service: CatalogService, product_id: str,
                  now: float | None = None) -> int:
    raise NotImplementedError("api availability helper is not implemented")
