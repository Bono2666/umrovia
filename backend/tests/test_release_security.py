"""S19: gate keamanan rilis — setting produksi, host/CSRF/CORS, header, log tanpa PII, integritas data."""
import json
import logging
import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from django.core.management import call_command
from django.test import Client, override_settings

from modules.payments.models import TravelInvoice
from modules.platform import integrity

from .test_payments import ok, post, record
from .test_payments import patch as http_patch
from .test_payments import scenario as scenario

BACKEND = Path(__file__).resolve().parents[1]


def production_env(**overrides):
    env = {
        **os.environ, "DJANGO_SETTINGS_MODULE": "config.settings.production", "SECRET_KEY": secrets.token_urlsafe(50),
        "PII_ENCRYPTION_KEY": Fernet.generate_key().decode(), "ALLOWED_HOSTS": "api.umrovia.com",
    }
    env.update(overrides)
    return {key: value for key, value in env.items() if value is not None}


def manage(*args, env):
    return subprocess.run([sys.executable, "manage.py", *args], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)


def test_production_settings_pass_deploy_check():
    result = manage("check", "--deploy", "--fail-level", "ERROR", env=production_env())
    assert result.returncode == 0, result.stderr[-2000:]
    security = {line.split(")")[0].split("(")[-1] for line in (result.stdout + result.stderr).splitlines() if "(security." in line}
    assert security <= {"security.W004"}, security  # HSTS 0 = rollout bertahap (didokumentasikan)


@pytest.mark.parametrize("missing", [{"SECRET_KEY": None}, {"PII_ENCRYPTION_KEY": None}, {"ALLOWED_HOSTS": "localhost,127.0.0.1"}])
def test_production_settings_fail_fast_without_secrets(missing):
    result = manage("check", env=production_env(**missing))
    assert result.returncode != 0


@override_settings(ALLOWED_HOSTS=["api.umrovia.com"])
def test_unknown_host_header_rejected(db):
    assert Client(HTTP_HOST="evil.example").get("/api/v1/health/").status_code == 400
    assert Client(HTTP_HOST="api.umrovia.com").get("/api/v1/health/").status_code == 200


def test_csrf_enforced_for_session_writes(scenario, user):
    scenario(environment="production")
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(user)
    body = json.dumps({"subject": "Tanpa token CSRF", "category": "OTHER", "body": "Harus ditolak oleh server."})
    assert strict.post("/api/v1/support/tickets", body, content_type="application/json").status_code == 403
    token = strict.get("/api/v1/auth/csrf").json()["csrfToken"]
    assert strict.post("/api/v1/support/tickets", body, content_type="application/json", HTTP_X_CSRFTOKEN=token).status_code == 201


def test_cors_allows_only_configured_origins(db):
    client = Client()
    allowed = client.options("/api/v1/health/", HTTP_ORIGIN="http://localhost:3000", HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET")
    assert allowed["Access-Control-Allow-Origin"] == "http://localhost:3000"
    denied = client.options("/api/v1/health/", HTTP_ORIGIN="https://evil.example", HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET")
    assert "Access-Control-Allow-Origin" not in denied


def test_security_headers_on_api_responses(db):
    response = Client().get("/api/v1/health/")
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["X-Frame-Options"] == "DENY"
    assert response["Referrer-Policy"] == "same-origin"
    assert set(response.json()["checks"]) >= {"database", "cache", "worker", "email_queue"}


def test_logs_never_contain_pilgrim_pii(scenario, caplog, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    caplog.set_level(logging.DEBUG)
    s = scenario(environment="production")
    secrets = ["Jamaah 0", "Jamaah 1", "3175012345678901", "A1234567", "jamaah0@contoh.test", "081299988877"]
    ok(http_patch(s["client"], f"/api/v1/pilgrims/{s['pilgrims'][0]['id']}", {"identity_number": secrets[2], "passport_number": secrets[3], "email": secrets[4], "phone": secrets[5]}))
    payment = ok(record(s, amount=1_000_000))
    ok(post(s["client"], f"/api/v1/payments/{payment['id']}/verify"))  # charge tertunda + notifikasi + audit
    s["client"].get(f"/api/v1/departures/{s['departure']['id']}/manifest/export?file=csv")
    post(s["client"], "/api/v1/payments", {"invoice": "bukan-uuid"})  # jalur error validasi
    logged = " ".join(f"{r.getMessage()} {json.dumps({k: str(v) for k, v in r.__dict__.items()})}" for r in caplog.records)
    assert caplog.records, "harus ada log yang diperiksa"
    for secret in secrets:
        assert secret not in logged, secret


def test_integrity_check_passes_and_detects_tampering(scenario, capsys):
    s = scenario(environment="production")
    ok(post(s["client"], f"/api/v1/payments/{ok(record(s, amount=2_000_000))['id']}/verify"))
    result = integrity.run()
    assert result["ok"], [c for c in result["checks"] if not c["ok"]]
    assert result["counts"]["payments_travelinvoice"] == 1 and result["counts"]["tenants_tenant"] >= 1
    TravelInvoice.objects.without_tenant_guard().update(balance_idr=1)  # simulasi data rusak/restore parsial
    broken = integrity.run()
    failed = [c["name"] for c in broken["checks"] if not c["ok"]]
    assert failed == ["Invoice: total = baris, saldo = total − pembayaran terverifikasi"]
    with pytest.raises(Exception, match="Integritas data gagal"):
        call_command("verify_integrity")
    assert "[GAGAL] Invoice" in capsys.readouterr().out
