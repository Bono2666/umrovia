"""S06 — fondasi template dokumen (Spec §10.2, POL-09/TR05, baris PDF).

Render HTML invoice/kuitansi: field §10.2, format rupiah integer (§4.4),
escaping anti-XSS, output DEMO (`DEMO-` + watermark), instruksi bayar hanya
nomor masked, `TEMPLATE_VERSION` di footer.
"""
import pytest

from modules.documents.render import (
    TEMPLATE_VERSION,
    TemplateContextError,
    format_idr,
    render_invoice,
    render_receipt,
)

ISSUER = {"legal_name": "PT Travel Nusantara", "address": "Jl. Sudirman 1, Jakarta", "support": "halo@travel.id"}

INVOICE = {
    "invoice_no": "INV-2026-0001",
    "issue_date": "2026-10-22",
    "due_date": "2026-10-29",
    "buyer_name": "Budi Santoso",
    "booking_ref": "BK-2026-0042",
    "lines": [
        {"description": "Paket Umroh Reguler 12 Hari", "amount_idr": 32_500_000},
        {"description": "Biaya pendaftaran", "amount_idr": 500_000},
    ],
    "subtotal_idr": 33_000_000,
    "tax_idr": 0,
    "discount_idr": 1_000_000,
    "grand_total_idr": 32_000_000,
    "paid_idr": 5_000_000,
    "outstanding_idr": 27_000_000,
    "issuer": ISSUER,
}


def test_format_idr_integer_locale():
    assert format_idr(0) == "Rp0"
    assert format_idr(50_000) == "Rp50.000"
    assert format_idr(32_500_000) == "Rp32.500.000"
    with pytest.raises(TemplateContextError):
        format_idr(-1)
    with pytest.raises(TemplateContextError):
        format_idr(1.5)
    with pytest.raises(TemplateContextError):
        format_idr("50000")


def test_invoice_renders_spec_fields_and_totals():
    out = render_invoice(INVOICE, invoice_config={"notes": "Bayar ke rekening resmi."})
    assert out.startswith("<!DOCTYPE html>")
    assert "INV-2026-0001" in out
    assert "PT Travel Nusantara" in out
    assert "Jl. Sudirman 1, Jakarta" in out
    assert "Budi Santoso" in out and "BK-2026-0042" in out
    assert "2026-10-29" in out  # due date (§10.2)
    assert "Rp32.500.000" in out and "Rp27.000.000" in out  # lines + outstanding
    assert "Bayar ke rekening resmi." in out
    assert f"template v{TEMPLATE_VERSION}" in out


def test_invoice_escapes_html_injection():
    ctx = dict(INVOICE, buyer_name="<script>alert(1)</script>")
    out = render_invoice(ctx)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_invoice_demo_prefix_and_watermark():
    ctx = dict(INVOICE, environment="demo")
    out = render_invoice(ctx)
    assert "DEMO-INV-2026-0001" in out
    assert "DOKUMEN DEMO" in out  # watermark jelas (POL-09/TR05)
    out_prod = render_invoice(dict(INVOICE, environment="production"))
    assert "DEMO-INV" not in out_prod
    assert "DOKUMEN DEMO" not in out_prod  # tidak ada elemen watermark di produksi


def test_invoice_bank_instructions_use_masked_only():
    ctx = dict(
        INVOICE,
        bank_accounts=[{"bank_name": "BCA", "account_name": "PT Travel Nusantara", "account_masked": "************1234"}],
    )
    out = render_invoice(ctx)
    assert "************1234" in out
    assert "12345678901234" not in out  # nomor penuh tak pernah muncul (input saja masked)


def test_invoice_missing_required_field_raises():
    ctx = dict(INVOICE)
    del ctx["grand_total_idr"]
    with pytest.raises(TemplateContextError):
        render_invoice(ctx)
    with pytest.raises(TemplateContextError):
        render_invoice(dict(INVOICE, lines=[]))


def test_receipt_renders_spec_fields():
    ctx = {
        "receipt_no": "RCP-2026-0001",
        "verified_date": "2026-10-23",
        "amount_idr": 5_000_000,
        "purpose": "DP booking BK-2026-0042",
        "accepted_via": "Transfer bank BCA",
        "invoice_no": "INV-2026-0001",
        "issuer": ISSUER,
    }
    out = render_receipt(ctx)
    assert "RCP-2026-0001" in out
    assert "Rp5.000.000" in out
    assert "DP booking BK-2026-0042" in out
    assert "Transfer bank BCA" in out
    assert f"template v{TEMPLATE_VERSION}" in out

    demo = render_receipt(dict(ctx, environment="demo"))
    assert "DEMO-RCP-2026-0001" in demo
    assert "DOKUMEN DEMO" in demo

    with pytest.raises(TemplateContextError):
        render_receipt({"receipt_no": "X"})  # issuer & field wajib hilang
