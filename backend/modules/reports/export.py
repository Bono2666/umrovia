"""Ekspor laporan (RPT-03/06): PDF lanskap, XLSX bernomor dan CSV dari payload yang sama dengan layar."""
import csv
from datetime import date
from io import BytesIO, StringIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.documents.render import format_idr
from modules.manifest.printing import GREEN, LINE, TINT, _p, _page_decor, _styles
from modules.payments.pdf import document_date

MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]


def format_value(value, kind):
    if value is None or value == "":
        return "—"
    if kind == "money":
        return ("−" if value < 0 else "") + format_idr(abs(int(value)))
    if kind == "int":
        return f"{int(value):,}".replace(",", ".")
    if kind == "percent":
        return f"{value:.1f}%".replace(".", ",")
    if kind == "date":
        day = date.fromisoformat(str(value)[:10])
        return f"{day.day} {MONTHS[day.month - 1][:3]} {day.year}"
    return str(value)


def period_text(report):
    start, end = (date.fromisoformat(report["period"][key]) for key in ("from", "to"))
    return f"{start.day} {MONTHS[start.month - 1]} {start.year} – {end.day} {MONTHS[end.month - 1]} {end.year}"


def header_lines(report, labels):
    lines = [f"{report['travel']} · Periode {period_text(report)}", f"Per {document_date(report['as_of'], report['timezone'], with_time=True)}"]
    active = [f"{name}: {labels[key]}" for key, name in (("package", "Paket"), ("departure", "Keberangkatan"), ("status", "Status"), ("agent", "Agen"), ("account", "Rekening")) if report["filters"].get(key)]
    if active:
        lines.append("Filter — " + " · ".join(active))
    if report.get("note"):
        lines.append(report["note"])
    return lines


def filename(report, ext):
    prefix = "DEMO-" if report["environment"] == "demo" else ""
    return f"{prefix}laporan-{report['report']}-{report['period']['from']}_{report['period']['to']}.{ext}"


def to_pdf(report, meta, labels) -> bytes:
    s = _styles()
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=30, bottomMargin=40, title=report["title"], author=report["travel"])
    aligned = {(name, r): s[name].clone(f"{name}-{int(r)}", alignment=2 if r else 0) for name in ("head", "cell") for r in (False, True)}
    story = [_p(report["title"], s["title"]), Spacer(1, 4), *[_p(line, s["small"]) for line in header_lines(report, labels)], Spacer(1, 10)]
    if report["kpis"]:
        cells = [[Paragraph(f"<font size=7 color='#555b5e'>{kpi['label']}</font><br/><b>{format_value(kpi['value'], kpi['type'])}</b>", s["normal"]) for kpi in report["kpis"]]]
        kpis = Table(cells, colWidths=[(doc.width) / len(report["kpis"])] * len(report["kpis"]))
        kpis.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story += [kpis, Spacer(1, 12)]
    for section in report["sections"]:
        story.append(_p(section["title"], s["label"]))
        if section.get("description"):
            story.append(_p(section["description"], s["small"]))
        story.append(Spacer(1, 4))
        columns = section["columns"]
        if not section["rows"]:
            story += [_p("Tidak ada data pada periode ini.", s["small"]), Spacer(1, 10)]
            continue
        right = [col["type"] in {"money", "int", "percent"} for col in columns]
        data = [[_p(col["label"], aligned[("head", r)]) for col, r in zip(columns, right, strict=True)]]
        data += [[_p(format_value(row.get(col["key"]), col["type"]), aligned[("cell", r)]) for col, r in zip(columns, right, strict=True)] for row in section["rows"]]
        if section.get("totals"):
            totals = section["totals"]
            data.append([_p(format_value(totals.get(col["key"]), col["type"]) if col["key"] in totals else " ", aligned[("head", r)]) for col, r in zip(columns, right, strict=True)])
        table = Table(data, repeatRows=1, colWidths=[doc.width / len(columns)] * len(columns))
        style = [("BACKGROUND", (0, 0), (-1, 0), TINT), ("LINEBELOW", (0, 0), (-1, 0), 0.75, GREEN), ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE),
                 ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        if section.get("totals"):
            style.append(("LINEABOVE", (0, -1), (-1, -1), 0.75, GREEN))
        table.setStyle(TableStyle(style))
        story += [table, Spacer(1, 4)]
        if section.get("truncated"):
            story.append(_p("Daftar dipotong pada 500 baris; persempit filter untuk rincian lengkap.", s["small"]))
        story.append(Spacer(1, 10))
    if report.get("checks"):
        story.append(_p("Rekonsiliasi terhadap catatan sumber", s["label"]))
        for check in report["checks"]:
            story.append(_p(f"{'✓ Sesuai' if check['ok'] else '✗ Selisih'} — {check['label']} ({check['detail']})", s["small"]))
    decor = _page_decor(meta)
    doc.build(story, onFirstPage=decor, onLaterPages=decor)
    return output.getvalue()


