"use client";

import { useEffect } from "react";
import { SESSION_EXPIRED_EVENT } from "./api";

/** Login yang kembali ke halaman saat ini setelah berhasil masuk. */
export function loginReturningHere() {
  return `/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
}

/**
 * Dipasang di shell halaman yang butuh login: sesi berakhir → login, lalu kembali ke halaman ini.
 * Muat ulang penuh (bukan router), karena cacheComponents menyimpan state halaman yang sudah
 * ditinggalkan — mis. "belum diberi akses" dari jawaban 403 tadi — dan menampilkannya lagi
 * setelah login.
 */
export function useSessionExpiry() {
  useEffect(() => {
    const expire = () => window.location.replace(loginReturningHere());
    window.addEventListener(SESSION_EXPIRED_EVENT, expire);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, expire);
  }, []);
}
