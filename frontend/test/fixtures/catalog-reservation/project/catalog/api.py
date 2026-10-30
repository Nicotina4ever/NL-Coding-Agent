from __future__ import annotations

from catalog.repository import CatalogRepository
from catalog.service import CatalogService


def bootstrap_catalog() -> CatalogService:
    repository = CatalogRepository()
    service = CatalogService(repository)
    service.create_product("p1", "Widget", 5)
    service.create_product("p2", "Gadget", 2)
    return service
