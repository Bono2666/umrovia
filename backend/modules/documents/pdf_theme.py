"""Tema PDF Umrovia — gaya template aplikasi: editorial, garis hairline, sudut persegi.

Satu sumber warna, gaya teks dan blok (kop, kartu info, tabel, kotak total, badge,
catatan) untuk semua generator PDF: invoice/kuitansi, dokumen cetak manifest dan
ekspor laporan. Warna = token `globals.css` dashboard: tinta #191b1d, abu #6f7377,
hijau brand #0e6b5c, garis hitam 12 %/32 % dan warna status. Badge meniru
`StatusBadge` (huruf kapital, bingkai tipis, latar tint 10 %).
"""
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import BaseDocTemplate, Flowable, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle

from modules.documents.pdf_fonts import BOLD, REGULAR, register_pdf_fonts

INK = colors.HexColor("#191b1d")
MUTED = colors.HexColor("#6f7377")
PRIMARY = colors.HexColor("#0e6b5c")
TINT = colors.HexColor("#eaf3ef")
LINE = colors.HexColor("#e3e4e4")  # --border: hitam 12 %
LINE_STRONG = colors.HexColor("#b5b6b7")  # --border-strong: hitam 32 %
SURFACE = colors.HexColor("#f7f8f8")  # kepala tabel, kolom label, baris zebra
# (teks, latar 10 %, bingkai 30 %) — sama dengan nada StatusBadge.
TONES = {
    "neutral": (MUTED, SURFACE, LINE_STRONG),
    "primary": (PRIMARY, TINT, colors.HexColor("#b7d3ce")),
    "success": (colors.HexColor("#157347"), colors.HexColor("#e8f1ec"), colors.HexColor("#b9d5c8")),
    "warning": (colors.HexColor("#9a6700"), colors.HexColor("#f5f0e6"), colors.HexColor("#e1d1b3")),
    "danger": (colors.HexColor("#b42318"), colors.HexColor("#f8e9e8"), colors.HexColor("#e8bdba")),
}
CELL_PAD = 8


def styles():
    register_pdf_fonts()
    body = ParagraphStyle("UmrBody", fontName=REGULAR, fontSize=9, leading=13, textColor=INK)
    s = {
        "body": body,
        "bold": body.clone("UmrBold", fontName=BOLD),
        "small": body.clone("UmrSmall", fontSize=7.5, leading=11, textColor=MUTED),
        "label": body.clone("UmrLabel", fontName=BOLD, fontSize=6.5, leading=9, textColor=MUTED, textTransform="uppercase"),
        "cell": body.clone("UmrCell", fontSize=7.5, leading=10),
        "cell-bold": body.clone("UmrCellBold", fontName=BOLD, fontSize=7.5, leading=10),
        "head": body.clone("UmrHead", fontName=BOLD, fontSize=6.5, leading=9, textColor=MUTED, textTransform="uppercase"),
        "issuer": body.clone("UmrIssuer", fontName=BOLD, fontSize=13, leading=17),
        "kind": body.clone("UmrKind", fontName=BOLD, fontSize=7.5, leading=10, textColor=PRIMARY, textTransform="uppercase", alignment=TA_RIGHT),
        "number": body.clone("UmrNumber", fontName=BOLD, fontSize=14, leading=18, alignment=TA_RIGHT),
        "h2": body.clone("UmrH2", fontName=BOLD, fontSize=10.5, leading=14),
        "name": body.clone("UmrName", fontName=BOLD, fontSize=11, leading=14),
        "amount": body.clone("UmrAmount", fontName=BOLD, fontSize=20, leading=25, textColor=PRIMARY),
        "kpi": body.clone("UmrKpi", fontName=BOLD, fontSize=12.5, leading=16),
        "grand": body.clone("UmrGrand", fontName=BOLD, fontSize=11, leading=14, textColor=PRIMARY),
    }
    return s


