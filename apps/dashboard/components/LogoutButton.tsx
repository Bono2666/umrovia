"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiFetch } from "@/lib/api";

/**
 * Tombol keluar (S02) — POST /auth/logout dengan CSRF
 * (GET /auth/csrf dahulu, otomatis oleh apiFetch).
 */
export function LogoutButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function onLogout() {
    setBusy(true);
    const result = await apiFetch<{ status: string }>("/auth/logout", {
      method: "POST",
    });
    if (result.ok) {
      router.push("/login");
      router.refresh();
    } else {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={onLogout}
      disabled={busy}
      className="border border-border-strong px-3 py-1.5 text-sm font-semibold text-ink transition-colors duration-300 hover:bg-ink hover:text-surface disabled:opacity-60"
    >
      {busy ? "Keluar…" : "Keluar"}
    </button>
  );
}
