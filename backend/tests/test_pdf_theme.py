"""Semua generator PDF bertema bisa dirender untuk produksi maupun demo, hanya dengan Poppins."""
import pytest

from modules.manifest import printing
from modules.payments.pdf import render_financial_pdf
from modules.reports import export

from .pdf_fonts import assert_poppins_only

ISSUER = {"legal_name": "PT Contoh Wisata", "address": "Jl. Contoh No. 1, Jakarta", "phone": "0812-0000-0000"}
DEPARTURE = {"code": "UMR-01", "package_name": "Umrah 12 Hari", "start_at": "2026-12-10T00:00:00+07:00", "end_at": "2026-12-21T00:00:00+07:00",
             "city_of_origin": "Jakarta", "route": "CGK – JED", "meeting_point": "Terminal 3"}
PERSON = {"name": "Ahmad Fikri", "code": "JMH-0001", "gender": "male", "birth_date": "1980-05-17", "booking_code": "BK-8F3D2A10", "room_type": "QUAD",
          "identity_masked": "************0001", "passport_masked": "*****4567", "phone": "+62812345678901", "participant_status": "CONFIRMED",
          "docs_complete": False, "docs_missing": ["passport"], "payment_status": "partial", "balance_idr": 1_000_000, "address": "Jl. Melati 5"}


def _meta(environment):
    return {"title": "Manifest jamaah", "travel": ISSUER["legal_name"], "demo": environment == "demo", "printed_at": "30 Oktober 2026", "printed_by": "Staf"}


def _documents(environment):
    meta = _meta(environment)
    invoice = {"number": "INV-1", "environment": environment, "issued_at": "2026-10-29T07:05:00+00:00", "timezone": "Asia/Jakarta", "due_at": "2026-11-12T00:00:00+07:00",
               "issuer": ISSUER, "booking_code": "BK-1", "buyer_name": "Ahmad", "branch": "", "gross_idr": 2_000_000, "discount_idr": 100_000, "extra_idr": 0,
               "lines": [{"description": "Ahmad · Umrah", "amount_idr": 1_900_000}], "total_idr": 1_900_000, "paid_idr": 0, "outstanding_idr": 1_900_000,
               "notes": "Catatan", "version": 2, "revision": {"version": 2, "previous_total_idr": 2_000_000, "reason": "Diskon"},
               "bank_accounts": [{"bank_name": "BSI", "account_name": "PT Contoh", "account_masked": "•••• 1234"}]}
    receipt = {**invoice, "number": "KWT-1", "received_at": "2026-10-29T03:00:00+00:00", "invoice_number": "INV-1", "kind": "DP", "method": "TRANSFER",
               "amount_idr": 500_000, "lines": [{"description": "Ahmad · DP", "amount_idr": 500_000}], "verified_by": "Staf"}
    report = {"report": "finance", "title": "Laporan Keuangan", "travel": ISSUER["legal_name"], "environment": environment, "period": {"from": "2026-10-01", "to": "2026-10-31"},
              "as_of": "2026-10-30T03:00:00+00:00", "timezone": "Asia/Jakarta", "filters": {}, "kpis": [{"label": "Kas", "value": 500_000, "type": "money"}],
              "sections": [{"title": "Kas", "columns": [{"key": "a", "label": "Rekening", "type": "text"}, {"key": "b", "label": "Jumlah", "type": "money"}],
                            "rows": [{"a": "BSI", "b": 500_000}], "totals": {"b": 500_000}}],
              "checks": [{"label": "Kas = kuitansi", "ok": True, "detail": "cocok"}]}
    return {
        "invoice": render_financial_pdf(invoice),
        "receipt": render_financial_pdf(receipt, receipt=True),
        "manifest": printing.manifest_pdf(departure=DEPARTURE, rows=[PERSON] * 30, pii=False, meta=meta),
        "forms": printing.registration_forms_pdf(departure=DEPARTURE, people=[PERSON], pii=False, meta=meta, issuer=ISSUER),
        "labels": printing.labels_pdf(departure=DEPARTURE, people=[PERSON] * 3, meta=meta),
        "envelopes": printing.envelopes_pdf(people=[PERSON], meta=meta, issuer=ISSUER),
        "report": export.to_pdf(report, {**meta, "title": "Laporan Keuangan"}, {}),
    }


@pytest.mark.parametrize("environment", ["production", "demo"])
def test_every_pdf_renders_with_theme(environment):
    for name, content in _documents(environment).items():
        assert content.startswith(b"%PDF-"), name
        assert_poppins_only(content)
