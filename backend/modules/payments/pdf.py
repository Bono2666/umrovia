"""PDF lokal dari snapshot; teks di-escape, tidak mengambil URL/aset remote."""
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Spacer

from modules.documents import pdf_theme as theme
from modules.documents.render import TEMPLATE_VERSION, format_idr

PAYMENT_KIND = {"DP": "DP", "INSTALLMENT": "Cicilan", "BALANCE": "Pelunasan"}
MONTHS = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]


def document_date(value, zone="Asia/Jakarta", *, with_time=False):
    date = datetime.fromisoformat(value)
    if date.tzinfo is not None:
        date = date.astimezone(ZoneInfo(zone))
    label = f"{date.day} {MONTHS[date.month]} {date.year}"
    return f"{label} · {date:%H:%M} ({zone})" if with_time else label


def _split_time(value, zone):
    """"29 Oktober 2026 · 14:05 (Asia/Jakarta)" → tanggal + jam sebagai keterangan sel."""
    day, _, time = document_date(value, zone, with_time=True).partition(" · ")
    return day, time


def render_financial_pdf(snapshot, *, receipt=False):
    s = theme.styles()
    output = BytesIO()
    number, issuer = snapshot["number"], snapshot["issuer"]
    zone = snapshot.get("timezone", "Asia/Jakarta")
    demo = snapshot["environment"] == "demo"
    title = "KUITANSI" if receipt else "INVOICE"
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=42, rightMargin=42, topMargin=44, bottomMargin=58, title=f"{title} {number}", author=issuer["legal_name"])
    width = doc.width
    version = snapshot.get("version", 1)
    badges = [("Terverifikasi", "success")] if receipt else ([(f"Revisi {version}", "warning")] if version > 1 else [])
    if demo:
        badges.append(("Demo", "danger"))
    story = [theme.kop(s, width=width, name=issuer["legal_name"], lines=[issuer.get("address"), issuer.get("phone") and f"Telepon {issuer['phone']}"],
                       kind="Kuitansi pembayaran" if receipt else "Invoice", number=number, badges=badges), Spacer(1, 16)]
    story += _receipt_body(snapshot, s, width, zone) if receipt else _invoice_body(snapshot, s, width, zone)
    if demo:
        story += [Spacer(1, 12), theme.notice(s, "DOKUMEN DEMO — TIDAK BERLAKU SEBAGAI BUKTI PEMBAYARAN", width, kind="danger")]
    decor = theme.page_decor(footer_left=f"{issuer['legal_name']} · dibuat dengan Umrovia · template {TEMPLATE_VERSION}", demo=demo)
    theme.build(doc, story, decor)
    return output.getvalue()


def _lines_table(snapshot, s, width, *, total=None):
    rows = [[str(index), line["description"], format_idr(line["amount_idr"])] for index, line in enumerate(snapshot["lines"], 1)]
    totals = [" ", total[0], total[1]] if total else None
    return theme.data_table(s, ["No", "Uraian", "Jumlah"], rows, [28, width - 28 - 130, 130], numeric={2}, totals=totals, body="body", pad=6)


def _invoice_body(snapshot, s, width, zone):
    issued, issued_time = _split_time(snapshot["issued_at"], zone)
    cells = [("Ditagihkan kepada", snapshot["buyer_name"], snapshot.get("branch") and f"Cabang {snapshot['branch']}"),
             ("Kode booking", snapshot["booking_code"]), ("Tanggal terbit", issued, issued_time),
             ("Jatuh tempo", document_date(snapshot["due_at"]))]
    story = [theme.info_grid(s, cells, width, cols=4), Spacer(1, 14), _lines_table(snapshot, s, width), Spacer(1, 14)]

    summary = []
    if snapshot.get("discount_idr") or snapshot.get("extra_idr"):
        summary.append(("Harga paket", format_idr(snapshot["gross_idr"]), ""))
        if snapshot.get("discount_idr"):
            summary.append(("Diskon", f"−{format_idr(snapshot['discount_idr'])}", ""))
        if snapshot.get("extra_idr"):
            summary.append(("Biaya tambahan", format_idr(snapshot["extra_idr"]), ""))
    summary += [("Total tagihan", format_idr(snapshot["total_idr"]), "grand"),
                ("Terbayar saat terbit", format_idr(snapshot["paid_idr"]), ""),
                ("Sisa tagihan saat terbit", format_idr(snapshot["outstanding_idr"]), "strong")]

    pay_width = width * 0.5
    accounts = []
    for account in snapshot.get("bank_accounts", []):
        accounts += [theme.p(account["bank_name"], s["bold"]), theme.p(f"{account['account_name']} · {account['account_masked']}", s["body"]), Spacer(1, 5)]
    accounts = accounts or [theme.p("Hubungi travel untuk instruksi pembayaran.", s["body"]), Spacer(1, 5)]
    accounts.append(theme.p("Sisa tagihan terkini dapat dilihat pada halaman Invoice.", s["small"]))
    if snapshot["issuer"].get("phone"):
        accounts.append(theme.p(f"Bantuan pembayaran: {snapshot['issuer']['phone']}", s["small"]))
    story.append(theme.columns([pay_width, width - pay_width - 14],
                               [theme.card(s, "Pembayaran ke rekening", accounts, pay_width), theme.totals_box(s, summary, width - pay_width - 14)], gap=14))
    if snapshot.get("revision"):
        revision = snapshot["revision"]
        story += [Spacer(1, 12), theme.notice(s, f"Revisi {revision['version']} menggantikan versi sebelumnya (total {format_idr(revision['previous_total_idr'])}). Alasan: {revision['reason']}", width, kind="warning")]
    if snapshot.get("notes"):
        story += [Spacer(1, 12), theme.card(s, "Catatan", theme.p(snapshot["notes"], s["body"]), width)]
    return story


def _receipt_body(snapshot, s, width, zone):
    method = {"CASH": "Tunai", "TRANSFER": "Transfer bank"}.get(snapshot["method"], snapshot["method"])
    kind = PAYMENT_KIND.get(snapshot["kind"], snapshot["kind"])
    received, received_time = _split_time(snapshot["received_at"], zone)
    verified, verified_time = _split_time(snapshot["issued_at"], zone)
    hero = theme.info_grid(s, [("Jumlah diterima", theme.p(format_idr(snapshot["amount_idr"]), s["amount"]), f"Untuk {kind} · {method}"),
                               ("Invoice", snapshot["invoice_number"], f"Booking {snapshot['booking_code']}")], width, cols=2)
    hero.setStyle([("BACKGROUND", (0, 0), (0, 0), theme.TINT)])
    cells = [("Diterima dari", snapshot["buyer_name"]), ("Tanggal penerimaan", received, received_time),
             ("Tanggal verifikasi", verified, verified_time), ("Diverifikasi oleh", snapshot["verified_by"])]
    story = [hero, Spacer(1, 12), theme.info_grid(s, cells, width, cols=4), Spacer(1, 16), theme.p("Rincian alokasi", s["h2"]), Spacer(1, 6),
             _lines_table(snapshot, s, width, total=("Total diterima", format_idr(snapshot["amount_idr"]))), Spacer(1, 10),
             theme.p("Kuitansi diterbitkan otomatis oleh sistem setelah pembayaran diverifikasi.", s["small"])]
    if snapshot["issuer"].get("phone"):
        story.append(theme.p(f"Bantuan pembayaran: {snapshot['issuer']['phone']}", s["small"]))
    return story