def right(s, name):
    """Varian rata kanan (angka/nominal) dari gaya `name`, dibuat sekali per dokumen."""
    key = f"{name}-r"
    if key not in s:
        s[key] = s[name].clone(f"{s[name].name}R", alignment=TA_RIGHT)
    return s[key]


def tone(s, name, color):
    key = f"{name}-{color.hexval()}"
    if key not in s:
        s[key] = s[name].clone(f"{s[name].name}{color.hexval()}", textColor=color)
    return s[key]


def p(value, style):
    """Teks biasa (di-escape; baris baru dipertahankan). Kosong → "—"."""
    return Paragraph(escape(str(value if value not in (None, "") else "—")).replace("\n", "<br/>"), style)


LINE_OPS = {"BOX", "OUTLINE", "GRID", "INNERGRID", "LINEABOVE", "LINEBELOW", "LINEBEFORE", "LINEAFTER"}


def squared(commands):
    """Ujung garis persegi: bawaan ReportLab membulat sehingga aksen tebal tampak melengkung.

    Garis tipis memakai ujung "square" (sudut bingkai tertutup rapat); aksen tebal ≥ 1,5 pt
    memakai ujung "butt" agar berhenti tepat di sudut bingkai, tidak menonjol keluar.
    """
    return [(*command, 0 if command[3] >= 1.5 else 2) if command[0] in LINE_OPS and len(command) == 5 else command
            for command in commands]


def _box(data, widths, commands, **kwargs):
    table = Table(data, colWidths=widths, **kwargs)
    table.setStyle(TableStyle(squared(commands)))
    return table


def _padding(left=CELL_PAD, top=6, bottom=7, right_=None):
    return [("LEFTPADDING", (0, 0), (-1, -1), left), ("RIGHTPADDING", (0, 0), (-1, -1), left if right_ is None else right_),
            ("TOPPADDING", (0, 0), (-1, -1), top), ("BOTTOMPADDING", (0, 0), (-1, -1), bottom)]


def badge(s, text, kind="neutral"):
    """Chip status ala StatusBadge: kapital, bingkai tipis, latar tint."""
    fg, bg, border = TONES[kind]
    width = stringWidth(text.upper(), BOLD, 6.5) + 11
    style = tone(s, "label", fg).clone(f"UmrBadge{fg.hexval()}", alignment=TA_CENTER)
    return _box([[Paragraph(escape(text), style)]], [width], [
        ("BOX", (0, 0), (-1, -1), 0.6, border), ("BACKGROUND", (0, 0), (-1, -1), bg),
        *_padding(left=5, top=2, bottom=3),
    ])


