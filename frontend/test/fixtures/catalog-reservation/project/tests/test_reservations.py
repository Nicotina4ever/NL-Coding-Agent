import pytest

from catalog import reservation_api as api
from catalog.models import InsufficientStock, Product, Reservation
from catalog.repository import CatalogRepository
from catalog.reservation_repository import ReservationRepository
from catalog.reservation_service import ReservationService


def make_service():
    catalog = CatalogRepository()
    catalog.add_product(Product("p1", "Widget", 5))
    catalog.add_product(Product("p2", "Gadget", 2))
    return ReservationService(catalog, ReservationRepository())


def test_reservation_reduces_available_stock():
    service = make_service()
    reservation = service.reserve("p1", 2, now=100.0, ttl=30.0)
    assert isinstance(reservation, Reservation)
    assert reservation.quantity == 2
    assert reservation.expires_at == 130.0
    assert service.available("p1", now=100.0) == 3


def test_insufficient_stock_is_rejected():
    service = make_service()
    with pytest.raises(InsufficientStock):
        service.reserve("p2", 3, now=100.0)


def test_release_restores_stock_and_reports_unknown_id():
    service = make_service()
    reservation = service.reserve("p1", 2, now=100.0)
    assert service.release(reservation.id) is True
    assert service.available("p1", now=100.0) == 5
    assert service.release("missing-reservation") is False


def test_expired_reservation_no_longer_blocks_stock():
    service = make_service()
    service.reserve("p1", 1, now=100.0, ttl=10.0)
    service.reserve("p1", 2, now=105.0, ttl=20.0)
    assert service.available("p1", now=105.0) == 2
    assert service.expire(now=111.0) == 1
    assert service.available("p1", now=111.0) == 3
    assert service.expire(now=130.0) == 1
    assert service.available("p1", now=130.0) == 5


def test_api_helpers_share_service():
    service = make_service()
    reservation = api.api_reserve(service, "p1", 1, now=200.0, ttl=10.0)
    assert api.api_available(service, "p1", now=200.0) == 4
    assert api.api_release(service, reservation.id) is True
    assert api.api_available(service, "p1", now=200.0) == 5
