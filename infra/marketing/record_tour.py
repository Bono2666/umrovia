"""Rekam video tur aplikasi (±50 detik) untuk halaman marketing dari aplikasi LOKAL berdata demo fiktif.

Prasyarat sama dengan capture.py (API :8000 + `next dev` :3000 memakai umrovia_demo,
Playwright + Chrome) ditambah ffmpeg. Frame diambil lewat screencast Chrome (retina, JPEG
berkualitas tinggi) lalu disusun ffmpeg menjadi MP4 (H.264) + WebM (VP9) dan poster WebP di
apps/dashboard/public/marketing/. Kursor digambar di halaman karena screencast tidak merekamnya.
Cara pakai: docs/runbooks/MARKETING_SCREENSHOTS.md.
"""
import asyncio
import base64
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

OUT = Path(__file__).resolve().parents[2] / "apps/dashboard/public/marketing"
WEB = "http://localhost:3000"
VIEW = {"width": 1440, "height": 900}
SIZE = "1600:1000"  # 16:10; tajam di lebar hero, ukuran file tetap ringan
PAGES = ["", "/leads", "/jamaah", "/booking", "/invoice", "/manifest", "/laporan"]

CURSOR = """
addEventListener('DOMContentLoaded', () => {
  const style = document.createElement('style');
  style.textContent = `nextjs-portal{display:none!important}
    #tour-cursor{position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;width:24px;height:24px;transition:none}
    .tour-ripple{position:fixed;z-index:2147483646;pointer-events:none;width:36px;height:36px;margin:-18px 0 0 -18px;border-radius:50%;
      border:2px solid #0e6b5c;background:rgb(14 107 92/.15);animation:tour-ripple .55s ease-out forwards}
    @keyframes tour-ripple{from{transform:scale(.3);opacity:1}to{transform:scale(1.4);opacity:0}}`;
  document.head.appendChild(style);
  const cursor = document.createElement('div');
  cursor.id = 'tour-cursor';
  cursor.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24"><path d="M5 2.5v17.2l4.4-4.2 2.9 6.6 2.7-1.2-2.9-6.5h6.1z" fill="#191b1d" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  document.documentElement.appendChild(cursor);
  const place = (x, y) => { cursor.style.transform = `translate(${x - 5}px, ${y - 2}px)`; sessionStorage.setItem('tour-cursor', `${x},${y}`); };
  const [x, y] = (sessionStorage.getItem('tour-cursor') || '720,450').split(',').map(Number);
  place(x, y);
  addEventListener('mousemove', (e) => place(e.clientX, e.clientY), true);
  addEventListener('mousedown', (e) => {
    const ring = document.createElement('div');
    ring.className = 'tour-ripple';
    ring.style.left = e.clientX + 'px'; ring.style.top = e.clientY + 'px';
    document.documentElement.appendChild(ring);
    setTimeout(() => ring.remove(), 600);
  }, true);
});
"""


