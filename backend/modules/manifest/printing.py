"""Dokumen cetak operasional (S15; PRD MOD-12, OPS-04; Spec TR05).

Manifest PDF/XLSX, formulir pendaftaran, label koper dan amplop dibuat lokal
dari data yang sudah difilter dan diizinkan pemanggil. Teks di-escape; tidak
ada aset/URL remote. Dokumen demo selalu ber-watermark "DEMO".
"""
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.documents.render import format_idr
from modules.payments.pdf import document_date

GREEN = colors.HexColor("#0e6b5c")
LINE = colors.HexColor("#d3ddda")
TINT = colors.HexColor("#eaf3ef")
GENDER = {"male": "L", "female": "P"}
PAYMENT = {"paid": "Lunas", "partial": "Sebagian", "unpaid": "Belum bayar"}
PARTICIPANT = {
    "REGISTERED": "Terdaftar", "AWAITING_DP": "Menunggu DP", "DP_VERIFIED_PENDING_CHARGE": "DP diterima",
    "CONFIRMED": "Terkonfirmasi", "READY": "Siap", "DEPARTED": "Berangkat", "COMPLETED": "Selesai",
    "CANCELED": "Batal", "REVIEW_REQUIRED": "Perlu review", "DRAFT": "Draf",
}
DOC_KIND = {"ktp": "KTP", "passport": "Paspor", "photo": "Foto", "kk": "KK", "other": "Lainnya"}
ROOM = {"QUAD": "Quad", "TRIPLE": "Triple", "DOUBLE": "Double", "SINGLE": "Single"}
DL = (220 * mm, 110 * mm)


def _fonts():
    # Dicek per nama: modul invoice dapat sudah mendaftarkan "Umrovia" saja.
    base = Path(reportlab.__file__).parent / "fonts"
    registered = pdfmetrics.getRegisteredFontNames()
    for name, file in [("Umrovia", "Vera.ttf"), ("Umrovia-Bold", "VeraBd.ttf")]:
        if name not in registered:
            pdfmetrics.registerFont(TTFont(name, str(base / file)))
    pdfmetrics.registerFontFamily("Umrovia", normal="Umrovia", bold="Umrovia-Bold", italic="Umrovia", boldItalic="Umrovia-Bold")


def _styles():
    _fonts()
    normal = ParagraphStyle("UmrNormal", fontName="Umrovia", fontSize=9, leading=12)
    return {
        "normal": normal,
        "small": ParagraphStyle("UmrSmall", parent=normal, fontSize=7.5, leading=10, textColor=colors.HexColor("#555b5e")),
        "cell": ParagraphStyle("UmrCell", parent=normal, fontSize=7.5, leading=9.5),
        "bold": ParagraphStyle("UmrBold", parent=normal, fontName="Umrovia-Bold"),
        "head": ParagraphStyle("UmrHead", parent=normal, fontName="Umrovia-Bold", fontSize=7.5, leading=9.5),
        "title": ParagraphStyle("UmrTitle", parent=normal, fontName="Umrovia-Bold", fontSize=16, leading=20, textColor=GREEN),
        "label": ParagraphStyle("UmrLabel", parent=normal, fontName="Umrovia-Bold", fontSize=11, leading=14),
    }


def _mask(value):
    """Nomor tersamar dari server ("************0001") → "•••• 0001" seperti di aplikasi."""
    return value.lstrip("*").join(["•••• ", ""]) if value and value.startswith("*") else value


def _lines(values, style):
    """Baris opsional (alamat/telepon kosong tidak dicetak sebagai tanda strip)."""
    return [_p(value, style) for value in values if value and value != "-"]


def _p(value, style):
    return Paragraph(escape(str(value if value not in (None, "") else "—")).replace("\n", "<br/>"), style)