def to_xlsx(report, meta, labels) -> bytes:
    book = Workbook()
    summary = book.active
    summary.title = "Ringkasan"
    summary.append([report["title"] + (" (DEMO)" if meta.get("demo") else "")])
    for line in header_lines(report, labels):
        summary.append([line])
    summary.append([f"Dicetak {meta['printed_at']} oleh {meta['printed_by']}"])
    summary.append([])
    summary.append(["Indikator", "Nilai"])
    header_row = summary.max_row
    for kpi in report["kpis"]:
        summary.append([kpi["label"], kpi["value"]])
        if kpi["type"] == "money":
            summary.cell(summary.max_row, 2).number_format = "#,##0"
    if report.get("checks"):
        summary.append([])
        summary.append(["Rekonsiliasi", "Hasil", "Rincian"])
        for check in report["checks"]:
            summary.append([check["label"], "Sesuai" if check["ok"] else "Selisih", check["detail"]])
    summary["A1"].font = Font(bold=True, size=14, color="0E6B5C")
    for cell in summary[header_row]:
        cell.font = Font(bold=True)
    summary.column_dimensions["A"].width = 58
    summary.column_dimensions["B"].width = 20
    summary.column_dimensions["C"].width = 60
    used = set()
    for section in report["sections"]:
        name = section["title"][:31].replace("/", "-")
        while name in used:
            name = name[:29] + str(len(used))
        used.add(name)
        sheet = book.create_sheet(name)
        columns = section["columns"]
        sheet.append([col["label"] for col in columns])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="EAF3EF")
        rows = list(section["rows"])
        if section.get("totals"):
            rows.append(section["totals"])
        for row in rows:
            sheet.append([_xlsx_value(row.get(col["key"]), col["type"]) for col in columns])
            for i, col in enumerate(columns, 1):
                target = sheet.cell(sheet.max_row, i)
                if isinstance(target.value, str):
                    target.data_type = "s"  # teks diawali =, +, -, @ tidak menjadi formula
                elif col["type"] == "money":
                    target.number_format = "#,##0"
                target.alignment = Alignment(vertical="top", wrap_text=True)
        if section.get("totals"):
            for cell in sheet[sheet.max_row]:
                cell.font = Font(bold=True)
        for i, col in enumerate(columns, 1):
            sheet.column_dimensions[sheet.cell(1, i).column_letter].width = 16 if col["type"] in {"money", "int", "percent", "date"} else 30
        sheet.freeze_panes = "A2"
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def _xlsx_value(value, kind):
    if value is None:
        return None
    if kind in {"money", "int"}:
        return int(value)
    if kind == "percent":
        return float(value)
    return str(value)


def to_csv(report, meta, labels) -> bytes:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow([report["title"]])
    for line in header_lines(report, labels):
        writer.writerow([line])
    for kpi in report["kpis"]:
        writer.writerow([kpi["label"], kpi["value"]])
    for section in report["sections"]:
        writer.writerow([])
        writer.writerow([section["title"]])
        writer.writerow([col["label"] for col in section["columns"]])
        rows = list(section["rows"]) + ([section["totals"]] if section.get("totals") else [])
        for row in rows:
            writer.writerow([_csv_value(row.get(col["key"])) for col in section["columns"]])
    for check in report.get("checks", []):
        writer.writerow(["Rekonsiliasi", check["label"], "Sesuai" if check["ok"] else "Selisih", check["detail"]])
    # BOM agar Excel membaca UTF-8; nilai teks berawalan formula diberi tanda kutip.
    return ("﻿" + buffer.getvalue()).encode()


def _csv_value(value):
    if value is None:
        return ""
    if isinstance(value, str) and value[:1] in {"=", "+", "-", "@"}:
        return "'" + value
    return value