class Tour:
    def __init__(self, page):
        self.page = page
        self.x, self.y = 720, 450
        self.recording = True  # frame saat False dibuang (potongan jeda loading)
        self.segment = 0

    async def pause(self, seconds):
        await asyncio.sleep(seconds)

    async def _animate(self, duration, step):
        """Panggil `step(progress)` dengan easing ease-in-out sampai `duration` detik berlalu.

        Berbasis jam, bukan jumlah langkah: tiap panggilan ke browser butuh waktu sendiri,
        sehingga loop berbasis langkah membuat video jauh lebih lambat dari rencana.
        """
        loop = asyncio.get_running_loop()
        start = loop.time()
        while True:
            t = min(1.0, (loop.time() - start) / duration)
            await step(0.5 - math.cos(math.pi * t) / 2)
            if t >= 1:
                return
            await asyncio.sleep(1 / 60)

    async def move(self, x, y, duration=0.7):
        sx, sy = self.x, self.y

        async def step(e):
            await self.page.mouse.move(sx + (x - sx) * e, sy + (y - sy) * e)

        await self._animate(duration, step)
        self.x, self.y = x, y

    async def scroll(self, pixels, duration=1.2):
        start = await self.page.evaluate("scrollY")

        async def step(e):
            await self.page.evaluate(f"window.scrollTo(0, {start + pixels * e})")

        await self._animate(duration, step)

    async def reveal(self, locator, top=150, duration=1.0):
        """Gulir halus sampai elemen berada ±`top` px dari atas layar (bila belum terlihat utuh)."""
        box = await locator.bounding_box()
        height = await self.page.evaluate("innerHeight")
        if box["y"] < 70 or box["y"] + min(box["height"], 240) > height:
            await self.scroll(box["y"] - top, duration)

    async def to(self, locator, duration=0.7, dx=0.5, dy=0.5):
        await self.reveal(locator)
        box = await locator.bounding_box()
        await self.move(box["x"] + box["width"] * dx, box["y"] + box["height"] * dy, duration)

    async def click(self, locator, duration=0.7):
        await self.to(locator, duration)
        await self.pause(0.12)
        await self.page.mouse.down()
        await self.pause(0.08)
        await self.page.mouse.up()

    async def cut_until(self, ready):
        """Potong jeda loading: berhenti merekam sampai `ready` tampil dan data selesai dimuat."""
        self.recording = False
        await ready.wait_for()
        await self.page.wait_for_load_state("networkidle")
        await self.page.wait_for_function("!document.querySelector('main')?.innerText.includes('Memuat')")
        await self.pause(0.4)
        self.segment += 1
        self.recording = True
        # Screencast hanya mengirim frame saat layar berubah: geser kursor 1 px agar frame baru terkirim
        await self.page.mouse.move(self.x + 1, self.y)
        await self.page.mouse.move(self.x, self.y)

    async def open(self, label, ready):
        """Pindah halaman lewat sidebar seperti pengguna; jeda loading dipotong dari video."""
        link = self.page.locator(f"aside a:has-text('{label}')").first
        href = await link.get_attribute("href")
        await self.click(link)
        self.recording = False
        # Tunggu URL berganti dulu: penanda `ready` bisa saja juga ada di halaman sebelumnya
        await self.page.wait_for_url(f"**{href}")
        await self.cut_until(ready)
        await self.pause(0.5)


async def tour(t: Tour, page):
    text = lambda value: page.get_by_text(value, exact=False).first  # noqa: E731
    item = lambda value: page.locator(f"li:has-text('{value}')").first  # noqa: E731

    # 1. Ringkasan — KPI, tindak lanjut, keberangkatan terdekat
    await t.pause(1.5)
    await t.move(560, 250, 0.9)
    await t.move(980, 250, 0.9)
    await t.pause(0.5)
    await t.to(text("Keberangkatan terdekat"), 0.8)
    await t.pause(1.5)
    await t.scroll(-400, 1.0)

    # 2. Leads — saluran & status lead
    await t.open("Leads", text("Nabila Putri"))
    await t.to(text("Nabila Putri"), 0.8)
    await t.pause(1.3)
    await t.scroll(260, 1.1)
    await t.pause(0.7)

    # 3. Jamaah — daftar lalu panel detail di bawahnya
    await t.open("Jamaah", item("Ahmad Fauzi Rahman"))
    await t.click(item("Ahmad Fauzi Rahman").locator("button:has-text('Detail')"))
    detail = page.locator("h3:has-text('Ahmad Fauzi Rahman')").first
    await t.cut_until(detail)
    await t.to(detail, 0.8, dx=0.2)
    await t.pause(1.2)
    await t.scroll(280, 1.2)
    await t.pause(1.0)

    # 4. Booking
    await t.open("Booking", page.locator("main li").first)
    await t.move(760, 380, 0.8)
    await t.scroll(340, 1.3)
    await t.pause(0.9)

    # 5. Invoice — termin dan rincian tagihan
    await t.open("Invoice", item("INV-2026-000001"))
    await t.click(item("INV-2026-000001").locator("summary:has-text('Rincian tagihan')"))
    await t.pause(1.0)
    await t.scroll(220, 1.0)
    await t.pause(1.5)

    # 6. Manifest — roster dan status dokumen/bayar
    await t.open("Manifest", item("Hj. Nurhayati"))
    await t.to(text("Roster manifest"), 0.8)
    await t.pause(0.5)
    await t.to(item("Hj. Nurhayati"), 0.8, dx=0.3)
    await t.pause(1.7)

    # 7. Laporan — ringkasan angka dan kesiapan keberangkatan
    await t.open("Laporan", text("Rekonsiliasi"))
    await t.move(700, 330, 0.8)
    await t.pause(1.0)
    await t.scroll(380, 1.3)
    await t.pause(2.2)


