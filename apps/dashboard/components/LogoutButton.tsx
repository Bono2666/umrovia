"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiFetch, problemMessage } from "@/lib/api";
import { Btn } from "@/components/workspace/ui";

/**
 * Tombol keluar (S02) — POST /auth/logout dengan CSRF
 * (GET /auth/csrf dahulu, otomatis oleh apiFetch).
 *
 * Ketahanan (perbaikan S06): `busy` selalu di-reset — baik saat request
 * gagal/timeout maupun sesudah sukses SEBELUM navigasi, sehingga tombol
 * tidak pernah bisa macet menampilkan "Keluar…" selamanya; kegagalan
 * ditampilkan sebagai pesan agar bisa dicoba ulang.
 */
/** `onLoggedOut` mengganti navigasi ke /login (mis. tetap di halaman undangan). */
export function LogoutButton({ onLoggedOut }: { onLoggedOut?: () => void } = {}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onLogout() {
    if (busy) return;
    setBusy(true);
    setError(null);
    const result = await apiFetch<{ status: string }>("/auth/logout", {
      method: "POST",
    });
    setBusy(false);
    if (result.ok) {
      if (onLoggedOut) onLoggedOut();
      else router.push("/login");
      return;
    }
    setError(problemMessage(result.error));
  }

  return (
    <span className="flex items-center gap-2">
      {error ? (
        <span className="max-w-48 truncate text-xs text-danger" role="alert">
          {error}
        </span>
      ) : null}
      <Btn variant="tint" size="xs" onClick={onLogout} disabled={busy}>
        {busy ? "Keluar…" : "Keluar"}
      </Btn>
    </span>
  );
}
