"""
Tests for restocking order API endpoints.
"""
from datetime import datetime

import pytest


def forecasts_by_sku(client):
    """Return the demand forecasts keyed by SKU."""
    return {f["item_sku"]: f for f in client.get("/api/demand").json()}


class TestRestockingForecastData:
    """The demand forecasts must carry the data restocking needs."""

    def test_forecasts_have_cost_and_lead_time(self, client):
        """Test that every forecast has a unit cost and a lead time."""
        data = client.get("/api/demand").json()
        assert len(data) > 0

        for forecast in data:
            assert isinstance(forecast["unit_cost"], (int, float))
            assert forecast["unit_cost"] > 0
            assert isinstance(forecast["lead_time_days"], int)
            assert forecast["lead_time_days"] > 0


class TestRestockingOrderEndpoints:
    """Test suite for restocking order endpoints."""

    def test_get_restocking_orders_empty(self, client):
        """Test that no orders exist before anything was submitted."""
        response = client.get("/api/restocking-orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_restocking_order(self, client):
        """Test submitting a valid order."""
        forecast = forecasts_by_sku(client)["WDG-001"]
        payload = {
            "budget": 10000,
            "items": [{
                "item_sku": "WDG-001",
                "item_name": forecast["item_name"],
                "quantity": 10,
                "unit_cost": forecast["unit_cost"],
            }],
        }

        response = client.post("/api/restocking-orders", json=payload)
        assert response.status_code == 201

        order = response.json()
        assert order["order_number"].startswith("RST-")
        assert order["status"] == "Submitted"
        assert order["budget"] == 10000
        assert abs(order["total_cost"] - 10 * forecast["unit_cost"]) < 0.01
        assert order["lead_time_days"] == forecast["lead_time_days"]
        assert len(order["items"]) == 1

    def test_lead_time_is_maximum_of_items(self, client):
        """Test that the order lead time is the slowest item's lead time."""
        forecasts = forecasts_by_sku(client)
        skus = ["FLT-405", "WDG-001"]
        payload = {
            "budget": 100000,
            "items": [
                {"item_sku": s, "item_name": forecasts[s]["item_name"],
                 "quantity": 1, "unit_cost": forecasts[s]["unit_cost"]}
                for s in skus
            ],
        }

        order = client.post("/api/restocking-orders", json=payload).json()
        expected = max(forecasts[s]["lead_time_days"] for s in skus)
        assert order["lead_time_days"] == expected

    def test_expected_delivery_matches_lead_time(self, client):
        """Test that expected delivery is submitted date plus lead time."""
        forecast = forecasts_by_sku(client)["GSK-203"]
        payload = {
            "budget": 10000,
            "items": [{"item_sku": "GSK-203", "item_name": forecast["item_name"],
                       "quantity": 5, "unit_cost": forecast["unit_cost"]}],
        }

        order = client.post("/api/restocking-orders", json=payload).json()
        submitted = datetime.fromisoformat(order["submitted_date"])
        delivery = datetime.fromisoformat(order["expected_delivery"])
        assert (delivery - submitted).days == forecast["lead_time_days"]

    def test_client_cannot_fake_unit_cost(self, client):
        """Test that the server uses the forecast price, not the client's."""
        forecast = forecasts_by_sku(client)["WDG-001"]
        payload = {
            "budget": 100,
            "items": [{"item_sku": "WDG-001", "item_name": "Fake",
                       "quantity": 10, "unit_cost": 0.01}],
        }

        # 10 * real price is far above the budget of 100, so a faked price must not pass
        assert 10 * forecast["unit_cost"] > 100
        response = client.post("/api/restocking-orders", json=payload)
        assert response.status_code == 400

    def test_created_order_is_listed_newest_first(self, client):
        """Test that submitted orders show up in the list, newest first."""
        forecast = forecasts_by_sku(client)["FLT-405"]
        item = {"item_sku": "FLT-405", "item_name": forecast["item_name"],
                "quantity": 1, "unit_cost": forecast["unit_cost"]}

        first = client.post("/api/restocking-orders", json={"budget": 1000, "items": [item]}).json()
        second = client.post("/api/restocking-orders", json={"budget": 1000, "items": [item]}).json()

        listed = client.get("/api/restocking-orders").json()
        assert [o["id"] for o in listed] == [second["id"], first["id"]]

    def test_create_order_over_budget(self, client):
        """Test that exceeding the budget is rejected."""
        forecast = forecasts_by_sku(client)["WDG-001"]
        payload = {
            "budget": 1,
            "items": [{"item_sku": "WDG-001", "item_name": forecast["item_name"],
                       "quantity": 10, "unit_cost": forecast["unit_cost"]}],
        }

        response = client.post("/api/restocking-orders", json=payload)
        assert response.status_code == 400
        assert "budget" in response.json()["detail"].lower()
        assert client.get("/api/restocking-orders").json() == []

    def test_create_order_without_items(self, client):
        """Test that an empty order is rejected."""
        response = client.post("/api/restocking-orders", json={"budget": 1000, "items": []})
        assert response.status_code == 400

    def test_create_order_invalid_quantity(self, client):
        """Test that zero or negative quantities are rejected."""
        forecast = forecasts_by_sku(client)["WDG-001"]
        for quantity in (0, -5):
            payload = {
                "budget": 10000,
                "items": [{"item_sku": "WDG-001", "item_name": forecast["item_name"],
                           "quantity": quantity, "unit_cost": forecast["unit_cost"]}],
            }
            response = client.post("/api/restocking-orders", json=payload)
            assert response.status_code == 400

    def test_create_order_unknown_sku(self, client):
        """Test that an unknown SKU is rejected."""
        payload = {
            "budget": 10000,
            "items": [{"item_sku": "NOPE-999", "item_name": "Nope", "quantity": 1, "unit_cost": 1.0}],
        }

        response = client.post("/api/restocking-orders", json=payload)
        assert response.status_code == 400
        assert "unknown sku" in response.json()["detail"].lower()

    def test_create_order_missing_fields(self, client):
        """Test that a malformed body fails Pydantic validation."""
        response = client.post("/api/restocking-orders", json={"budget": 1000})
        assert response.status_code == 422
