"""Template dokumen — Spec §10.2 + baris PDF (HTML-to-PDF + versi template).

Fondasi S06 ("template basics"): render **HTML** invoice & kuitansi dari
konteks dict. Model invoice/kuitansi, penomoran, dan endpoint PDF menyusul
S11 (butuh data booking/payment) — sprint ini hanya mesin template-nya,
unit-test dengan konteks sintetis.

Keputusan:
- Semua nilai konteks melewati `html.escape` (anti-XSS di HTML/PDF).
- Nominal = integer rupiah diformat `Rp50.000` (§4.4); negatif/non-int ditolak.
- Output DEMO: nomor diberi prefix `DEMO-` + watermark jelas (POL-09, TR05,
  §4.3 "dokumen demo menggunakan watermark jelas").
- `TEMPLATE_VERSION` ditempel di footer setiap dokumen (versi template).
- Instruksi bayar memakai `account_masked` saja — renderer TIDAK PERNAH
  menerima nomor rekening penuh (§5.3; caller wajib mengirim masked).
"""
import html

TEMPLATE_VERSION = "2026-10-2"

_WATERMARK = "DOKUMEN DEMO — TIDAK BERLAKU SEBAGAI BUKTI PEMBAYARAN"


class TemplateContextError(ValueError):
    """Konteks template tidak lengkap/tidak valid."""


def format_idr(amount) -> str:
    """Format integer rupiah → `Rp50.000` (locale id-ID, tanpa desimal)."""
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise TemplateContextError(f"Nominal harus integer rupiah: {amount!r}")
    if amount < 0:
        raise TemplateContextError(f"Nominal tidak boleh negatif: {amount}")
    return f"Rp{amount:,}".replace(",", ".")


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _require(ctx: dict, key: str):
    value = ctx.get(key)
    if value in (None, ""):
        raise TemplateContextError(f"Konteks wajib: '{key}'")
    return value


def _require_issuer(ctx: dict) -> dict:
    issuer = _require(ctx, "issuer")
    if not isinstance(issuer, dict):
        raise TemplateContextError("Konteks wajib: 'issuer' berupa objek")
    _require(issuer, "legal_name")
    _require(issuer, "address")
    return issuer


def _document_no(no: str, demo: bool) -> str:
    return f"DEMO-{no}" if demo else str(no)


def _base_styles(primary_color: str) -> str:
    return f"""
    body {{ font-family: 'Poppins', Arial, sans-serif; color: #10221f; margin: 2rem; }}
    h1 {{ font-size: 1.25rem; margin: 0 0 .25rem; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
    th, td {{ border: 1px solid #e2e8e6; padding: .5rem .75rem; text-align: left; }}
    th {{ background: #f7f9f8; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .muted {{ color: #5b6b67; font-size: .85rem; }}
    .totals td {{ border: none; padding: .25rem .75rem .25rem 0; text-align: right; }}
    .grand {{ font-weight: 700; border-top: 2px solid {primary_color}; }}
    .brand {{ color: {primary_color}; }}
    .watermark {{ position: fixed; top: 40%; left: 10%; width: 80%;
        transform: rotate(-24deg); text-align: center; font-size: 2rem;
        font-weight: 800; color: rgba(185, 28, 28, 0.18); z-index: 9; }}
    .footer {{ margin-top: 2rem; border-top: 1px solid #e2e8e6; padding-top: .5rem; }}
    """.strip()


def _watermark_tag(demo: bool) -> str:
    if not demo:
        return ""
    return f'<div class="watermark">{_esc(_WATERMARK)}</div>'


def _issuer_block(issuer: dict) -> str:
    support = issuer.get("support") or issuer.get("phone") or issuer.get("email") or "-"
    return (
        f"<div><strong class='brand'>{_esc(issuer['legal_name'])}</strong><br>"
        f"<span class='muted'>{_esc(issuer['address'])}</span><br>"
        f"<span class='muted'>Bantuan: {_esc(support)}</span></div>"
    )


def _payment_instructions(bank_accounts: list) -> str:
    if not bank_accounts:
        return ""
    rows = "".join(
        f"<tr><td>{_esc(acc.get('bank_name'))}</td>"
        f"<td>{_esc(acc.get('account_name'))}</td>"
        f"<td class='num'>{_esc(acc.get('account_masked'))}</td></tr>"
        for acc in bank_accounts
    )
    return (
        "<h2 style='font-size:1rem'>Instruksi pembayaran</h2>"
        "<table><thead><tr><th>Bank</th><th>Atas nama</th>"
        "<th class='num'>Nomor rekening</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        '<p class="muted">Transfer sesuai nominal tagihan; unggah bukti '
        "transfer setelah masuk ke menu Pembayaran.</p>"
    )


def _doc_head(title: str, styles: str, demo: bool) -> str:
    return (
        "<!DOCTYPE html><html lang='id'><head><meta charset='utf-8'>"
        f"<title>{_esc(title)}</title><style>{styles}</style></head><body>"
        f"{_watermark_tag(demo)}"
    )


def _doc_footer() -> str:
    return (
        f"<div class='footer muted'>Dokumen dibuat oleh Umrovia · "
        f"template v{_esc(TEMPLATE_VERSION)}</div>"
        "</body></html>"
    )


