"""S18: konsol platform — MFA staf, peran platform, tanpa kebocoran PII, lifecycle tenant, trial, tarif, dukungan."""
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from modules.audit.models import AuditEvent
from modules.billing.services import current_price
from modules.identity.models import User
from modules.notifications.models import Notification
from modules.platform import mfa
from modules.platform.models import StaffMFA, SupportTicket
from modules.tenants.models import Tenant
from modules.trial.models import TenantTrialEvent
from modules.trial.services import expire_due_trials

from .conftest import mark_platform_mfa
from .test_billing import billing as billing
from .test_payment_security import staff
from .test_payments import ok, post
from .test_payments import patch as http_patch
from .test_payments import scenario as scenario
from .test_portal import portal
from .test_trial import trial_a as trial_a
from .test_wallet import wallet_setup as wallet_setup

PASSWORD = "Platform-Rahasia-2026"


@pytest.fixture(autouse=True)
def mail_settings(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


def platform_client(group="Platform Super Admin", *, mfa_done=True):
    user = User.objects.create_user(email=f"{uuid4().hex[:8]}@umrovia.test", password=PASSWORD, status="ACTIVE", is_staff=True, email_verified_at=timezone.now())
    if group:
        user.groups.add(Group.objects.get(name=group))
    client = Client()
    client.force_login(user)
    if mfa_done:
        mark_platform_mfa(client)
    return client, user


def action(client, tenant, name, reason="Pelanggaran ketentuan layanan", **extra):
    return post(client, f"/api/v1/platform/tenants/{tenant.pk}/{name}", {"reason": reason, **extra})


@pytest.fixture
def prod(scenario):
    s = scenario(environment="production")
    s["tenant"].state = "ACTIVE"
    s["tenant"].save(update_fields=["state"])
    return s


def test_totp_matches_rfc6238_vector():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # "12345678901234567890"
    assert mfa.code_for(secret, now=59) == "287082" and mfa.code_for(secret, now=1111111109) == "081804"


def test_mfa_enrollment_verify_replay_and_recovery(db, settings, monkeypatch):
    # Jam TOTP dikunci: bila langkah 30 detik berganti di tengah tes, "kode yang sama"
    # untuk uji replay menjadi kode langkah berikutnya yang sah, dan tes gagal acak.
    step = mfa.current_step()
    monkeypatch.setattr(mfa, "current_step", lambda now=None: step if now is None else int(now // mfa.STEP))
    client, user = platform_client(mfa_done=False)
    me = ok(client.get("/api/v1/platform/me"))
    assert me["mfa"] == {"enrolled": False, "verified": False, "recovery_codes_left": 0} and "platform.tenant_manage" in me["permissions"]
    assert client.get("/api/v1/platform/overview").json()["code"] == "mfa_required"
    assert post(client, "/api/v1/platform/mfa/setup", {"password": "salah"}).status_code == 400
    secret = ok(post(client, "/api/v1/platform/mfa/setup", {"password": PASSWORD}))["secret"]
    device = StaffMFA.objects.get(user=user)
    assert secret not in device.secret_encrypted  # tersimpan terenkripsi
    assert post(client, "/api/v1/platform/mfa/confirm", {"code": "000000"}).status_code == 400
    confirmed = ok(post(client, "/api/v1/platform/mfa/confirm", {"code": mfa.code_for(secret)}))
    codes = confirmed["recovery_codes"]
    assert len(codes) == 10 and confirmed["mfa"]["verified"] and codes[0] not in json.dumps(StaffMFA.objects.get(user=user).recovery_hashes)
    assert ok(client.get("/api/v1/platform/overview"))["tenants_by_state"]
    assert post(client, "/api/v1/platform/mfa/setup", {"password": PASSWORD}).status_code == 400  # perangkat aktif tidak bisa ditimpa
    # Sesi baru: wajib verifikasi lagi; kode yang sama tidak bisa dipakai ulang.
    fresh = Client()
    fresh.force_login(user)
    assert fresh.get("/api/v1/platform/tenants").json()["code"] == "mfa_required"
    assert post(fresh, "/api/v1/platform/mfa/verify", {"code": mfa.code_for(secret)}).status_code == 400
    assert ok(post(fresh, "/api/v1/platform/mfa/verify", {"recovery_code": codes[0].lower()}))["mfa"]["recovery_codes_left"] == 9
    other = Client()
    other.force_login(user)
    assert post(other, "/api/v1/platform/mfa/verify", {"recovery_code": codes[0]}).status_code == 400  # sekali pakai
    assert ok(post(other, "/api/v1/platform/mfa/verify", {"code": mfa.code_for(secret, now=(step + 1) * mfa.STEP)}))["mfa"]["verified"]
    settings.PLATFORM_MFA_TTL_SECONDS = 0
    assert other.get("/api/v1/platform/overview").json()["code"] == "mfa_required"
    actions = set(AuditEvent.objects.filter(actor=user).values_list("action", flat=True))
    assert {"platform.mfa.setup_denied", "platform.mfa.enrolled", "platform.mfa.failed", "platform.mfa.verified"} <= actions
    call_command("reset_platform_mfa", user.email, reason="Perangkat hilang, diverifikasi via video call")
    assert not StaffMFA.objects.filter(user=user).exists() and AuditEvent.objects.filter(action="platform.mfa.reset").exists()


def test_tenant_roles_never_grant_platform_and_platform_roles_are_scoped(prod):
    tenant = prod["tenant"]
    assert prod["client"].get("/api/v1/platform/overview").status_code == 403  # Owner "*" tenant ≠ platform
    assert prod["client"].get("/api/v1/platform/me").status_code == 403
    nobody, _ = platform_client(group=None)
    assert nobody.get("/api/v1/platform/overview").status_code == 403
    support, _ = platform_client("Platform Support")
    assert support.get("/api/v1/platform/tenants").status_code == 200
    assert support.get("/api/v1/platform/support/tickets").status_code == 200
    assert action(support, tenant, "suspend").status_code == 403
    assert support.get("/api/v1/platform/audit").status_code == 403
    assert support.get("/api/v1/platform/billing/queue").status_code == 403
    billing, _ = platform_client("Platform Billing")
    assert billing.get("/api/v1/platform/billing/queue").status_code == 200
    assert action(billing, tenant, "suspend").status_code == 403
    assert billing.get("/api/v1/platform/support/tickets").status_code == 403
    assert post(billing, "/api/v1/platform/pricing", {"code": "STD-2027", "unit_price_idr": 50_000, "effective_from": (timezone.now() + timedelta(days=30)).isoformat(), "reason": "Tarif tahun depan"}).status_code == 403


def test_platform_responses_contain_no_pilgrim_pii(prod):
    client = prod["client"]
    for index, pilgrim in enumerate(prod["pilgrims"]):
        ok(http_patch(client, f"/api/v1/pilgrims/{pilgrim['id']}", {"identity_number": f"317500000000{index:04d}", "email": f"jamaah{index}@contoh.test", "phone": f"08123450000{index}"}))
    ok(post(client, "/api/v1/support/tickets", {"subject": "Tidak bisa unduh manifest", "category": "TECHNICAL", "body": "Mohon dibantu, tombol unduh tidak bereaksi."}))
    admin, _ = platform_client()
    ticket = SupportTicket.objects.get()
    responses = [admin.get(url) for url in [
        "/api/v1/platform/overview", "/api/v1/platform/tenants", f"/api/v1/platform/tenants/{prod['tenant'].pk}", "/api/v1/platform/trials",
        "/api/v1/platform/audit", "/api/v1/platform/pricing", "/api/v1/platform/support/tickets", f"/api/v1/platform/support/tickets/{ticket.pk}",
    ]]
    assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]
    dump = " ".join(r.content.decode() for r in responses)
    for secret in ["Jamaah 0", "Jamaah 1", "3175000000000000", "jamaah0@contoh.test", "081234500000", "Owner@example.com", "owner@example.com"]:
        assert secret not in dump, secret
    detail = responses[2].json()
    assert detail["owner_email"].startswith("ow•") and detail["usage"]["active_participants"] == 3
    assert AuditEvent.objects.filter(action="platform.tenant.viewed", tenant=prod["tenant"]).count() == 1


def test_suspend_blocks_workspace_and_portal_then_reactivate(prod):
    tenant, client = prod["tenant"], prod["client"]
    pilgrim_client, access_id, _ = portal(prod, 0)
    admin, _ = platform_client()
    assert action(admin, tenant, "suspend", reason="singkat").status_code == 400
    suspended = ok(action(admin, tenant, "suspend"))
    assert suspended["state"] == "SUSPENDED" and suspended["suspension_reason"] == "Pelanggaran ketentuan layanan"
    assert action(admin, tenant, "suspend").status_code == 400
    blocked = client.get("/api/v1/bookings")
    assert blocked.status_code == 403 and blocked.json()["code"] == "tenant_suspended"
    assert post(client, "/api/v1/payments", {}).json()["code"] == "tenant_suspended"
    me = ok(client.get("/api/v1/me"))
    assert me["memberships"][0]["tenant"]["state"] == "SUSPENDED" and me["is_platform_staff"] is False
    assert post(client, "/api/v1/support/tickets", {"subject": "Mengapa ditangguhkan?", "category": "ACCOUNT", "body": "Mohon penjelasan penangguhan."}).status_code == 201
    assert ok(pilgrim_client.get("/api/v1/portal/me"))["results"] == []
    assert pilgrim_client.get(f"/api/v1/portal/accesses/{access_id}/documents").status_code == 404
    restored = ok(action(admin, tenant, "reactivate", reason="Klarifikasi diterima, akses dipulihkan"))
    assert restored["state"] == "ACTIVE" and restored["suspended_at"] is None
    assert client.get("/api/v1/bookings").status_code == 200
    assert len(ok(pilgrim_client.get("/api/v1/portal/me"))["results"]) == 1
    assert set(AuditEvent.objects.filter(tenant=tenant, action__startswith="platform.tenant.").values_list("action", flat=True)) >= {"platform.tenant.suspended", "platform.tenant.reactivated"}


def test_trial_conversion_does_not_lift_suspension(trial_a):
    tenant, trial = trial_a
    admin, _ = platform_client()
    ok(action(admin, tenant, "suspend"))
    trial.ends_at = timezone.now() - timedelta(minutes=1)
    trial.save(update_fields=["ends_at"])
    assert expire_due_trials() == 1
    tenant.refresh_from_db()
    assert tenant.state == "SUSPENDED" and tenant.state_before_suspension == "ACTIVE"
    assert ok(action(admin, tenant, "reactivate", reason="Pemeriksaan selesai tanpa temuan"))["state"] == "ACTIVE"


def test_termination_requires_a_second_admin(prod):
    tenant, client = prod["tenant"], prod["client"]
    first, first_user = platform_client()
    second, _ = platform_client()
    assert action(first, tenant, "termination").status_code == 400  # harus ditangguhkan dulu
    ok(action(first, tenant, "suspend"))
    request = ok(action(first, tenant, "termination", reason="Permintaan tertulis pemilik usaha"))
    assert action(first, tenant, "termination").status_code == 400  # satu pengajuan terbuka
    assert action(first, tenant, "reactivate", reason="Coba aktifkan kembali sekarang").status_code == 400
    decide = f"/api/v1/platform/tenants/{tenant.pk}/termination/{request['id']}/decide"
    assert post(first, decide, {"decision": "approve", "reason": "Saya sendiri menyetujui"}).status_code == 403
    approved = ok(post(second, decide, {"decision": "approve", "reason": "Dokumen permintaan sudah diverifikasi"}))
    assert approved["status"] == "APPROVED" and approved["requested_by"].startswith(first_user.email[:2])
    tenant.refresh_from_db()
    assert tenant.state == "TERMINATED" and tenant.terminated_at
    assert client.get("/api/v1/bookings").json()["code"] == "tenant_terminated"
    assert action(second, tenant, "reactivate", reason="Tidak boleh setelah diakhiri").status_code == 400
    assert post(second, decide, {"decision": "reject", "reason": "Sudah diputuskan sebelumnya"}).status_code == 400


def test_trial_list_and_extension(trial_a):
    tenant, trial = trial_a
    admin, _ = platform_client()
    rows = ok(admin.get("/api/v1/platform/trials"))["results"]
    assert [row["slug"] for row in rows] == [tenant.slug]
    url = f"/api/v1/platform/trials/{tenant.pk}/extend"
    assert post(admin, url, {"days": 0, "reason": "Butuh waktu migrasi data"}).status_code == 400
    assert post(admin, url, {"days": 5, "reason": "pendek"}).status_code == 400
    before = trial.ends_at
    extended = ok(post(admin, url, {"days": 5, "reason": "Butuh waktu migrasi data dari sistem lama"}))
    assert extended["status"] == "EXTENDED"
    trial.refresh_from_db()
    assert trial.ends_at - before == timedelta(days=5)
    assert TenantTrialEvent.objects.filter(tenant=tenant, type="EXTENDED").count() == 1
    assert admin.get("/api/v1/platform/trials?status=BOGUS").status_code == 400


def test_pricing_versions_are_future_only(db):
    admin, _ = platform_client()
    before = current_price()
    url = "/api/v1/platform/pricing"
    rows = ok(admin.get(url))["results"]
    assert any(row["current"] for row in rows)
    past = {"code": "STD-OLD", "unit_price_idr": 40_000, "effective_from": (timezone.now() - timedelta(days=1)).isoformat(), "reason": "Coba ubah tarif lampau"}
    assert post(admin, url, past).status_code == 400
    future = {**past, "code": "STD-2027", "effective_from": (timezone.now() + timedelta(days=60)).isoformat(), "reason": "Penyesuaian tarif tahun 2027"}
    scheduled = ok(post(admin, url, future))["results"]
    assert next(row for row in scheduled if row["code"] == "STD-2027")["scheduled"]
    assert post(admin, url, future).status_code == 400  # kode unik
    assert current_price().pk == before.pk


def test_support_ticket_thread_internal_notes_and_isolation(prod, tenant_b):
    sales = staff(prod["tenant"], "Sales")
    assert post(sales, "/api/v1/support/tickets", {"subject": "Hi", "category": "OTHER", "body": "Pendek sekali ya"}).status_code == 400
    ticket = ok(post(sales, "/api/v1/support/tickets", {"subject": "Saldo wallet belum masuk", "category": "BILLING", "body": "Transfer kemarin belum tercatat."}))
    assert ticket["number"].startswith("SUP-") and ticket["status"] == "OPEN" and len(ticket["messages"]) == 1
    agent, agent_user = platform_client("Platform Support")
    listing = ok(agent.get("/api/v1/platform/support/tickets?status=active"))
    assert listing["count"] == 1 and listing["results"][0]["tenant"]["slug"] == prod["tenant"].slug
    base = f"/api/v1/platform/support/tickets/{ticket['id']}"
    ok(post(agent, f"{base}/messages", {"body": "Cek mutasi bank platform dulu.", "internal": True}))
    replied = ok(post(agent, f"{base}/messages", {"body": "Sudah kami cek, mohon kirim referensi transfer."}))
    assert replied["status"] == "WAITING_TENANT" and replied["assigned_to"].startswith(agent_user.email[:2])
    assert "diagnosis" in ok(agent.get(base))
    tenant_view = ok(sales.get(f"/api/v1/support/tickets/{ticket['id']}"))
    assert [m["author"] for m in tenant_view["messages"]][1:] == ["Tim Umrovia"] and all(not m["internal"] for m in tenant_view["messages"])
    email = Notification.objects.without_tenant_guard().get(template_key="support.replied")
    assert email.recipient_type == "USER" and ticket["number"] in email.subject and not email.subject.startswith("[DEMO]")
    assert ok(post(sales, f"/api/v1/support/tickets/{ticket['id']}/messages", {"body": "Referensi: TRF-001 tanggal kemarin"}))["status"] == "OPEN"
    assert ok(post(sales, f"/api/v1/support/tickets/{ticket['id']}/resolve"))["status"] == "RESOLVED"
    assert ok(http_patch(agent, base, {"priority": "HIGH"}))["priority"] == "HIGH"
    other = staff(tenant_b, "Owner")
    assert other.get(f"/api/v1/support/tickets/{ticket['id']}").status_code == 404
    assert ok(other.get("/api/v1/support/tickets"))["count"] == 0
    assert post(other, f"/api/v1/support/tickets/{ticket['id']}/messages", {"body": "Bukan tiket saya"}).status_code == 404


def test_overview_and_billing_queue_aggregates(billing):
    from modules.billing.models import SaaSCharge

    from .test_billing import cancel_booking, fund, pay
    from .test_wallet import topup

    s = billing
    s["tenant"].refresh_from_db()
    fund(s, 50_000)
    pay(s)  # DP terverifikasi → satu charge Rp50.000 terpotong
    pending_topup = topup(s, 75_000)
    cancel_booking(s)  # refund SaaS hanya untuk peserta yang dibatalkan
    charge = SaaSCharge.objects.without_tenant_guard().get()
    ok(post(s["client"], f"/api/v1/wallet/charges/{charge.pk}/refund-request", {"reason": "Jamaah batal sebelum berangkat"}))
    Tenant.objects.create(slug="travel-c", legal_name="PT C", display_name="Travel C", state="SUSPENDED")
    admin, _ = platform_client()
    overview = ok(admin.get("/api/v1/platform/overview"))
    assert overview["tenants_by_state"]["SUSPENDED"] == 1
    assert overview["revenue_month_idr"] == 50_000 and overview["wallet_liability_idr"] == 0
    assert overview["topups_awaiting"] == 1 and overview["refunds_awaiting"] == 1
    billing_staff, _ = platform_client("Platform Billing")
    queue = ok(billing_staff.get("/api/v1/platform/billing/queue"))
    assert [t["amount_idr"] for t in queue["topups"]] == [75_000] and queue["topups"][0]["id"] == pending_topup["id"]
    [refund] = queue["refunds"]
    assert refund["booking_code"] == s["travel"]["booking"]["code"] and refund["amount_idr"] == 50_000
    dump = json.dumps(queue).lower()
    assert "jamaah 0" not in dump and "owner@example.com" not in dump  # email hanya tersamar


def test_create_platform_staff_command(db, monkeypatch):
    monkeypatch.setenv("PLATFORM_STAFF_PASSWORD", "Staf-Platform-Kuat-2026")
    call_command("create_platform_staff", "support@umrovia.test", role="Platform Support", name="Tim Support")
    user = User.objects.get(email="support@umrovia.test")
    assert user.is_staff and user.status == "ACTIVE" and user.email_verified_at and not user.is_superuser
    assert user.has_perm("platform.support_manage") and not user.has_perm("platform.tenant_manage")
    assert AuditEvent.objects.filter(action="platform.staff.granted").exists()
    monkeypatch.setenv("PLATFORM_STAFF_PASSWORD", "pendek")
    with pytest.raises(Exception, match="minimal 12"):
        call_command("create_platform_staff", "baru@umrovia.test", role="Platform Billing")
