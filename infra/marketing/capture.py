"""Ambil screenshot halaman marketing dari aplikasi LOKAL berisi data demo fiktif (seed_demo.py).

Prasyarat: API lokal di :8000 dan `next dev` di :3000 memakai database umrovia_demo,
Playwright (Chrome terpasang), Pillow, PyMuPDF. Hasil: apps/dashboard/public/marketing/*.webp.
Cara pakai: docs/runbooks/MARKETING_SCREENSHOTS.md.
"""
import io
import time
from pathlib import Path

import pymupdf as fitz
from PIL import Image
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[2] / "apps/dashboard/public/marketing"
WEB, API = "http://localhost:3000", "http://localhost:8000/api/v1"
RATIO = 10 / 16
HIDE_DEV = "const s=document.createElement('style');s.textContent='nextjs-portal{display:none!important}';document.documentElement.appendChild(s);"


def save(name, png, width=880, pad_to_ratio=False):
    """PNG 2× → WebP; kartu fitur 880px (16:10), hero 2400px."""
    im = Image.open(io.BytesIO(png)).convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    if pad_to_ratio and im.height < round(im.width * RATIO):  # cegah object-cover memotong sisi kanan
        canvas = Image.new("RGB", (im.width, round(im.width * RATIO)), "#ffffff")
        canvas.paste(im, (0, 0))
        im = canvas
    im.save(OUT / f"{name}.webp", "WEBP", quality=82, method=6)
    print("ok", name, im.size)


def box_of(pg, js):
    """Kotak (x, y, w, h) elemen terkecil yang memenuhi predikat JS, dalam koordinat halaman."""
    return pg.evaluate(f"""() => {{
        const ok = (e) => {{ {js} }};
        let best = null;
        for (const e of document.querySelectorAll('main *')) {{
            if (!ok(e)) continue;
            const r = e.getBoundingClientRect();
            if (!best || r.width * r.height < best.w * best.h) best = {{x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height}};
        }}
        return best;
    }}""")


def shot(pg, name, box, pad=0, height=None):
    w = box["w"] + 2 * pad
    clip = {"x": box["x"] - pad, "y": box["y"] - pad, "width": w, "height": height or w * RATIO}
    # Gulir dulu: halaman panjang melewati batas tinggi screenshot full-page Chrome
    pg.evaluate(f"window.scrollTo(0, {max(0, clip['y'] - 140)})")
    time.sleep(0.6)
    clip["y"] -= pg.evaluate("scrollY")
    save(name, pg.screenshot(clip=clip), pad_to_ratio=height is not None)


def go(pg, path):
    pg.goto(WEB + "/dashboard" + path)
    pg.wait_for_load_state("networkidle")
    time.sleep(2.5)


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light", device_scale_factor=2)
    ctx.add_init_script(f"document.addEventListener('DOMContentLoaded', () => {{ {HIDE_DEV} }});")
    pg = ctx.new_page()
    pg.goto(WEB + "/login")
    pg.wait_for_load_state("networkidle")
    time.sleep(4)  # tunggu hidrasi; isian sebelum hidrasi tidak masuk state React
    pg.fill("input[type=email]", "owner@amanah-haramain.test")
    pg.fill("input[type=password]", "Demo-Amanah-2026")
    with pg.expect_response(lambda r: "/auth/login" in r.url and r.request.method == "POST", timeout=15000):
        pg.click("button[type=submit]")
    time.sleep(3)

    # Hero pita gelap = video tur (record_tour.py); di sini hanya kartu fitur.
    go(pg, "")
    kuota = box_of(pg, "return e.classList.contains('card') && e.textContent.startsWith('Keberangkatan terdekat')")
    shot(pg, "kuota-jadwal", kuota, height=kuota["h"])

    go(pg, "/leads")
    card = box_of(pg, "return e.classList.contains('card') && e.textContent.includes('Nabila Putri') && e.textContent.includes('Bapak Darmawan')")
    row = box_of(pg, "return e.tagName === 'LI' && e.textContent.startsWith('Nabila Putri')")
    shot(pg, "kanal-leads", {"x": card["x"], "y": row["y"] - 18, "w": card["w"]})

    go(pg, "/jamaah")
    shot(pg, "daftar-jamaah", box_of(pg, "return e.classList.contains('card') && e.textContent.startsWith('Daftar jamaah')"))
    pg.locator("li:has-text('Ahmad Fauzi Rahman') button:has-text('Detail')").first.click()
    time.sleep(2.5)
    shot(pg, "profil-jamaah", box_of(pg, "return e.textContent.startsWith('Ahmad Fauzi Rahman') && e.textContent.includes('Riwayat perjalanan') && e.textContent.includes('Dokumen')"), pad=4)

    go(pg, "/invoice")
    pg.locator("li:has-text('INV-2026-000001') summary:has-text('Rincian tagihan')").first.click()
    time.sleep(1)
    shot(pg, "termin", box_of(pg, "return e.tagName === 'LI' && e.textContent.startsWith('INV-2026-000001')"), pad=14)

    go(pg, "/manifest")  # keberangkatan Desember terpilih bawaan
    roster = box_of(pg, "return e.classList.contains('card') && e.textContent.startsWith('Roster manifest')")
    shot(pg, "manifest-final", roster)
    first = box_of(pg, "return e.tagName === 'LI' && e.textContent.startsWith('Hj. Nurhayati')")
    shot(pg, "kelengkapan-berkas", {"x": roster["x"], "y": first["y"] - 4, "w": roster["w"]})

    # Kuitansi digital: PDF kuitansi pelunasan yang diterbitkan aplikasi, dirender apa adanya
    payments = pg.request.get(API + "/payments").json()
    pick = next(r for r in payments.get("results", payments) if r.get("kind") == "BALANCE" and r.get("receipt"))
    page = fitz.open(stream=pg.request.get(f"{API}/receipts/{pick['receipt']['id']}/pdf").body(), filetype="pdf")[0]
    # Kop sampai tabel "Total diterima" (364 pt), 16:10 di tengah halaman
    height = 364
    left = (page.rect.width - height / RATIO) / 2
    pix = page.get_pixmap(dpi=220, clip=fitz.Rect(left, 0, left + height / RATIO, height))
    save("kuitansi", pix.tobytes("png"))
    b.close()