def render_invoice(ctx: dict, *, branding: dict | None = None,
                   invoice_config: dict | None = None) -> str:
    """Render HTML invoice travel (Spec §10.2).

    Wajib: invoice_no, issue_date, due_date, buyer_name, booking_ref,
    lines[{description, amount_idr}], subtotal_idr, grand_total_idr,
    paid_idr, outstanding_idr, issuer{legal_name, address}.
    Opsional: tax_idr/discount_idr (default 0), bank_accounts (masked),
    environment ("demo" → prefix DEMO- + watermark), invoice_config.notes.
    """
    if not isinstance(ctx, dict):
        raise TemplateContextError("Konteks invoice harus berupa objek")
    issuer = _require_issuer(ctx)
    lines = _require(ctx, "lines")
    if not isinstance(lines, list) or not lines:
        raise TemplateContextError("Konteks wajib: 'lines' berupa daftar non-kosong")
    for line in lines:
        _require(line, "description")
        if "amount_idr" not in line:
            raise TemplateContextError("Setiap baris butuh 'amount_idr'")

    demo = str(ctx.get("environment", "production")).lower() == "demo"
    primary = (branding or {}).get("primary_color") or "#0e6b5c"
    invoice_no = _document_no(_require(ctx, "invoice_no"), demo)

    line_rows = "".join(
        f"<tr><td>{_esc(line['description'])}</td>"
        f"<td class='num'>{format_idr(line['amount_idr'])}</td></tr>"
        for line in lines
    )
    subtotal = ctx.get("subtotal_idr", sum(line["amount_idr"] for line in lines))
    tax = ctx.get("tax_idr", 0)
    discount = ctx.get("discount_idr", 0)

    styles = _base_styles(primary)
    body = [
        "<div style='display:flex;justify-content:space-between;gap:2rem'>",
        _issuer_block(issuer),
        "<div style='text-align:right'>",
        f"<h1>INVOICE <span class='brand'>{_esc(invoice_no)}</span></h1>",
        f"<div class='muted'>Tanggal terbit: {_esc(_require(ctx, 'issue_date'))}</div>",
        f"<div class='muted'>Jatuh tempo: {_esc(_require(ctx, 'due_date'))}</div>",
        "</div></div>",
        "<p><strong>Pembeli:</strong> " + _esc(_require(ctx, "buyer_name")) + "<br>",
        "<strong>Booking:</strong> " + _esc(_require(ctx, "booking_ref")) + "</p>",
        "<table><thead><tr><th>Uraian</th><th class='num'>Jumlah</th></tr></thead>"
        f"<tbody>{line_rows}</tbody></table>",
        "<table class='totals' style='width:auto;margin-left:auto'>",
        f"<tr><td>Subtotal</td><td>{format_idr(subtotal)}</td></tr>",
        f"<tr><td>Diskon</td><td>{format_idr(discount)}</td></tr>",
        f"<tr><td>Pajak</td><td>{format_idr(tax)}</td></tr>",
        f"<tr class='grand'><td>Tagihan</td><td>{format_idr(_require(ctx, 'grand_total_idr'))}</td></tr>",
        f"<tr><td>Sudah dibayar</td><td>{format_idr(_require(ctx, 'paid_idr'))}</td></tr>",
        f"<tr><td>Sisa tagihan</td><td>{format_idr(_require(ctx, 'outstanding_idr'))}</td></tr>",
        "</table>",
    ]
    notes = (invoice_config or {}).get("notes")
    if notes:
        body.append(f"<p class='muted'>{_esc(notes)}</p>")
    body.append(_payment_instructions(ctx.get("bank_accounts") or []))
    body.append(_doc_footer())
    return _doc_head(f"Invoice {invoice_no}", styles, demo) + "".join(body)


def render_receipt(ctx: dict, *, branding: dict | None = None) -> str:
    """Render HTML kuitansi pembayaran (Spec §10.2).

    Wajib: receipt_no, verified_date, amount_idr, purpose, accepted_via,
    invoice_no, issuer{legal_name, address}. Opsional: environment demo.
    """
    if not isinstance(ctx, dict):
        raise TemplateContextError("Konteks kuitansi harus berupa objek")
    issuer = _require_issuer(ctx)
    demo = str(ctx.get("environment", "production")).lower() == "demo"
    primary = (branding or {}).get("primary_color") or "#0e6b5c"
    receipt_no = _document_no(_require(ctx, "receipt_no"), demo)

    styles = _base_styles(primary)
    body = [
        "<div style='display:flex;justify-content:space-between;gap:2rem'>",
        _issuer_block(issuer),
        "<div style='text-align:right'>",
        f"<h1>KUITANSI <span class='brand'>{_esc(receipt_no)}</span></h1>",
        f"<div class='muted'>Terverima: {_esc(_require(ctx, 'verified_date'))}</div>",
        "</div></div>",
        "<table class='totals' style='width:100%;margin-top:1rem'>",
        f"<tr><td>Tagihan</td><td>{_esc(_require(ctx, 'invoice_no'))}</td></tr>",
        f"<tr><td>Untuk</td><td>{_esc(_require(ctx, 'purpose'))}</td></tr>",
        f"<tr><td>Diterima melalui</td><td>{_esc(_require(ctx, 'accepted_via'))}</td></tr>",
        f"<tr class='grand'><td>Nominal diterima</td>"
        f"<td>{format_idr(_require(ctx, 'amount_idr'))}</td></tr>",
        "</table>",
        _doc_footer(),
    ]
    return _doc_head(f"Kuitansi {receipt_no}", styles, demo) + "".join(body)
