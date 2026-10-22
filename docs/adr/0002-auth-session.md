# ADR-0002: Autentikasi Berbasis Sesi Cookie (bukan JWT)

**Status:** Diterima (S02, 22 Okt 2026)
**Konteks:** Roadmap S02 + Spec §8.1 ("OAuth/OIDC-compatible session **atau** JWT
short-lived access dengan rotating refresh; CSRF wajib untuk cookie auth"), §7.1, T07

## Keputusan

Autentikasi dashboard travel memakai **sesi Django berbasis cookie** (`sessionid`,
`HttpOnly`, `SameSite=Lax`) + **CSRF token** untuk request state-changing:

- `POST /auth/login` → `django.contrib.auth.login()` men-set sesi; `GET /me` dan
  endpoint lain membaca sesi via `SessionAuthentication`.
- `POST /auth/logout` → `session.flush()`; wajib header `X-CSRFToken` yang diambil dari
  `GET /auth/csrf` (cookie `csrftoken` tidak `HttpOnly`, dibaca JS).
- Tidak ada endpoint `/auth/refresh` — sesi tidak punya masa berlaku token pendek;
  sesi berakhir saat logout / browser ditutup (konfigurasi `SESSION_COOKIE_AGE` menyusul).

## Mengapa sesi, bukan JWT (untuk sekarang)

1. **Spec mengizinkan keduanya.** Pilihan sesi adalah implementasi paling kecil yang
   memenuhi §8.1 untuk S02 tanpa mengorbankan keamanan.
2. **Revocability.** Logout/penghapusan akun langsung efektif (server-side session
   store di Redis/DB); JWT access token tidak bisa dicabut sebelum kedaluwarsa.
3. **Kompatibilitas browser alami.** Cookie diatur otomatis oleh browser, cocok untuk
   app di `app.umrovia.com` pada domain yang sama (situs+subdomain = same-site,
   `SameSite=Lax` aman untuk XHR lintas-port/subdomain).
4. **Risiko CSRF ditangani** dengan pola standar: `ensure_csrf_cookie` + header
   `X-CSRFToken` di setiap mutasi (helper `apiFetch` di frontend melakukannya otomatis).

## Konsekuensi & batasan

- **Portal jamaah (S14) & integrasi pihak ketiga** kemungkinan butuh token stateless
  (magic-link, API key, atau JWT singkat) — keputusan itu di-ADR terpisah saat F06.
- Rate limit login/register memakai `ScopedRateThrottle` + cache (Redis di compose,
  locmem lokal); laju di `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]` (mis. login 10/menit).
- Token sekali-pakai (verifikasi email, reset password) disimpan sebagai **SHA-256**
  dengan `expires_at` + `used_at` — kebocoran DB tidak memungkinkan pemalsuan link
  (model `identity.AuthToken`, TTL 24 jam / 60 menit).
- Registrasi **anti-enumeration**: respons register/resend/forgot selalu generik;
  email terdaftar tetap menerima respons identik.