def badge_row(s, badges, *, align="RIGHT"):
    items = [badge(s, text, kind) for text, kind in badges]
    cells, widths = [], []
    for index, item in enumerate(items):
        if index:
            cells.append("")
            widths.append(4)
        cells.append(item)
        widths.append(item._colWidths[0])
    return _box([cells], widths, [*_padding(left=0, top=0, bottom=0), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")], hAlign=align)


def kop(s, *, width, name, lines=(), kind, number, badges=(), split=0.58):
    """Kop dokumen: penerbit di kiri; jenis, nomor dan badge di kanan; garis tinta di bawah."""
    left = [p(name, s["issuer"]), *[p(line, s["small"]) for line in lines if line and line != "-"]]
    right_cell = [p(kind, s["kind"]), Spacer(1, 2), p(number, s["number"])]
    if badges:
        right_cell += [Spacer(1, 5), badge_row(s, badges)]
    return _box([[left, right_cell]], [width * split, width * (1 - split)], [
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        *_padding(left=0, top=0, bottom=12), ("LINEBELOW", (0, 0), (-1, 0), 1.2, INK),
    ])


def info_grid(s, cells, width, cols=None):
    """Kartu berbingkai berisi pasangan label kapital + nilai; `cells` = (label, nilai[, keterangan])."""
    cols = cols or len(cells)
    rows = [list(cells[i:i + cols]) for i in range(0, len(cells), cols)]
    rows[-1] += [None] * (cols - len(rows[-1]))

    def cell(item):
        if not item:
            return ""
        label, value, *note = item
        return [p(label, s["label"]), Spacer(1, 2), value if isinstance(value, Flowable) else p(value, s["body"]),
                *[p(text, s["small"]) for text in note if text]]

    return _box([[cell(item) for item in row] for row in rows], [width / cols] * cols, [
        ("BOX", (0, 0), (-1, -1), 0.75, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.75, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), *_padding(top=7, bottom=8),
    ])


def card(s, title, body, width, *, kind="neutral"):
    """Kartu berbingkai dengan baris judul kapital berlatar abu (atau tint nada `kind`)."""
    fg, bg, _ = TONES[kind]
    head_bg = SURFACE if kind == "neutral" else bg
    body = body if isinstance(body, list) else [body]
    return _box([[p(title, tone(s, "label", INK if kind == "neutral" else fg))], [body]], [width], [
        ("BOX", (0, 0), (-1, -1), 0.75, LINE), ("BACKGROUND", (0, 0), (-1, 0), head_bg),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        *_padding(top=6, bottom=7), ("TOPPADDING", (0, 1), (-1, 1), 8), ("BOTTOMPADDING", (0, 1), (-1, 1), 9),
    ])


def form_section(s, title, rows, width, label_width=130):
    """Bagian formulir: judul, lalu baris label (kolom abu) + nilai dalam grid berbingkai."""
    data = [[p(title, tone(s, "label", INK)), ""]] + [[p(label, s["label"]), p(value, s["body"])] for label, value in rows]
    return _box(data, [label_width, width - label_width], [
        ("SPAN", (0, 0), (-1, 0)), ("BOX", (0, 0), (-1, -1), 0.75, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.75, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), TINT), ("BACKGROUND", (0, 1), (0, -1), SURFACE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), *_padding(top=5, bottom=6),
    ])


def data_table(s, header, rows, widths, *, numeric=(), totals=None, zebra=False, body="cell", pad=4, hpad=None):
    """Tabel berbingkai: kepala kapital berlatar abu, garis baris hairline, total bertint."""
    numeric = set(numeric)

    def row(values, name):
        return [value if isinstance(value, Flowable) else p(value, right(s, name) if i in numeric else s[name])
                for i, value in enumerate(values)]

    data = [row(header, "head"), *[row(values, body) for values in rows]]
    commands = [
        ("BOX", (0, 0), (-1, -1), 0.75, LINE_STRONG), ("BACKGROUND", (0, 0), (-1, 0), SURFACE),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, LINE_STRONG), ("LINEBELOW", (0, 1), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), *_padding(left=pad + 2 if hpad is None else hpad, top=pad, bottom=pad + 1),
    ]
    if zebra and rows:
        commands.append(("ROWBACKGROUNDS", (0, 1), (-1, len(rows)), [colors.white, SURFACE]))
    if totals is not None:
        data.append(row(totals, "cell-bold" if body == "cell" else "bold"))
        commands += [("BACKGROUND", (0, -1), (-1, -1), TINT), ("LINEABOVE", (0, -1), (-1, -1), 0.75, PRIMARY)]
    return _box(data, widths, commands, repeatRows=1)


def totals_box(s, rows, width):
    """Ringkasan nominal rata kanan; `rows` = (label, nilai, peran) dengan peran "", "strong" atau "grand"."""
    data, commands = [], [("BOX", (0, 0), (-1, -1), 0.75, LINE), ("LINEBELOW", (0, 0), (-1, -2), 0.5, LINE),
                          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), *_padding(top=6, bottom=7)]
    for index, (label, value, role) in enumerate(rows):
        if role == "grand":
            data.append([p(label, tone(s, "bold", PRIMARY)), p(value, right(s, "grand"))])
            commands += [("BACKGROUND", (0, index), (-1, index), TINT), ("LINEABOVE", (0, index), (-1, index), 0.75, PRIMARY),
                         ("LINEBELOW", (0, index), (-1, index), 0.75, PRIMARY)]
        else:
            name = "bold" if role == "strong" else "body"
            data.append([p(label, s[name] if role else tone(s, "body", MUTED)), p(value, right(s, name))])
    return _box(data, [width * 0.52, width * 0.48], commands)


