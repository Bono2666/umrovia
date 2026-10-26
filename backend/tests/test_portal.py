"""S14: portal jamaah — undangan, object-level permission, upload aman, signed download."""
import re
import time
from datetime import timedelta
from smtplib import SMTPException
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client
from django.utils import timezone

from modules.audit.models import AuditEvent
from modules.identity.models import User
from modules.pilgrims.models import PilgrimDocument
from modules.portal.models import PortalAccess, PortalInvite
from modules.tenants.models import TenantEnvironment

from .test_payment_security import staff
from .test_payments import ok, post
from .test_payments import patch as http_patch
from .test_payments import scenario as scenario

PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PASSWORD = "Rahasia-Portal-2026"


@pytest.fixture(autouse=True)
def private_media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture
def travel(scenario):
    """Produksi: booking grup 3 jamaah dengan invoice terbit."""
    return scenario(environment="production")


def invite(s, index=0, email=None):
    pilgrim = s["pilgrims"][index]
    mail.outbox.clear()
    response = post(s["client"], f"/api/v1/pilgrims/{pilgrim['id']}/portal", {"email": email or f"jamaah{index}@example.test"})
    assert response.status_code == 201, response.content
    return re.search(r"token=([\w.\-]+)", mail.outbox[-1].body).group(1)


def accept(token, client=None, password=PASSWORD):
    client = client or Client()
    response = post(client, "/api/v1/portal/accept-invite", {"token": token, "password": password, "full_name": "Ahmad Jamaah"})
    return client, response


def portal(s, index=0):
    client, response = accept(invite(s, index))
    assert response.status_code == 200, response.content
    me = ok(client.get("/api/v1/portal/me"))["results"]
    return client, me[0]["access_id"], me[0]


def upload(client, access_id, kind="passport", content=PDF, name="paspor.pdf"):
    csrf = client.get("/api/v1/auth/csrf").json()["csrfToken"]
    return client.post(f"/api/v1/portal/accesses/{access_id}/documents", {"kind": kind, "file": SimpleUploadedFile(name, content)}, HTTP_X_CSRFTOKEN=csrf)


def test_invite_accept_creates_verified_portal_account(travel):
    token = invite(travel)
    assert "/portal/undangan?token=" in mail.outbox[-1].body and mail.outbox[-1].to == ["jamaah0@example.test"]
    info = ok(Client().get(f"/api/v1/portal/invites/inspect?token={token}"))
    assert info["valid"] and not info["account_exists"] and info["travel_name"] and "@example.test" in info["email"]
    assert "jamaah0@" not in info["email"]  # masked
    assert accept(token, password="123")[1].status_code == 400  # weak password rejected, invite still open
    client, response = accept(token)
    assert response.status_code == 200
    user = User.objects.get(email="jamaah0@example.test")
    assert user.status == "ACTIVE" and user.email_verified_at is not None
    me = ok(client.get("/api/v1/me"))
    assert me["memberships"] == [] and me["portal_access_count"] == 1
    assert ok(Client().get(f"/api/v1/portal/invites/inspect?token={token}"))["code"] == "used"
    assert accept(token, client=Client())[1].status_code == 400  # one-time
    assert AuditEvent.objects.filter(action="portal.invite.accepted").count() == 1


def test_existing_account_must_log_in_as_invited_email(travel, user):
    token = invite(travel, 1, email=user.email)
    _, response = accept(token)
    assert response.status_code == 403 and response.json()["code"] == "login_required"
    other = staff(travel["tenant"], "Sales")
    assert accept(token, client=other)[1].status_code == 403  # wrong account
    _, response = accept(token, client=travel["client"])  # owner happens to be the pilgrim
    assert response.status_code == 200
    assert PortalAccess.objects.get(user=user).pilgrim_id.hex == travel["pilgrims"][1]["id"].replace("-", "")


