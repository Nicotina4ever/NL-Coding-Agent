from __future__ import annotations

from dataclasses import dataclass


class InsufficientStock(Exception):
    """Raised when a reservation exceeds currently available stock."""


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    stock: int


@dataclass(frozen=True)
class Reservation:
    id: str
    product_id: str
    quantity: int
    created_at: float
    expires_at: float