def _page_decor(meta, *, footer=True):
    """Footer (judul, pencetak, halaman) + watermark DEMO untuk environment demo."""
    def draw(canvas, doc):
        canvas.saveState()
        width, height = canvas._pagesize
        if meta.get("demo"):
            canvas.setFont("Umrovia-Bold", 48)
            canvas.setFillColor(colors.Color(0.85, 0.2, 0.2, alpha=0.12))
            canvas.translate(width / 2, height / 2)
            canvas.rotate(30)
            canvas.drawCentredString(0, 0, "DEMO — BUKAN DOKUMEN RESMI")
            canvas.restoreState()
            canvas.saveState()
        if footer:
            canvas.setFont("Umrovia", 7)
            canvas.setFillColor(colors.HexColor("#6f7377"))
            canvas.drawString(doc.leftMargin, 22, f"{meta['title']} · {meta['travel']} · dicetak {meta['printed_at']} oleh {meta['printed_by']}")
            canvas.drawRightString(width - doc.rightMargin, 22, f"Halaman {doc.page}")
        canvas.restoreState()
    return draw


def print_meta(*, title, travel, environment, actor, zone="Asia/Jakarta"):
    return {
        "title": title, "travel": travel, "demo": environment == "demo",
        "printed_at": document_date(datetime.now().astimezone().isoformat(), zone, with_time=True),
        "printed_by": (getattr(actor, "full_name", "") or getattr(actor, "email", "")) or "sistem",
    }


def _departure_lines(dep, s):
    when = document_date(dep["start_at"])
    if dep.get("end_at"):
        when += f" – {document_date(dep['end_at'])}"
    lines = [f"{dep['package_name']} · {dep['code']}", f"{when} · {dep.get('city_of_origin') or '—'}"]
    extra = " · ".join(filter(None, [dep.get("route"), dep.get("meeting_point") and f"Titik kumpul: {dep['meeting_point']}"]))
    if extra:
        lines.append(extra)
    return [_p(line, s["normal"]) for line in lines]


# ------------------------------------------------------------- manifest --

def _manifest_row(index, row, pii):
    docs = "Lengkap" if row.get("docs_complete") else "Kurang: " + ", ".join(DOC_KIND.get(k, k) for k in row.get("docs_missing", []))
    payment = PAYMENT.get(row.get("payment_status"), "—")
    if row.get("payment_status") and row["payment_status"] != "paid":
        payment += f" · sisa {format_idr(row.get('balance_idr', 0))}"
    return [
        str(index), row["name"], GENDER.get(row.get("gender"), "—"),
        document_date(row["birth_date"]) if row.get("birth_date") else "—",
        row["booking_code"], ROOM.get(row.get("room_type"), row.get("room_type") or "—"),
        row.get("identity_number") if pii else _mask(row.get("identity_masked")),
        row.get("passport_number") if pii else _mask(row.get("passport_masked")),
        row.get("phone"), PARTICIPANT.get(row.get("participant_status"), row.get("participant_status")),
        docs, payment,
    ]


MANIFEST_HEADERS = ["No", "Nama", "L/P", "Tgl lahir", "Booking", "Kamar", "NIK", "Paspor", "Telepon", "Status", "Dokumen", "Pembayaran"]


def manifest_pdf(*, departure, rows, pii, meta, version=None) -> bytes:
    s = _styles()
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=30, bottomMargin=40, title=f"Manifest {departure['code']}", author=meta["travel"])
    stamp = (f"Versi {version['version_no']} · diterbitkan {version['published_at']} oleh {version['published_by']}" if version
             else "Belum diterbitkan sebagai versi — salinan kerja saat dicetak")
    story = [_p(f"Manifest Jamaah — {meta['travel']}", s["title"]), Spacer(1, 4), *_departure_lines(departure, s),
             _p(f"{len(rows)} jamaah · {stamp}" + (" · BERISI DATA PRIBADI LENGKAP — rahasia" if pii else " · identitas tersamar"), s["small"]), Spacer(1, 8)]
    data = [[_p(h, s["head"]) for h in MANIFEST_HEADERS]]
    data += [[_p(value, s["cell"]) for value in _manifest_row(i, row, pii)] for i, row in enumerate(rows, 1)]
    widths = [26, 114, 26, 60, 70, 44, 58, 58, 74, 62, 100, 94]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TINT), ("LINEBELOW", (0, 0), (-1, 0), 0.75, GREEN),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table if rows else _p("Belum ada jamaah aktif pada keberangkatan ini.", s["normal"]))
    decor = _page_decor(meta)
    doc.build(story, onFirstPage=decor, onLaterPages=decor)
    return output.getvalue()