def test_reinvite_revokes_old_link_and_invalid_tokens_rejected(travel):
    first = invite(travel)
    second = invite(travel)
    assert ok(Client().get(f"/api/v1/portal/invites/inspect?token={first}"))["code"] == "revoked"
    assert accept(first)[1].status_code == 400
    for bad in ["", "not-a-token", f"{uuid4()}.forged", second[:-3] + "xyz"]:
        assert Client().get(f"/api/v1/portal/invites/inspect?token={bad}").status_code == 400
    with patch("modules.portal.services.timezone.now", return_value=timezone.now() + timedelta(days=8)):
        assert ok(Client().get(f"/api/v1/portal/invites/inspect?token={second}"))["code"] == "expired"


def test_overview_shows_only_own_participant_in_group_booking(travel):
    client, access_id, me = portal(travel)
    names = {p["name"] for p in travel["pilgrims"]}
    assert me["profile"]["name"] == travel["pilgrims"][0]["name"]
    booking = me["bookings"][0]
    assert booking["code"] == travel["booking"]["code"] and booking["participant_status"] == "AWAITING_DP"
    line = next(row for row in travel["invoice"]["lines"] if row["pilgrim_name"] == travel["pilgrims"][0]["name"])
    assert booking["payment"]["amount_idr"] == line["amount_idr"] and booking["payment"]["paid_idr"] == 0
    assert booking["payment"]["group_invoice"] and booking["payment"]["invoice_id"] is None
    body = client.get("/api/v1/portal/me").content.decode()
    for other in names - {me["profile"]["name"]}:
        assert other not in body  # POR02: no other pilgrim data
    # Group invoice PDF and other people's access are not reachable.
    assert client.get(f"/api/v1/portal/accesses/{access_id}/invoices/{travel['invoice']['id']}/pdf").status_code == 404
    other_client, other_access, _ = portal(travel, 1)
    assert client.get(f"/api/v1/portal/accesses/{other_access}/documents").status_code == 404
    assert other_client.get(f"/api/v1/portal/accesses/{access_id}/documents").status_code == 404
    assert client.get(f"/api/v1/portal/accesses/{uuid4()}/documents").status_code == 404


def test_solo_booking_payments_and_pdfs(travel):
    s = travel
    pilgrim = ok(post(s["client"], "/api/v1/pilgrims", {"name": "Solo Jamaah", "email": "solo@example.test"}))
    booking = ok(post(s["client"], "/api/v1/bookings", {"departure": s["departure"]["id"], "participants": [pilgrim["id"]], "room_types": {pilgrim["id"]: "QUAD"}}))
    ok(post(s["client"], f"/api/v1/bookings/{booking['id']}/transition", {"target": "RESERVED"}))
    invoice = ok(post(s["client"], f"/api/v1/bookings/{booking['id']}/issue-invoice"))
    payment = ok(post(s["client"], "/api/v1/payments", {"invoice": invoice["id"], "amount_idr": 5_000_000, "kind": "DP", "method": "CASH", "received_at": timezone.now().isoformat(), "reference": f"REF-{uuid4().hex[:8]}", "allocations": [{"booking_participant_id": invoice["lines"][0]["participant_id"], "amount_idr": 5_000_000}]}))
    ok(post(s["client"], f"/api/v1/payments/{payment['id']}/verify"))
    mail.outbox.clear()
    ok(post(s["client"], f"/api/v1/pilgrims/{pilgrim['id']}/portal", {}))  # defaults to pilgrim email
    token = re.search(r"token=([\w.\-]+)", mail.outbox[-1].body).group(1)
    client, _ = accept(token)
    me = ok(client.get("/api/v1/portal/me"))["results"][0]
    row = me["bookings"][0]
    assert row["payment"]["paid_idr"] == 5_000_000 and row["payment"]["invoice_id"] == invoice["id"]
    assert row["receipts"][0]["downloadable"] and row["receipts"][0]["amount_idr"] == 5_000_000
    pdf = client.get(f"/api/v1/portal/accesses/{me['access_id']}/invoices/{invoice['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-") and "no-store" in pdf["Cache-Control"]
    receipt = client.get(f"/api/v1/portal/accesses/{me['access_id']}/receipts/{row['receipts'][0]['id']}/pdf")
    assert receipt.status_code == 200