def notice(s, text, width, *, kind="neutral"):
    """Catatan berbingkai dengan aksen garis kiri sesuai nada."""
    fg, bg, border = TONES[kind]
    return _box([[p(text, tone(s, "small", INK if kind == "neutral" else fg))]], [width], [
        ("BOX", (0, 0), (-1, -1), 0.6, border), ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, fg), *_padding(left=10, top=6, bottom=7),
    ])


def columns(widths, cells, gap=12):
    """Letakkan beberapa blok berdampingan (tanpa bingkai) dengan jarak `gap`."""
    data, col_widths = [], []
    for index, (cell, width) in enumerate(zip(cells, widths, strict=True)):
        if index:
            data.append("")
            col_widths.append(gap)
        data.append(cell)
        col_widths.append(width)
    return _box([data], col_widths, [("VALIGN", (0, 0), (-1, -1), "TOP"), *_padding(left=0, top=0, bottom=0)])


def page_decor(*, footer_left="", demo=False, demo_text="DEMO", demo_size=70, footer=True):
    """Pita hijau di tepi atas, footer hairline (nomor halaman diisi `PageCountCanvas`) dan
    watermark DEMO yang digambar paling akhir (`after`) agar berada di atas semua elemen."""
    def draw(canvas, doc):
        width, height = canvas._pagesize
        canvas.saveState()
        canvas.setFillColor(PRIMARY)
        canvas.rect(0, height - 5, width, 5, stroke=0, fill=1)
        canvas.page_label = None
        if footer:
            y = doc.bottomMargin - 20
            canvas.setStrokeColor(LINE)
            canvas.setLineWidth(0.75)
            canvas.line(doc.leftMargin, y + 10, width - doc.rightMargin, y + 10)
            canvas.setFont(REGULAR, 7)
            canvas.setFillColor(MUTED)
            canvas.drawString(doc.leftMargin, y, footer_left)
            canvas.page_label = (width - doc.rightMargin, y)
        canvas.restoreState()

    def watermark(canvas, doc):
        width, height = canvas._pagesize
        canvas.saveState()
        canvas.translate(width / 2, height / 2)
        canvas.rotate(30)
        canvas.setFillColor(colors.Color(0.71, 0.14, 0.09, alpha=0.12))
        canvas.setFont(BOLD, demo_size)
        canvas.drawCentredString(0, 0, demo_text)
        canvas.restoreState()

    draw.after = watermark if demo else (lambda canvas, doc: None)  # ReportLab selalu memanggil onPageEnd
    return draw


class PageCountCanvas(Canvas):
    """Menunda penutupan halaman agar footer bisa menulis "Halaman x dari y"."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.page_label = None
        self._pages = []

    def showPage(self):  # noqa: N802 — nama API ReportLab
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for number, state in enumerate(self._pages, 1):
            self.__dict__.update(state)
            if self.page_label:
                self.setFont(REGULAR, 7)
                self.setFillColor(MUTED)
                self.drawRightString(*self.page_label, f"Halaman {number} dari {total}")
            super().showPage()
        super().save()


def build(doc, story, decor):
    """Frame tanpa padding bawaan (6 pt) agar teks dan tabel selebar `doc.width` rata di margin."""
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="normal")
    # SimpleDocTemplate berpindah ke template "Later" setelah halaman pertama.
    doc.addPageTemplates([PageTemplate(id=name, frames=[frame], onPage=decor, onPageEnd=decor.after, pagesize=doc.pagesize) for name in ("First", "Later")])
    BaseDocTemplate.build(doc, story, canvasmaker=PageCountCanvas)
