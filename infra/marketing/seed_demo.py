"""Isi database LOKAL kosong dengan travel FIKTIF untuk screenshot marketing.

Semua nama, NIK, paspor, telepon, dan alamat adalah karangan. Jangan pernah
dijalankan terhadap database produksi. Cara pakai: docs/runbooks/MARKETING_SCREENSHOTS.md.
"""
import re
import sys
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client
from django.test.utils import setup_test_environment

if not settings.DEBUG or not connection.settings_dict["NAME"].endswith("_demo"):
    raise SystemExit("seed_demo hanya untuk database lokal *_demo dengan DEBUG=True.")

setup_test_environment()  # mail.outbox (locmem) agar token verifikasi bisa dibaca

sys.path.insert(0, ".")
from modules.identity.models import User  # noqa: E402
from tests.test_platform_console import platform_client  # noqa: E402

WIB = ZoneInfo("Asia/Jakarta")
PASSWORD = "Demo-Amanah-2026"
EMAIL = "owner@amanah-haramain.test"
PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"


def csrf(c):
    return c.get("/api/v1/auth/csrf").json()["csrfToken"]


def call(c, method, url, body=None, files=None):
    kw = {"HTTP_X_CSRFTOKEN": csrf(c), "HTTP_IDEMPOTENCY_KEY": str(uuid4())}
    if files is not None:
        r = c.post(url, files, **kw)
    elif method == "post":
        r = c.post(url, body or {}, content_type="application/json", **kw)
    else:
        r = c.patch(url, body or {}, content_type="application/json", **kw)
    if r.status_code not in (200, 201):
        raise SystemExit(f"GAGAL {method.upper()} {url}: {r.status_code} {r.content[:400]!r}")
    return r.json()


def post(c, url, body=None):
    return call(c, "post", url, body)


def at(y, m, d, h=9):
    return datetime(y, m, d, h, tzinfo=WIB).isoformat()