def test_upload_review_reupload_history(travel):
    client, access_id, _ = portal(travel)
    first = upload(client, access_id)
    assert first.status_code == 201 and first.json()["version"] == 1 and first.json()["status"] == "UPLOADED"
    doc = PilgrimDocument.objects.without_tenant_guard().get(pk=first.json()["id"])
    assert doc.object_key.startswith(f"tenants/{travel['tenant'].pk}/environments/production/pilgrims/") and doc.object_key.endswith(".pdf")
    review = http_patch(travel["client"], f"/api/v1/pilgrims/{travel['pilgrims'][0]['id']}/documents/{doc.pk}", {"status": "REJECTED", "reason": "Foto buram"})
    assert review.status_code == 200, review.content
    items = {row["kind"]: row for row in ok(client.get(f"/api/v1/portal/accesses/{access_id}/documents"))["results"]}
    assert items["passport"]["latest"]["status"] == "REJECTED" and items["passport"]["latest"]["reason"] == "Foto buram"
    second = upload(client, access_id, content=PNG, name="paspor.png")
    assert second.json()["version"] == 2  # POR01 history kept
    http_patch(travel["client"], f"/api/v1/pilgrims/{travel['pilgrims'][0]['id']}/documents/{second.json()['id']}", {"status": "APPROVED"})
    items = {row["kind"]: row for row in ok(client.get(f"/api/v1/portal/accesses/{access_id}/documents"))["results"]}
    assert [h["version"] for h in items["passport"]["history"]] == [2, 1] and not items["passport"]["can_upload"]
    assert upload(client, access_id).status_code == 409  # approved stays approved


@pytest.mark.parametrize("content,name", [
    (b"MZ\x90\x00 executable", "virus.pdf"),
    (b"hello world", "notes.txt"),
    (b"%PDF-1.4\n<< /OpenAction << /S /JavaScript /JS (app.alert(1)) >> >>", "active.pdf"),
    (b"", "empty.pdf"),
])
def test_upload_rejects_unsafe_files(travel, content, name):
    client, access_id, _ = portal(travel)
    assert upload(client, access_id, content=content, name=name).status_code == 400
    assert upload(client, access_id, kind="visa-palsu").status_code == 400
    assert PilgrimDocument.objects.without_tenant_guard().count() == 0


def test_upload_size_limit(travel, settings):
    settings.PILGRIM_DOCUMENT_MAX_MB = 1
    client, access_id, _ = portal(travel)
    assert upload(client, access_id, content=PDF + b"0" * (1024 * 1024)).status_code == 400


def test_signed_download_bound_expiring_and_rechecked(travel):
    client, access_id, _ = portal(travel)
    doc = upload(client, access_id).json()
    path = ok(post(client, f"/api/v1/portal/accesses/{access_id}/documents/{doc['id']}/download-url"))["path"]
    response = client.get(path)
    assert response.status_code == 200 and response.content == PDF
    assert response["X-Content-Type-Options"] == "nosniff" and "attachment" in response["Content-Disposition"]
    assert travel["client"].get(path).status_code == 404  # bound to the requesting user
    assert Client().get(path).status_code in (401, 403)
    assert client.get(path[:-4] + "abcd").status_code == 404  # tampered
    later = time.time() + 601
    with patch("django.core.signing.time.time", return_value=later):
        assert client.get(path).status_code == 403  # SEC02 expired
    # Revocation is re-checked even for a still-valid link.
    access = PortalAccess.objects.get(pk=access_id)
    ok(post(travel["client"], f"/api/v1/pilgrims/{travel['pilgrims'][0]['id']}/portal/revoke", {"access_id": str(access.pk)}))
    assert client.get(path).status_code == 404
    assert ok(client.get("/api/v1/portal/me"))["results"] == []
    assert client.get(f"/api/v1/portal/accesses/{access_id}/documents").status_code == 404
    assert AuditEvent.objects.filter(action="pilgrim_documents.downloaded").count() == 1


