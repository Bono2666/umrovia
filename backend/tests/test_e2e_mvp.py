"""S19 / Spec §14.3 E2E: signup → 20 dummy → convert → top-up → booking → DP verified → charge → receipt →
upload dokumen → manifest → berangkat → laporan. Satu skenario lewat API publik, seperti pengguna sungguhan."""
import re
from datetime import timedelta

import pytest
from django.core import mail
from django.test import Client
from django.utils import timezone

from modules.platform import integrity

from .pdf_fonts import assert_poppins_only
from .test_payments import ok, post
from .test_payments import patch as http_patch
from .test_platform_console import platform_client
from .test_portal import PDF, accept, upload

PASSWORD = "Kata-Sandi-Travel-2026"


@pytest.fixture(autouse=True)
def e2e_settings(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.WALLET_MANUAL_BANK_NAME = "BANK PLATFORM"
    settings.WALLET_MANUAL_ACCOUNT_NAME = "PT Umrovia"
    settings.WALLET_MANUAL_ACCOUNT_NUMBER = "000123456"


def token(message):
    return re.search(r"token=([\w.\-]+)", message.body).group(1)


@pytest.mark.django_db(transaction=False)
def test_mvp_end_to_end_flow():
    owner = Client()
    # 1. Signup + verifikasi email → workspace trial.
    assert post(owner, "/api/v1/auth/register", {"email": "owner@amanah.test", "password": PASSWORD, "travel_name": "PT Amanah Haramain", "slug": "amanah-haramain", "agree_terms": True}).status_code == 201
    assert ok(post(owner, "/api/v1/auth/verify-email", {"token": token(mail.outbox[-1])}))["status"] == "verified"
    ok(post(owner, "/api/v1/auth/login", {"email": "owner@amanah.test", "password": PASSWORD}))
    me = ok(owner.get("/api/v1/me"))
    tenant_id = me["memberships"][0]["tenant"]["id"]
    assert me["memberships"][0]["tenant"]["state"] == "TRIAL"

    # 2. Trial: 20 booking dummy, ke-21 ditolak (TR02); tanpa biaya.
    for index in range(20):
        ok(post(owner, "/api/v1/trial/demo-bookings", {"label": f"Demo {index}"}))
    assert post(owner, "/api/v1/trial/demo-bookings", {"label": "Demo 21"}).json()["code"] == "TRIAL_QUOTA_EXCEEDED"

    # 3. Konversi ke produksi tanpa tagihan (TR08/TR09).
    ok(post(owner, "/api/v1/trial/convert", {"confirm": True}))
    assert ok(owner.get("/api/v1/me"))["memberships"][0]["tenant"]["state"] == "ACTIVE"
    assert ok(owner.get("/api/v1/wallet"))["balance_idr"] == 0

    # 4. Top-up SaaS Wallet Rp100.000, diverifikasi petugas billing platform (ber-MFA).
    topup = ok(post(owner, "/api/v1/wallet/topups", {"amount_idr": 100_000}))
    ok(post(owner, f"/api/v1/wallet/topups/{topup['id']}/submit", {"payment_reference": "TRF-E2E-1", "evidence_ref": "restricted://bukti-e2e"}))
    billing, _ = platform_client("Platform Billing")
    ok(post(billing, f"/api/v1/platform/tenants/{tenant_id}/wallet/topups/{topup['id']}/settle", {"amount_idr": 100_000, "provider_txn_id": "MUTASI-E2E-1"}))
    assert ok(owner.get("/api/v1/wallet"))["balance_idr"] == 100_000

    # 5. Master data: rekening, paket per kamar, keberangkatan, dua jamaah.
    bank = ok(post(owner, "/api/v1/bank-accounts", {"bank_name": "BSI", "account_name": "PT Amanah Haramain", "account_number": "7012345678"}))["bank_account"]
    rooms = [{"room_type": "QUAD", "price_idr": 30_000_000}, {"room_type": "DOUBLE", "price_idr": 35_000_000}]
    package = ok(post(owner, "/api/v1/packages", {"name": "Umroh Reguler", "price_idr": 30_000_000, "room_prices": rooms}))
    start = timezone.now() + timedelta(days=45)
    departure = ok(post(owner, "/api/v1/departures", {"package": package["id"], "start_at": start.isoformat(), "end_at": (start + timedelta(days=12)).isoformat(), "city_of_origin": "Jakarta", "seat_capacity": 30}))
    ok(post(owner, f"/api/v1/departures/{departure['id']}/transition", {"target": "OPEN"}))
    pilgrims = [ok(post(owner, "/api/v1/pilgrims", {"name": name, "identity_number": nik, "email": email}))
                for name, nik, email in [("Ahmad Fauzi", "3175000000000001", "fauzi@jamaah.test"), ("Siti Aminah", "3175000000000002", "siti@jamaah.test")]]

    # 6. Booking → reservasi kursi → invoice.
    booking = ok(post(owner, "/api/v1/bookings", {"departure": departure["id"], "participants": [p["id"] for p in pilgrims], "room_types": {pilgrims[0]["id"]: "QUAD", pilgrims[1]["id"]: "DOUBLE"}}))
    ok(post(owner, f"/api/v1/bookings/{booking['id']}/transition", {"target": "RESERVED"}))
    invoice = ok(post(owner, f"/api/v1/bookings/{booking['id']}/issue-invoice"))
    assert invoice["total_idr"] == 65_000_000

    # 7. DP terverifikasi per jamaah → biaya Rp50.000 per jamaah tepat sekali + kuitansi.
    for line in invoice["lines"]:
        payment = ok(post(owner, "/api/v1/payments", {
            "invoice": invoice["id"], "amount_idr": 10_000_000, "kind": "DP", "method": "TRANSFER", "bank_account": bank["id"],
            "received_at": timezone.now().isoformat(), "reference": f"DP-{line['participant_id'][:8]}",
            "allocations": [{"booking_participant_id": line["participant_id"], "amount_idr": 10_000_000}],
        }))
        verified = ok(post(owner, f"/api/v1/payments/{payment['id']}/verify"))
        assert verified["status"] == "VERIFIED" and verified["receipt"]["receipt_no"]
        ok(post(owner, f"/api/v1/payments/{payment['id']}/verify"))  # verifikasi ulang: tidak ada biaya kedua
    wallet = ok(owner.get("/api/v1/wallet"))
    assert wallet["balance_idr"] == 0 and wallet["pending_charge_count"] == 0  # 2 × Rp50.000
    receipt_pdf = owner.get(f"/api/v1/receipts/{verified['receipt']['id']}/pdf").content
    assert receipt_pdf.startswith(b"%PDF-")
    assert_poppins_only(receipt_pdf)

    # 8. Portal jamaah: undangan → unggah paspor → disetujui petugas.
    ok(post(owner, f"/api/v1/pilgrims/{pilgrims[0]['id']}/portal", {"email": "fauzi@jamaah.test"}))
    pilgrim_client, accepted = accept(token(mail.outbox[-1]), password="Portal-Jamaah-2026")
    assert accepted.status_code == 200
    access_id = ok(pilgrim_client.get("/api/v1/portal/me"))["results"][0]["access_id"]
    assert upload(pilgrim_client, access_id, content=PDF).status_code == 201
    document = ok(owner.get(f"/api/v1/pilgrims/{pilgrims[0]['id']}/documents"))["results"][0]
    ok(http_patch(owner, f"/api/v1/pilgrims/{pilgrims[0]['id']}/documents/{document['id']}", {"status": "APPROVED"}))

    # 9. Konfirmasi → siap → manifest terbit → berangkat.
    for target in ["CONFIRMED", "DOCUMENT_PROCESS", "READY_TO_DEPART"]:
        ok(post(owner, f"/api/v1/bookings/{booking['id']}/transition", {"target": target}))
    ok(post(owner, f"/api/v1/departures/{departure['id']}/manifest/publish"))
    manifest_pdf = owner.get(f"/api/v1/departures/{departure['id']}/manifest/versions/1/pdf").content
    assert manifest_pdf.startswith(b"%PDF-")
    assert_poppins_only(manifest_pdf)
    for target in ["READY", "DEPARTED"]:
        ok(post(owner, f"/api/v1/departures/{departure['id']}/transition", {"target": target}))
    ok(post(owner, f"/api/v1/bookings/{booking['id']}/transition", {"target": "DEPARTED"}))

    # 10. Laporan: angka cocok dengan transaksi; wallet terpisah dari kas travel; integritas utuh.
    window = f"?from={(timezone.localdate() - timedelta(days=1)).isoformat()}&to={(timezone.localdate() + timedelta(days=60)).isoformat()}"
    finance = {k["key"]: k["value"] for k in ok(owner.get(f"/api/v1/reports/finance{window}"))["kpis"]}
    assert finance["invoiced"] == 65_000_000 and finance["received"] == 20_000_000 and finance["outstanding"] == 45_000_000
    saas = {k["key"]: k["value"] for k in ok(owner.get(f"/api/v1/reports/saas{window}"))["kpis"]}
    assert saas["topups"] == 100_000 and saas["charges"] == 100_000 and saas["balance"] == 0
    operational = ok(owner.get(f"/api/v1/reports/operational{window}"))
    [row] = next(s for s in operational["sections"] if s["key"] == "departures")["rows"]
    assert row["participants"] == 2 and row["dp_received"] == 2 and row["departed"] == 2 and row["manifest"] == "v1"
    result = integrity.run()
    assert result["ok"], [c for c in result["checks"] if not c["ok"]]