async def main():
    frames = Path(tempfile.mkdtemp(prefix="umrovia-tour-"))
    async with async_playwright() as p:
        # Screencast memotret jendela headless, bukan viewport emulasi: samakan ukuran jendela
        # dan paksa skala 2× agar frame 2880×1800 utuh (tanpa ini 1440×813, terpotong & buram).
        browser = await p.chromium.launch(channel="chrome", args=[f"--window-size={VIEW['width']},{VIEW['height']}", "--force-device-scale-factor=2"])
        ctx = await browser.new_context(viewport=VIEW, color_scheme="light", device_scale_factor=2)
        await ctx.add_init_script(CURSOR)
        page = await ctx.new_page()
        await page.goto(WEB + "/login")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(4)  # tunggu hidrasi; isian sebelum hidrasi tidak masuk state React
        await page.fill("input[type=email]", "owner@amanah-haramain.test")
        await page.fill("input[type=password]", "Demo-Amanah-2026")
        async with page.expect_response(lambda r: "/auth/login" in r.url and r.request.method == "POST", timeout=15000):
            await page.click("button[type=submit]")
        await asyncio.sleep(3)
        # Panaskan semua halaman (next dev mengompilasi saat kunjungan pertama) agar tidak ada jeda di video
        for path in PAGES:
            await page.goto(WEB + "/dashboard" + path)
            await page.wait_for_load_state("networkidle")
        await page.goto(WEB + "/dashboard")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2.5)

        shots = []  # (timestamp, segmen, berkas)
        cdp = await ctx.new_cdp_session(page)
        t = Tour(page)

        async def on_frame(event):
            if t.recording:
                path = frames / f"{len(shots):05d}.jpg"
                path.write_bytes(base64.b64decode(event["data"]))
                shots.append((event["metadata"]["timestamp"], t.segment, path))
            await cdp.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})

        cdp.on("Page.screencastFrame", lambda event: asyncio.ensure_future(on_frame(event)))
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": 2880, "maxHeight": 1800, "everyNthFrame": 1})
        await page.mouse.move(t.x, t.y)
        await tour(t, page)
        await cdp.send("Page.stopScreencast")
        await asyncio.sleep(0.5)
        await browser.close()

    # Screencast hanya mengirim frame saat layar berubah: durasi tiap frame = selisih timestamp
    # dalam segmen yang sama; di batas potongan loading frame terakhir tampil sebentar saja.
    # Urutkan per timestamp (frame pertama kadang datang terlambat) dan buang durasi ≤ 0.
    shots.sort(key=lambda shot: shot[0])
    listing = frames / "frames.txt"
    rows, total = [], 0.0
    for (stamp, segment, path), following in zip(shots, [*shots[1:], None], strict=True):
        if following is None:
            duration = 1.0
        else:
            duration = following[0] - stamp if following[1] == segment else 0.12
        if duration > 0.001:
            rows += [f"file '{path}'", f"duration {duration:.4f}"]
            total += duration
    rows.append(f"file '{shots[-1][2]}'")
    listing.write_text("\n".join(rows) + "\n")
    source = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-vf", f"scale={SIZE}:flags=lanczos,fps=30", "-an"]
    subprocess.run([*source, "-c:v", "libx264", "-preset", "slow", "-crf", "27", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT / "tur-aplikasi.mp4")], check=True)
    subprocess.run([*source, "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "40", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4", str(OUT / "tur-aplikasi.webm")], check=True)
    width, height = map(int, SIZE.split(":"))
    Image.open(shots[0][2]).convert("RGB").resize((width, height), Image.LANCZOS).save(OUT / "tur-aplikasi-poster.webp", "WEBP", quality=82, method=6)
    print(f"ok {len(shots)} frame, {total:.1f} detik")
    shutil.rmtree(frames)


asyncio.run(main())
