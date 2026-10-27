"""Keamanan sesi (AUTH-02/03): batas idle, batas absolut, dan "keluar dari semua perangkat".

- Idle: cookie & sesi server kedaluwarsa setelah `SESSION_COOKIE_AGE` tanpa
  aktivitas; aktivitas diperbarui paling sering tiap 5 menit agar tidak
  menulis tabel sesi pada setiap request.
- Absolut: sesi berakhir `SESSION_ABSOLUTE_SECONDS` setelah login walau aktif.
- Versi sesi: sesi menyimpan `User.session_version` saat login; bila versi
  pengguna naik (logout semua perangkat, reset sandi), sesi lama ditolak.
"""
import time

from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.models import AnonymousUser

TOUCH_SECONDS = 300


def start_session(request, user):
    request.session["sv"] = user.session_version
    request.session["auth_at"] = request.session["seen_at"] = int(time.time())


class SessionSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            session, now = request.session, int(time.time())
            if "sv" not in session:  # sesi sebelum fitur ini / force_login
                start_session(request, user)
            elif session["sv"] != user.session_version or now - session.get("auth_at", now) > settings.SESSION_ABSOLUTE_SECONDS:
                logout(request)
                request.user = AnonymousUser()
            elif now - session.get("seen_at", 0) > TOUCH_SECONDS:
                session["seen_at"] = now  # memperpanjang batas idle
        return self.get_response(request)
