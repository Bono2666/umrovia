"""Font PDF Umrovia: Poppins (SIL OFL, lihat fonts/OFL.txt), sama dengan font UI.

Didaftarkan sebagai keluarga "Umrovia" agar pemanggil tidak bergantung pada nama
berkas: reguler = Poppins Regular, tebal (`<b>`, judul) = Poppins SemiBold seperti
heading aplikasi. Semua generator PDF (invoice/kuitansi, manifest & dokumen cetak,
ekspor laporan) wajib memanggil `register_pdf_fonts()` sebelum membangun dokumen.
"""
from pathlib import Path

from reportlab import rl_config
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus.tables import CellStyle

FONT_DIR = Path(__file__).resolve().parent / "fonts"
REGULAR, BOLD = "Umrovia", "Umrovia-Bold"


def register_pdf_fonts() -> None:
    registered = pdfmetrics.getRegisteredFontNames()
    for name, file in [(REGULAR, "Poppins-Regular.ttf"), (BOLD, "Poppins-SemiBold.ttf")]:
        if name not in registered:
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
    pdfmetrics.registerFontFamily(REGULAR, normal=REGULAR, bold=BOLD, italic=REGULAR, boldItalic=BOLD)
    # Bawaan ReportLab = Helvetica: font awal canvas, dan font sel Table yang selalu
    # di-setFont walau isinya Paragraph (Helvetica ikut tertanam tanpa dipakai).
    rl_config.canvas_basefontname = REGULAR
    CellStyle.fontname = REGULAR
