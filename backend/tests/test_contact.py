"""Public contact submission, validation, consent and privacy boundaries."""
import logging
from smtplib import SMTPException

import pytest
from rest_framework.throttling import SimpleRateThrottle

from modules.platform.models import ContactMessage

pytestmark = pytest.mark.django_db


@pytest.fixture
def contact_logs(caplog):
    logger = logging.getLogger("modules.platform.services")
    logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


@pytest.fixture
def contact_payload():
    return {
        "name": "Pengunjung Demo",
        "company": "Travel Contoh",
        "email": "visitor@example.com",
        "phone": "",
        "topic": "product",
        "message": "Saya ingin memahami alur penggunaan workspace travel.",
        "consent": True,
        "website": "",
    }


def test_anonymous_contact_is_stored_without_exposing_personal_data(client, contact_payload, mailoutbox, settings):
    settings.CONTACT_RECIPIENT_EMAIL = "bonoworxx@gmail.com"
    response = client.post("/api/v1/contact", contact_payload, content_type="application/json")
    assert response.status_code == 201
    assert set(response.json()) == {"reference"}
    message = ContactMessage.objects.get(pk=response.json()["reference"])
    assert message.email == contact_payload["email"]
    assert message.consented_at is not None
    assert message.resolved_at is None
    assert len(mailoutbox) == 1
    notification = mailoutbox[0]
    assert notification.to == ["bonoworxx@gmail.com"]
    assert notification.from_email == settings.DEFAULT_FROM_EMAIL
    assert notification.reply_to == [contact_payload["email"]]
    assert str(message.pk) in notification.subject
    assert message.get_topic_display() in notification.subject
    assert contact_payload["name"] in notification.body
    assert contact_payload["company"] in notification.body
    assert contact_payload["message"] in notification.body
    assert notification.content_subtype == "plain"


@pytest.mark.parametrize("field,value", [
    ("consent", False), ("email", "invalid"), ("message", "short"),
    ("name", " "), ("topic", "unknown"), ("website", "https://spam.example"),
    ("message", "a" * 4001),
])
def test_invalid_contact_is_not_stored(client, contact_payload, field, value, mailoutbox):
    contact_payload[field] = value
    response = client.post("/api/v1/contact", contact_payload, content_type="application/json")
    assert response.status_code == 400
    assert field in response.json()["field_errors"]
    assert not ContactMessage.objects.exists()
    assert not mailoutbox


def test_consent_cannot_be_omitted(client, contact_payload, mailoutbox):
    contact_payload.pop("consent")
    response = client.post("/api/v1/contact", contact_payload, content_type="application/json")
    assert response.status_code == 400
    assert not ContactMessage.objects.exists()
    assert not mailoutbox


def test_contact_messages_cannot_be_read_publicly(client, contact_payload):
    created = client.post("/api/v1/contact", contact_payload, content_type="application/json")
    assert client.get("/api/v1/contact").status_code == 405
    assert client.get(f"/api/v1/contact/{created.json()['reference']}").status_code == 404


def test_contact_rate_limit(client, contact_payload, monkeypatch, mailoutbox):
    monkeypatch.setattr(SimpleRateThrottle, "THROTTLE_RATES", {
        **SimpleRateThrottle.THROTTLE_RATES, "contact-submit": "2/min",
    })
    for _ in range(2):
        assert client.post("/api/v1/contact", contact_payload, content_type="application/json").status_code == 201
    response = client.post("/api/v1/contact", contact_payload, content_type="application/json")
    assert response.status_code == 429
    assert ContactMessage.objects.count() == 2
    assert len(mailoutbox) == 2


@pytest.mark.parametrize("topic", ContactMessage.Topic.values)
def test_contact_notification_recipient_is_server_controlled(client, contact_payload, settings, mailoutbox, topic):
    settings.CONTACT_RECIPIENT_EMAIL = "contact-inbox@example.com"
    contact_payload.update({"topic": topic, "to": "untrusted@example.com", "recipient": "untrusted@example.com"})
    response = client.post("/api/v1/contact", contact_payload, content_type="application/json")
    assert response.status_code == 201
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [settings.CONTACT_RECIPIENT_EMAIL]
    assert mailoutbox[0].reply_to == [contact_payload["email"]]


def test_contact_email_failure_preserves_message_and_reference(client, contact_payload, monkeypatch, contact_logs):
    def fail_send(self):
        raise SMTPException(f"Sensitive upstream error for {contact_payload['email']}")

    monkeypatch.setattr("modules.platform.services.EmailMessage.send", fail_send)
    response = client.post("/api/v1/contact", contact_payload, content_type="application/json")
    assert response.status_code == 201
    assert ContactMessage.objects.filter(pk=response.json()["reference"]).exists()
    log_output = contact_logs.text
    assert "email notification failed" in log_output
    assert "SMTPException" in log_output
    assert contact_payload["email"] not in log_output
    assert contact_payload["message"] not in log_output


def test_contact_email_zero_delivery_is_logged(client, contact_payload, monkeypatch, contact_logs):
    monkeypatch.setattr("modules.platform.services.EmailMessage.send", lambda self: 0)
    response = client.post("/api/v1/contact", contact_payload, content_type="application/json")
    assert response.status_code == 201
    assert ContactMessage.objects.filter(pk=response.json()["reference"]).exists()
    assert "email notification not sent" in contact_logs.text
