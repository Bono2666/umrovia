"""Data fiktif bervolume untuk uji beban (S19).

Jalankan: DATABASE_URL=<db kosong> WALLET_MANUAL_BANK_NAME=X WALLET_MANUAL_ACCOUNT_NAME=X WALLET_MANUAL_ACCOUNT_NUMBER=1 manage.py shell < seed_load.py

Hasil: 1 travel produksi, 4 paket, 24 keberangkatan, 720 jamaah, 240 booking
(3 jamaah), 240 invoice, 120 DP terverifikasi (wallet terisi → biaya terpotong).
Akun: owner@load.test / Load-Test-2026!
"""
import json
import time
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth.models import Group
from django.test import Client
from django.utils import timezone

from modules.identity.models import User
from modules.platform.access import MFA_SESSION_KEY
from modules.tenants.models import Role, Tenant, TenantEnvironment, TenantMembership
from modules.tenants.rbac import DEFAULT_ROLE_PERMISSIONS
from modules.trial.services import convert_trial, start_trial

started = time.time()
now = timezone.now()
owner = User.objects.create_user(email="owner@load.test", password="Load-Test-2026!", full_name="Owner Beban", status="ACTIVE", email_verified_at=now)
tenant = Tenant.objects.create(slug="beban-tour", legal_name="PT Uji Beban", display_name="Beban Tour", phone="+62215550000", state="PROVISIONING")
roles = {name: Role.objects.create(tenant=tenant, name=name, permissions_json=grants) for name, grants in DEFAULT_ROLE_PERMISSIONS.items()}
TenantMembership.objects.without_tenant_guard().create(tenant=tenant, user=owner, role=roles["Owner"], status="ACTIVE")
TenantEnvironment.objects.get_or_create(tenant=tenant, environment="demo", defaults={"state": "ACTIVE"})
start_trial(tenant)
convert_trial(tenant, actor=owner)
c = Client(HTTP_HOST="localhost")
c.force_login(owner)
csrf = c.get("/api/v1/auth/csrf").json()["csrfToken"]


def post(url, body=None, client=c):
    r = client.post("/api/v1" + url, json.dumps(body or {}), content_type="application/json", HTTP_X_CSRFTOKEN=csrf, HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert r.status_code in (200, 201), (url, r.content[:300])
    return r.json()


bank = post("/bank-accounts", {"bank_name": "Bank Syariah Indonesia", "account_name": "PT Uji Beban", "account_number": "7012345678"})["bank_account"]
billing = User.objects.create_user(email="billing@load.test", password="x" * 16, status="ACTIVE", is_staff=True, email_verified_at=now)
billing.groups.add(Group.objects.get(name="Platform Billing"))
pc = Client(HTTP_HOST="localhost")
pc.force_login(billing)
session = pc.session
session[MFA_SESSION_KEY] = time.time()
session.save()
pcsrf = pc.get("/api/v1/auth/csrf").json()["csrfToken"]
topup = post("/wallet/topups", {"amount_idr": 10_000_000})
post(f"/wallet/topups/{topup['id']}/submit", {"payment_reference": "TRF-LOAD", "evidence_ref": "restricted://bukti"})
r = pc.post(f"/api/v1/platform/tenants/{tenant.pk}/wallet/topups/{topup['id']}/settle", json.dumps({"amount_idr": 10_000_000, "provider_txn_id": "BANK-LOAD"}), content_type="application/json", HTTP_X_CSRFTOKEN=pcsrf)
assert r.status_code == 200, r.content

rooms = [{"room_type": r, "price_idr": p} for r, p in [("QUAD", 32_500_000), ("TRIPLE", 34_000_000), ("DOUBLE", 36_500_000)]]
packages = [post("/packages", {"name": f"Umroh {name}", "duration_days": 12, "price_idr": 32_500_000, "room_prices": rooms}) for name in ["Reguler", "Plus Turki", "Ramadhan", "Akhir Tahun"]]
departures = []
for i in range(24):
    dep = post("/departures", {"package": packages[i % 4]["id"], "start_at": (now + timedelta(days=30 + i * 7)).isoformat(), "end_at": (now + timedelta(days=42 + i * 7)).isoformat(), "city_of_origin": ["Jakarta", "Surabaya", "Medan"][i % 3], "seat_capacity": 45})
    post(f"/departures/{dep['id']}/transition", {"target": "OPEN"})
    departures.append(dep)
for i in range(240):
    pilgrims = [post("/pilgrims", {"name": f"Jamaah Beban {i:03d}-{j}", "gender": "male" if j % 2 else "female"}) for j in range(3)]
    booking = post("/bookings", {"departure": departures[i % 24]["id"], "participants": [p["id"] for p in pilgrims], "room_types": {p["id"]: "QUAD" for p in pilgrims}})
    post(f"/bookings/{booking['id']}/transition", {"target": "RESERVED"})
    invoice = post(f"/bookings/{booking['id']}/issue-invoice")
    if i % 2 == 0:
        payment = post("/payments", {"invoice": invoice["id"], "amount_idr": 5_000_000, "kind": "DP", "method": "TRANSFER", "bank_account": bank["id"], "received_at": now.isoformat(), "reference": f"TRF-{i:04d}",
                                     "allocations": [{"booking_participant_id": invoice["lines"][0]["participant_id"], "amount_idr": 5_000_000}]})
        post(f"/payments/{payment['id']}/verify")
print(f"seeded-load {time.time() - started:.0f}s departures={len(departures)}")