def manifest_xlsx(*, departure, rows, pii, meta) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Manifest"
    sheet.append([f"Manifest Jamaah — {meta['travel']}" + (" (DEMO)" if meta.get("demo") else "")])
    sheet.append([f"{departure['package_name']} · {departure['code']} · {document_date(departure['start_at'])} · {departure.get('city_of_origin') or ''}"])
    sheet.append([f"Dicetak {meta['printed_at']} oleh {meta['printed_by']} · " + ("data pribadi lengkap — rahasia" if pii else "identitas tersamar")])
    sheet.append([])
    headers = MANIFEST_HEADERS + ["Tagihan (Rp)", "Terbayar (Rp)", "Sisa (Rp)"]
    sheet.append(headers)
    for i, row in enumerate(rows, 1):
        values = _manifest_row(i, row, pii)
        values[0] = i
        sheet.append(values + [row.get("amount_idr", 0), row.get("paid_idr", 0), row.get("balance_idr", 0)])
    sheet["A1"].font = Font(bold=True, size=14, color="0E6B5C")
    for cell in sheet[5]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="EAF3EF")
    for row in sheet.iter_rows(min_row=6):
        for cell in row:
            # Teks yang diawali =, +, -, @ dipaksa string agar tidak menjadi formula.
            if isinstance(cell.value, str):
                cell.data_type = "s"
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for letter, width in zip("ABCDEFGHIJKLMNO", [5, 28, 5, 16, 14, 9, 20, 14, 17, 15, 24, 22, 14, 14, 14], strict=True):
        sheet.column_dimensions[letter].width = width
    sheet.freeze_panes = "A6"
    output = BytesIO()
    book.save(output)
    return output.getvalue()


# --------------------------------------------------- formulir & label/amplop --

def registration_forms_pdf(*, departure, people, pii, meta, issuer) -> bytes:
    """Satu halaman per jamaah: data diri, kontak, perjalanan dan tanda tangan."""
    s = _styles()
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=42, rightMargin=42, topMargin=42, bottomMargin=48, title=f"Formulir pendaftaran {departure['code']}", author=meta["travel"])
    story = []
    for index, person in enumerate(people):
        if index:
            story.append(PageBreak())
        rows = [
            ("Nama sesuai paspor", person["name"]), ("Kode jamaah", person["code"]),
            ("Jenis kelamin", {"male": "Laki-laki", "female": "Perempuan"}.get(person.get("gender"), "—")),
            ("Tempat, tanggal lahir", ", ".join(filter(None, [person.get("birth_place"), document_date(person["birth_date"]) if person.get("birth_date") else ""])) or "—"),
            ("NIK", person.get("identity_number") if pii else _mask(person.get("identity_masked"))),
            ("Nomor paspor", person.get("passport_number") if pii else _mask(person.get("passport_masked"))),
            ("Masa berlaku paspor", document_date(person["passport_expires_at"]) if person.get("passport_expires_at") else "—"),
            ("Alamat", person.get("address")), ("Telepon / WhatsApp", person.get("phone")), ("Email", person.get("email")),
            ("Wali / mahram", " · ".join(filter(None, [person.get("guardian_name"), person.get("guardian_relation")])) or "—"),
            ("Kontak darurat", " · ".join(filter(None, [person.get("emergency_contact_name"), person.get("emergency_contact_phone")])) or "—"),
            ("Booking · kamar", f"{person['booking_code']} · {ROOM.get(person.get('room_type'), person.get('room_type') or '—')}"),
        ]
        table = Table([[_p(label, s["small"]), _p(value, s["normal"])] for label, value in rows], colWidths=[130, 380])
        table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        signatures = Table([[_p("Jamaah", s["small"]), _p("Petugas travel", s["small"])], [Spacer(1, 52), Spacer(1, 52)], [_p(f"( {person['name']} )", s["normal"]), _p("( ............................................ )", s["normal"])]], colWidths=[255, 255])
        story += [
            _p("Formulir Pendaftaran Jamaah", s["title"]), _p(issuer["legal_name"], s["bold"]),
            _p(" · ".join(filter(None, [issuer.get("address") if issuer.get("address") != "-" else "", issuer.get("phone")])), s["small"]),
            Spacer(1, 10), *_departure_lines(departure, s), Spacer(1, 10), table, Spacer(1, 14),
            _p("Dengan menandatangani formulir ini, jamaah menyatakan data di atas benar dan menyetujui ketentuan perjalanan dari travel.", s["small"]),
            Spacer(1, 18), KeepTogether(signatures),
        ]
    if not people:
        story.append(_p("Belum ada jamaah aktif pada keberangkatan ini.", s["normal"]))
    decor = _page_decor(meta)
    doc.build(story, onFirstPage=decor, onLaterPages=decor)
    return output.getvalue()