owner = Client(HTTP_HOST="localhost")
post(owner, "/api/v1/auth/register", {"email": EMAIL, "password": PASSWORD, "travel_name": "Amanah Haramain Tour", "slug": "amanah", "agree_terms": True})
token = re.search(r"token=([\w.\-]+)", mail.outbox[-1].body).group(1)
post(owner, "/api/v1/auth/verify-email", {"token": token})
post(owner, "/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
tenant_id = owner.get("/api/v1/me").json()["memberships"][0]["tenant"]["id"]
User.objects.filter(email=EMAIL).update(full_name="Rahmawati Hasanah")
post(owner, "/api/v1/trial/convert", {"confirm": True})
print("workspace aktif")

topup = post(owner, "/api/v1/wallet/topups", {"amount_idr": 5_000_000})
post(owner, f"/api/v1/wallet/topups/{topup['id']}/submit", {"payment_reference": "TRF-0412", "evidence_ref": "restricted://bukti-topup"})
billing, _ = platform_client("Platform Billing")
billing.defaults["HTTP_HOST"] = "localhost"
post(billing, f"/api/v1/platform/tenants/{tenant_id}/wallet/topups/{topup['id']}/settle", {"amount_idr": 5_000_000, "provider_txn_id": "MUTASI-0412"})
print("wallet Rp5.000.000")

call(owner, "patch", "/api/v1/tenant/settings", {"branding_json": {"address": "Jl. KH. Noer Ali No. 18, Kayuringin Jaya, Bekasi Selatan, Kota Bekasi 17144"}})
bank = post(owner, "/api/v1/bank-accounts", {"bank_name": "BSI", "account_name": "PT Amanah Haramain Tour", "account_number": "7123456789"})["bank_account"]

PAKET = [
    ("Umroh Reguler 12 Hari", [("QUAD", 32_500_000), ("TRIPLE", 34_500_000), ("DOUBLE", 37_000_000)]),
    ("Umroh Plus Turki 15 Hari", [("QUAD", 39_900_000), ("DOUBLE", 45_000_000)]),
    ("Umroh Ramadhan 14 Hari", [("QUAD", 41_000_000), ("DOUBLE", 47_500_000)]),
]
packages = []
for name, rooms in PAKET:
    packages.append(post(owner, "/api/v1/packages", {"name": name, "price_idr": rooms[0][1], "room_prices": [{"room_type": t, "price_idr": p} for t, p in rooms]}))

JADWAL = [(0, at(2026, 12, 12, 7), 12, "Jakarta", 45), (1, at(2027, 1, 16, 7), 15, "Surabaya", 40), (2, at(2027, 2, 20, 7), 14, "Jakarta", 30)]
departures = []
for pkg, start, days, city, seats in JADWAL:
    start_dt = datetime.fromisoformat(start)
    dep = post(owner, "/api/v1/departures", {"package": packages[pkg]["id"], "start_at": start, "end_at": (start_dt + timedelta(days=days)).isoformat(), "city_of_origin": city, "seat_capacity": seats})
    post(owner, f"/api/v1/departures/{dep['id']}/transition", {"target": "OPEN"})
    departures.append(dep)
print("paket & jadwal")

JAMAAH = [
    ("Ahmad Fauzi Rahman", "male", "1978-04-12", "Bekasi", "081234560101"),
    ("Siti Aminah", "female", "1981-09-03", "Bekasi", "081234560102"),
    ("Muhammad Rizki Pratama", "male", "2004-01-22", "Bekasi", "081234560103"),
    ("Hj. Nurhayati", "female", "1962-06-15", "Bogor", "081234560104"),
    ("Bambang Sutrisno", "male", "1970-11-30", "Depok", "081234560105"),
    ("Dewi Lestari", "female", "1974-02-08", "Depok", "081234560106"),
    ("Fadli Hidayat", "male", "1988-07-19", "Jakarta", "081234560107"),
    ("Annisa Rahmawati", "female", "1990-12-01", "Jakarta", "081234560108"),
    ("H. Abdul Karim", "male", "1958-03-27", "Surabaya", "081234560109"),
    ("Hj. Fatimah Zahra", "female", "1961-08-14", "Surabaya", "081234560110"),
    ("Yusuf Maulana", "male", "1985-05-05", "Sidoarjo", "081234560111"),
    ("Rina Kartika", "female", "1987-10-10", "Sidoarjo", "081234560112"),
    ("Hendra Gunawan", "male", "1979-01-17", "Malang", "081234560113"),
    ("Ustadz Hasan Basri", "male", "1968-09-09", "Jakarta", "081234560114"),
    ("Khadijah Puspita", "female", "1993-04-24", "Tangerang", "081234560115"),
    ("Ridwan Kamil Syah", "male", "1983-06-02", "Tangerang", "081234560116"),
]
pilgrims = []
for i, (name, gender, birth, place, phone) in enumerate(JAMAAH):
    body = {"name": name, "gender": gender, "birth_date": birth, "birth_place": place, "phone": phone, "nationality": "WNI",
            "identity_number": f"{3275 + (i % 5) * 3}{10 + i * 7 % 80:02d}{(i * 37) % 28 + 1:02d}{(i * 5) % 12 + 1:02d}{70 + i:02d}{(i * 4271 + 1093) % 10000:04d}", "address": f"Jl. Melati No. {i + 3}, {place}"}
    if i < 10:
        body.update({"passport_number": f"{'CE' if i % 2 else 'X'}{(i * 739153 + 4812301) % 10000000:07d}", "passport_name": name.replace("Hj. ", "").replace("H. ", "").upper(),
                     "passport_issued_at": "2024-03-11", "passport_expires_at": "2034-03-11", "passport_place_of_issue": "Kanim " + place})
    pilgrims.append(post(owner, "/api/v1/pilgrims", body))
print("jamaah", len(pilgrims))

# (keberangkatan, indeks jamaah, kamar, pembayaran per peserta: list (kind, nominal, tanggal), status akhir)
BOOKING = [
    (0, [0, 1, 2], "QUAD", [("DP", 10_000_000, at(2026, 9, 2)), ("INSTALLMENT", 15_000_000, at(2026, 10, 5))], "DOCUMENT_PROCESS"),
    (0, [3], "DOUBLE", [("DP", 10_000_000, at(2026, 9, 10)), ("BALANCE", 27_000_000, at(2026, 10, 20))], "DOCUMENT_PROCESS"),
    (0, [4, 5], "DOUBLE", [("DP", 10_000_000, at(2026, 9, 18))], "CONFIRMED"),
    (0, [6, 7], "TRIPLE", [("DP", 10_000_000, at(2026, 10, 1))], "CONFIRMED"),
    (1, [8, 9], "DOUBLE", [("DP", 10_000_000, at(2026, 10, 8)), ("INSTALLMENT", 15_000_000, at(2026, 10, 27))], "CONFIRMED"),
    (1, [10, 11, 12], "QUAD", [("DP", 10_000_000, at(2026, 10, 15))], "CONFIRMED"),
    (2, [13], "DOUBLE", [("DP", 10_000_000, at(2026, 10, 22))], "CONFIRMED"),
    (2, [14, 15], "QUAD", [], "RESERVED"),
]
bookings = []
for dep, members, room, pays, final in BOOKING:
    ids = [pilgrims[i]["id"] for i in members]
    bk = post(owner, "/api/v1/bookings", {"departure": departures[dep]["id"], "participants": ids, "room_types": {pid: room for pid in ids}})
    post(owner, f"/api/v1/bookings/{bk['id']}/transition", {"target": "RESERVED"})
    inv = post(owner, f"/api/v1/bookings/{bk['id']}/issue-invoice")
    for kind, amount, received in pays:
        for line in inv["lines"]:
            pay = post(owner, "/api/v1/payments", {"invoice": inv["id"], "amount_idr": amount, "kind": kind, "method": "TRANSFER", "bank_account": bank["id"],
                                                   "received_at": received, "reference": f"{kind}-{line['participant_id'][:6].upper()}",
                                                   "allocations": [{"booking_participant_id": line["participant_id"], "amount_idr": amount}]})
            post(owner, f"/api/v1/payments/{pay['id']}/verify")
    path = {"RESERVED": [], "CONFIRMED": ["CONFIRMED"], "DOCUMENT_PROCESS": ["CONFIRMED", "DOCUMENT_PROCESS"]}[final]
    for target in path:
        post(owner, f"/api/v1/bookings/{bk['id']}/transition", {"target": target})
    bookings.append(bk)
print("booking", len(bookings))

for pkg in packages:
    for kind in ["passport", "ktp", "photo"]:
        post(owner, "/api/v1/document-requirements", {"package": pkg["id"], "kind": kind, "mandatory": True, "deadline_rule": "before_ready"})

# Dokumen: keberangkatan Desember (jamaah 0–7) — sebagian lengkap & disetujui, sebagian menunggu
DOCS = {0: ["passport", "ktp", "photo", "kk"], 1: ["passport", "ktp", "photo", "kk"], 2: ["passport", "ktp", "photo"], 3: ["passport", "ktp", "photo", "kk"],
        4: ["passport", "ktp"], 5: ["passport", "ktp", "photo"], 6: ["ktp"], 7: ["passport", "ktp"]}
PENDING = {(2, "photo"), (5, "photo"), (7, "passport")}
for i, kinds in DOCS.items():
    pid = pilgrims[i]["id"]
    for kind in kinds:
        doc = call(owner, "post", f"/api/v1/pilgrims/{pid}/documents/upload", files={"kind": kind, "file": SimpleUploadedFile(f"{kind}.pdf", PDF, content_type="application/pdf")})
        if (i, kind) not in PENDING:
            call(owner, "patch", f"/api/v1/pilgrims/{pid}/documents/{doc['id']}", {"status": "APPROVED"})
print("dokumen")
post(owner, f"/api/v1/departures/{departures[0]['id']}/manifest/publish")
print("manifest v1")

LEADS = [
    ("Bapak Darmawan", "081298760001", "WHATSAPP", "NEW", 0, 4, "Tanya paket keluarga Desember, 2 dewasa 2 remaja."),
    ("Ibu Sulastri", "081298760002", "INSTAGRAM", "CONTACTED", 1, 2, "Minta brosur Plus Turki, berangkat dari Surabaya."),
    ("Keluarga Pak Imam", "081298760003", "REFERRAL", "QUALIFIED", 2, 5, "Rujukan Hj. Nurhayati. Ingin kamar double untuk orang tua."),
    ("Ahmad Syarif", "081298760004", "WEBSITE", "QUOTED", 0, 1, "Penawaran Reguler quad dikirim via email."),
    ("Majelis Taklim Al-Ikhlas", "081298760005", "EVENT", "QUALIFIED", 2, 18, "Rombongan majelis, minta jadwal manasik dan cicilan."),
    ("Ibu Ratna Sari", "081298760006", "FACEBOOK", "NEW", 1, 2, ""),
    ("Pak Joko Widarto", "081298760007", "WALK_IN", "CONTACTED", 0, 2, "Datang ke kantor, bandingkan dengan travel lain."),
    ("Nabila Putri", "081298760008", "TIKTOK", "NEW", 2, 1, "Tanya Umroh Ramadhan untuk mahasiswa."),
]
for idx, (name, phone, source, stage, pkg, pax, notes) in enumerate(LEADS):
    follow = at(2026, 10, 28, 10) if idx == 3 else at(2026, 11, 2 + idx % 5, 9 + idx % 4)
    lead = post(owner, "/api/v1/leads", {"name": name, "phone": phone, "source": source, "interest_package": packages[pkg]["id"], "pax": pax, "notes": notes,
                                         "city": ["Bekasi", "Surabaya", "Bogor", "Jakarta", "Depok", "Sidoarjo", "Jakarta", "Tangerang"][idx], "next_follow_up_at": follow})
    for target in ["CONTACTED", "QUALIFIED", "QUOTED"]:
        if ["NEW", "CONTACTED", "QUALIFIED", "QUOTED"].index(stage) >= ["NEW", "CONTACTED", "QUALIFIED", "QUOTED"].index(target):
            post(owner, f"/api/v1/leads/{lead['id']}/stage", {"stage": target})
print("leads", len(LEADS))

# Rombongan tambahan → keterisian kursi realistis (Des ±70%, Jan ±55%, Feb ±40%)
DEPAN = ["Agus", "Budi", "Cahya", "Dian", "Eko", "Fitri", "Gilang", "Hana", "Irfan", "Juwita", "Kurnia", "Lukman", "Maya", "Nanda", "Oki", "Putri",
         "Rahmat", "Sari", "Taufik", "Umi", "Vina", "Wahyu", "Yanti", "Zainal", "Arif", "Bunga", "Dodi", "Erna", "Firman", "Gita", "Hadi", "Indah",
         "Joko", "Kiki", "Lina", "Mulyadi", "Novi", "Rudi", "Sinta", "Tono", "Wulan", "Yogi", "Zahra", "Anwar", "Bayu", "Citra", "Darma", "Eka",
         "Faisal", "Gina", "Hamdan", "Ika", "Jamal", "Lestari", "Mahmud", "Nur", "Rizal", "Salma", "Teguh", "Wati", "Yusran", "Asih", "Bahrul", "Dewanto"]
BELAKANG = ["Santoso", "Wibowo", "Saputra", "Lestari", "Hidayat", "Nugroho", "Rahayu", "Setiawan", "Kurniawan", "Permana", "Siregar", "Harahap", "Nasution", "Pane", "Lubis", "Utami"]
TARGET = [(0, 24, "QUAD"), (1, 17, "QUAD"), (2, 9, "DOUBLE")]
n = 0
for dep, count, room in TARGET:
    made = 0
    while made < count:
        size = min(2 if n % 3 else 3, count - made)
        ids = []
        for _ in range(size):
            g = "female" if n % 2 else "male"
            nm = f"{DEPAN[n % len(DEPAN)]} {BELAKANG[(n * 7) % len(BELAKANG)]}"
            ids.append(post(owner, "/api/v1/pilgrims", {"name": nm, "gender": g, "birth_date": f"{1965 + n % 35}-{n % 12 + 1:02d}-{n % 27 + 1:02d}", "phone": f"08{[13, 52, 21, 57, 12][n % 5]}{(n * 7919 + 52174836) % 100000000:08d}"})["id"])
            n += 1
        bk = post(owner, "/api/v1/bookings", {"departure": departures[dep]["id"], "participants": ids, "room_types": {pid: room for pid in ids}})
        post(owner, f"/api/v1/bookings/{bk['id']}/transition", {"target": "RESERVED"})
        inv = post(owner, f"/api/v1/bookings/{bk['id']}/issue-invoice")
        if n % 4:  # sebagian besar sudah DP
            for line in inv["lines"]:
                pay = post(owner, "/api/v1/payments", {"invoice": inv["id"], "amount_idr": 10_000_000, "kind": "DP", "method": "TRANSFER", "bank_account": bank["id"],
                                                       "received_at": at(2026, 10, 10 + n % 18), "reference": f"DP-{line['participant_id'][:6].upper()}",
                                                       "allocations": [{"booking_participant_id": line["participant_id"], "amount_idr": 10_000_000}]})
                post(owner, f"/api/v1/payments/{pay['id']}/verify")
            post(owner, f"/api/v1/bookings/{bk['id']}/transition", {"target": "CONFIRMED"})
        made += size
print("rombongan tambahan", n)
print("SELESAI", EMAIL, PASSWORD)