def test_staff_upload_and_review_download(travel):
    s = travel
    pilgrim_id = s["pilgrims"][2]["id"]
    csrf = s["client"].get("/api/v1/auth/csrf").json()["csrfToken"]
    response = s["client"].post(f"/api/v1/pilgrims/{pilgrim_id}/documents/upload", {"kind": "ktp", "file": SimpleUploadedFile("ktp.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 32)}, HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 201 and response.json()["object_key"].endswith(".jpg")
    path = ok(post(s["client"], f"/api/v1/pilgrims/{pilgrim_id}/documents/{response.json()['id']}/download-url"))["path"]
    downloaded = s["client"].get(path)
    assert downloaded.status_code == 200 and downloaded["Content-Type"] == "image/jpeg"
    reader = staff(s["tenant"], "Operations")  # has pilgrims.read
    assert reader.get(path).status_code == 404  # token belongs to the owner session
    assert post(reader, f"/api/v1/pilgrims/{pilgrim_id}/portal", {"email": "x@example.test"}).status_code == 403  # no pilgrims.write


def test_profile_contact_update_only(travel):
    client, access_id, _ = portal(travel)
    updated = ok(http_patch(client, f"/api/v1/portal/accesses/{access_id}/profile", {"phone": "0812-3456-7890", "address": "Jl. Haji No. 1"}))
    assert updated["phone"] == "+6281234567890" and updated["address"] == "Jl. Haji No. 1"
    assert http_patch(client, f"/api/v1/portal/accesses/{access_id}/profile", {"name": "Nama Lain"}).status_code == 400
    assert http_patch(client, f"/api/v1/portal/accesses/{access_id}/profile", {"phone": "12"}).status_code == 400


def test_staff_portal_status_and_invite_email_failure(travel):
    s = travel
    pilgrim_id = s["pilgrims"][0]["id"]
    status = ok(s["client"].get(f"/api/v1/pilgrims/{pilgrim_id}/portal"))
    assert status == {"accesses": [], "pending_invite": None}
    invite(s)
    status = ok(s["client"].get(f"/api/v1/pilgrims/{pilgrim_id}/portal"))
    assert status["pending_invite"]["email"] == "jamaah0@example.test"
    ok(post(s["client"], f"/api/v1/pilgrims/{pilgrim_id}/portal/revoke", {"invite_id": status["pending_invite"]["id"]}))
    assert ok(s["client"].get(f"/api/v1/pilgrims/{pilgrim_id}/portal"))["pending_invite"] is None
    with patch("modules.portal.services.send_mail", side_effect=SMTPException("down")):
        response = post(s["client"], f"/api/v1/pilgrims/{pilgrim_id}/portal", {"email": "y@example.test"})
    assert response.status_code == 502
    assert PortalInvite.objects.without_tenant_guard().filter(email="y@example.test").count() == 0  # rolled back


def test_read_only_demo_blocks_portal_writes(travel):
    client, access_id, _ = portal(travel)
    TenantEnvironment.objects.filter(tenant=travel["tenant"], environment="production").update(state="READ_ONLY")
    assert upload(client, access_id).status_code == 403
    assert http_patch(client, f"/api/v1/portal/accesses/{access_id}/profile", {"address": "x"}).status_code == 403


def test_portal_invite_table_enforces_rls(db):
    with connection.cursor() as cursor:
        cursor.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname='portal_portalinvite'")
        assert cursor.fetchone() == (True, True)
