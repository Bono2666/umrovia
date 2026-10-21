"""S01/T04 — health endpoint smoke test."""
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_returns_ok(client):
    url = reverse("platform:health")
    response = client.get(url)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "umrovia-api"
    assert body["checks"]["database"] == "ok"
    assert "version" in body


@pytest.mark.django_db
def test_health_sets_request_id_header(client):
    url = reverse("platform:health")
    response = client.get(url)
    assert response["X-Request-ID"]


@pytest.mark.django_db
def test_health_accepts_incoming_request_id(client):
    url = reverse("platform:health")
    response = client.get(url, headers={"X-Request-ID": "gateway-abc-123"})
    assert response["X-Request-ID"] == "gateway-abc-123"
