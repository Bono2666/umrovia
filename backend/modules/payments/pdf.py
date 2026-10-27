"""PDF lokal dari snapshot; teks di-escape, tidak mengambil URL/aset remote."""
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.documents.render import TEMPLATE_VERSION, format_idr

MONTHS = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]


def document_date(value, zone="Asia/Jakarta", *, with_time=False):
    date = datetime.fromisoformat(value)
    if date.tzinfo is not None:
        date = date.astimezone(ZoneInfo(zone))
    label = f"{date.day} {MONTHS[date.month]} {date.year}"
    return f"{label} · {date:%H:%M} ({zone})" if with_time else label


def render_financial_pdf(snapshot, *, receipt=False):
    if "Umrovia" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Umrovia", str(Path(reportlab.__file__).parent / "fonts" / "Vera.ttf")))
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("UmroviaNormal", parent=styles["Normal"], fontName="Umrovia", fontSize=10, leading=15, spaceAfter=8)
    heading = ParagraphStyle("UmroviaHeading", parent=normal, fontSize=20, leading=26, textColor=colors.HexColor("#0e6b5c"))
    small = ParagraphStyle("UmroviaSmall", parent=normal, fontSize=8, leading=12)

    def text(value, style=normal):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)

    output = BytesIO()
    number = snapshot["number"]
    title = "KUITANSI" if receipt else "INVOICE"
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=42, rightMargin=42, topMargin=48, bottomMargin=60, title=f"{title} {number}", author=snapshot["issuer"]["legal_name"])
    version = snapshot.get("version", 1)
    story = [text(f"{title} {number}" + (f" · Revisi {version}" if not receipt and version > 1 else ""), heading), text(snapshot["issuer"]["legal_name"]), text(snapshot["issuer"].get("address", "-"), small)]
    zone = snapshot.get("timezone", "Asia/Jakarta")
    if snapshot.get("branch"):
        story.append(text(f"Cabang: {snapshot['branch']}", small))
    story.extend([Spacer(1, 12), text(f"Booking: {snapshot['booking_code']}"), text(f"Pelanggan: {snapshot['buyer_name']}"), text(f"{'Tanggal verifikasi' if receipt else 'Tanggal terbit'}: {document_date(snapshot['issued_at'], zone, with_time=True)}")])
    if receipt:
        method = {"CASH": "Tunai", "TRANSFER": "Transfer bank"}.get(snapshot["method"], snapshot["method"])
        kind = {"DP": "DP", "INSTALLMENT": "Cicilan", "BALANCE": "Pelunasan"}.get(snapshot["kind"], snapshot["kind"])
        story.extend([text(f"Tanggal penerimaan: {document_date(snapshot['received_at'], zone, with_time=True)}"), text(f"Invoice: {snapshot['invoice_number']}"), text(f"Metode penerimaan: {method}"), text(f"Untuk: {kind}"), text(f"Diverifikasi oleh: {snapshot['verified_by']}"), Spacer(1, 12), text(f"Diterima: {format_idr(snapshot['amount_idr'])}", heading)])
    else:
        story.append(text(f"Jatuh tempo: {document_date(snapshot['due_at'])}"))
    rows = [[text("Uraian"), text("Jumlah (IDR)")]]
    rows.extend([[text(line["description"]), text(format_idr(line["amount_idr"]))] for line in snapshot["lines"]])
    table = Table(rows, colWidths=[355, 155], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf3ef")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.HexColor("#0e6b5c")),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#d3ddda")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([Spacer(1, 12), table])
    if not receipt:
        if snapshot.get("discount_idr") or snapshot.get("extra_idr"):
            story.extend([Spacer(1, 10), text(f"Harga paket: {format_idr(snapshot['gross_idr'])}")])
            if snapshot.get("discount_idr"):
                story.append(text(f"Diskon: -{format_idr(snapshot['discount_idr'])}"))
            if snapshot.get("extra_idr"):
                story.append(text(f"Biaya tambahan: {format_idr(snapshot['extra_idr'])}"))
        story.extend([Spacer(1, 16), text(f"Total tagihan: {format_idr(snapshot['total_idr'])}", heading)])
        if snapshot.get("revision"):
            story.append(text(f"Revisi {snapshot['revision']['version']} menggantikan versi sebelumnya (total {format_idr(snapshot['revision']['previous_total_idr'])}). Alasan: {snapshot['revision']['reason']}", small))
        story.extend([text(f"Terbayar saat terbit: {format_idr(snapshot['paid_idr'])}"), text(f"Sisa tagihan saat terbit: {format_idr(snapshot['outstanding_idr'])}"), text("Sisa tagihan terkini dapat dilihat pada halaman Invoice.", small)])
        for account in snapshot.get("bank_accounts", []):
            story.append(text(f"{account['bank_name']} · {account['account_name']} · {account['account_masked']}", small))
        if snapshot.get("notes"):
            story.append(text(snapshot["notes"], small))
    if snapshot["issuer"].get("phone"):
        story.append(text(f"Bantuan pembayaran: {snapshot['issuer']['phone']}", small))
    if snapshot["environment"] == "demo":
        story.extend([Spacer(1, 16), text("DOKUMEN DEMO - TIDAK BERLAKU SEBAGAI BUKTI PEMBAYARAN", small)])

    def decorate(canvas, document):
        canvas.saveState()
        canvas.setFont("Umrovia", 8)
        canvas.setFillColor(colors.HexColor("#6f7377"))
        canvas.drawString(42, 30, f"Dokumen travel · Umrovia · Template {TEMPLATE_VERSION}")
        canvas.drawRightString(A4[0] - 42, 30, f"Halaman {document.page}")
        if snapshot["environment"] == "demo":
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(35)
            canvas.setFillColor(colors.Color(0.7, 0.1, 0.1, alpha=0.10))
            canvas.setFont("Umrovia", 70)
            canvas.drawCentredString(0, 0, "DEMO")
        canvas.restoreState()

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return output.getvalue()
