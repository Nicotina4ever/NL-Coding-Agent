import pytest

from catalog import api
from catalog.models import InsufficientStock, Reservation


def test_existing_product_api_is_preserved():
    service = api.bootstrap()
    assert service.get_product("p1").stock == 5
    assert [product.id for product in service.list_products()] == ["p1", "p2"]


def test_reservation_reduces_available_stock():
    service = api.bootstrap()
    reservation = service.reserve("p1", 2, now=100.0, ttl=30.0)
    assert isinstance(reservation, Reservation)
    assert reservation.quantity == 2
    assert reservation.expires_at == 130.0
    assert service.available("p1", now=100.0) == 3


def test_insufficient_stock_is_rejected():
    service = api.bootstrap()
    with pytest.raises(InsufficientStock):
        service.reserve("p2", 3, now=100.0)


def test_release_restores_stock_and_reports_unknown_id():
    service = api.bootstrap()
    reservation = service.reserve("p1", 2, now=100.0)
    assert service.release(reservation.id) is True
    assert service.available("p1", now=100.0) == 5
    assert service.release("missing-reservation") is False


def test_expired_reservation_no_longer_blocks_stock():
    service = api.bootstrap()
    service.reserve("p1", 1, now=100.0, ttl=10.0)
    service.reserve("p1", 2, now=105.0, ttl=20.0)
    assert service.available("p1", now=105.0) == 2
    assert service.expire(now=111.0) == 1
    assert service.available("p1", now=111.0) == 3
    assert service.expire(now=130.0) == 1
    assert service.available("p1", now=130.0) == 5


def test_api_helpers_share_bootstrap_service():
    service = api.bootstrap()
    reservation = api.api_reserve(service, "p1", 1, now=200.0, ttl=10.0)
    assert api.api_available(service, "p1", now=200.0) == 4
    assert api.api_release(service, reservation.id) is True
    assert api.api_available(service, "p1", now=200.0) == 5
