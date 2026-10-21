# Legacy — Aplasi Umrovia v0 (Django + Soft UI templates)

> **STATUS: LEGACY / REFERENSI.** Direktori ini berisi aplikasi Django lama (Django 5.0.6,
> MySQL, template server-side Soft UI) hasil konversi awal dari proyek "Sekolah Islam".
> Kode ini **hanya dipertahankan sebagai referensi logika bisnis travel dan demo interim**
> selama migrasi ke stack SaaS (lihat `../docs/PRODUCT_SPEC_Umrovia_SaaS_v1_2_Development_Plan.md` §19.2).
>
> Jangan tambahkan fitur baru di sini. Fitur baru dikembangkan di `../backend/` (Django/DRF,
> PostgreSQL + RLS) dan `../apps/` (Next.js). Direktori ini dihapus setelah domain logic
> selesai di-port (target: setelah F05/F06 pada roadmap).

## Menjalankan (lokal, opsional)

```bash
cd legacy
# butuh MySQL dengan database `umrovia` (atau set DATABASE_URL)
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Login admin mengikuti data masing-masing. Modul: Pengguna/Posisi/Menu/Auth + domain travel
(Agen, Paket, Keberangkatan, Jamaah, Booking, Invoice, Pembayaran).