def labels_pdf(*, departure, people, meta) -> bytes:
    """Label koper/nama A4: 2 kolom × 7 baris (≈ 95 × 36 mm)."""
    s = _styles()
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=10 * mm, rightMargin=10 * mm, topMargin=12 * mm, bottomMargin=14 * mm, title=f"Label jamaah {departure['code']}", author=meta["travel"])
    cells = []
    for person in people:
        cells.append([
            _p(person["name"], s["label"]),
            _p(f"{person['booking_code']} · {ROOM.get(person.get('room_type'), person.get('room_type') or '')}".strip(" ·"), s["small"]),
            _p(f"{departure['package_name']} · {document_date(departure['start_at'])}", s["small"]),
            _p(f"{meta['travel']}{' · ' + person['phone'] if person.get('phone') else ''}", s["small"]),
        ])
    if len(cells) % 2:
        cells.append("")
    grid = [cells[i:i + 2] for i in range(0, len(cells), 2)]
    story = [_p("Belum ada jamaah aktif pada keberangkatan ini.", s["normal"])]
    if grid:
        table = Table(grid, colWidths=[95 * mm, 95 * mm], rowHeights=[36 * mm] * len(grid))
        table.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.4, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
        story = [table]
    decor = _page_decor(meta)
    doc.build(story, onFirstPage=decor, onLaterPages=decor)
    return output.getvalue()


def envelopes_pdf(*, people, meta, issuer) -> bytes:
    """Amplop DL (220 × 110 mm) per jamaah: pengirim travel, penerima jamaah."""
    s = _styles()
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=DL, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=10 * mm, bottomMargin=10 * mm, title="Amplop jamaah", author=meta["travel"])
    story = []
    for index, person in enumerate(people):
        if index:
            story.append(PageBreak())
        sender = [_p(issuer["legal_name"], s["bold"]), *_lines([issuer.get("address"), issuer.get("phone")], s["small"])]
        recipient = [_p("Kepada Yth.", s["small"]), _p(person["name"], s["label"]), _p(person.get("address") or "Alamat belum diisi", s["normal"]), *_lines([person.get("phone")], s["small"])]
        story += [Table([[sender, ""]], colWidths=[110 * mm, 86 * mm]), Spacer(1, 10 * mm), Table([["", recipient]], colWidths=[70 * mm, 126 * mm])]
    if not people:
        story.append(_p("Belum ada jamaah aktif pada keberangkatan ini.", s["normal"]))
    decor = _page_decor(meta, footer=False)
    doc.build(story, onFirstPage=decor, onLaterPages=decor)
    return output.getvalue()
