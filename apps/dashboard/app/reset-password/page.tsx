"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { apiFetch, problemMessage } from "@/lib/api";

type ResetResponse = { status: string };

function ResetPasswordInner() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    const result = await apiFetch<ResetResponse>("/auth/password/reset", {
      method: "POST",
      body: JSON.stringify({ token, password }),
    });
    setBusy(false);
    if (result.ok) {
      setDone(true);
    } else {
      setMessage(problemMessage(result.error));
    }
  }

  if (!token) {
    return (
      <div className="mt-4 space-y-3">
        <p className="text-sm text-danger">
          Tautan reset tidak memiliki token. Minta tautan baru.
        </p>
        <Link href="/forgot-password" className="btn btn--solid btn--lg block w-full text-center">
          Minta tautan baru
        </Link>
      </div>
    );
  }

  if (done) {
    return (
      <div className="mt-4 space-y-4">
        <p className="text-sm text-success">
          Password berhasil diperbarui. Silakan masuk dengan password baru.
        </p>
        <Link href="/login" className="btn btn--solid btn--lg block w-full text-center">
          Lanjut masuk
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="mt-6 space-y-4">
      <div>
        <label className="text-sm font-medium" htmlFor="new_password">
          Password baru
        </label>
        <input
          id="new_password"
          type="password"
          required
          minLength={8}
          className="input mt-1"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Minimal 8 karakter"
        />
      </div>
      <button type="submit" className="btn btn--solid btn--lg w-full" disabled={busy}>
        {busy ? "Menyimpan…" : "Simpan password baru"}
      </button>
      {message && <p className="text-sm text-danger">{message}</p>}
    </form>
  );
}

/** Reset password (S02) — POST /auth/password/reset, token sekali pakai (T07). */
export default function ResetPasswordPage() {
  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <div className="card w-full max-w-md p-8">
        <h1 className="text-2xl font-bold tracking-tight text-ink">
          Atur ulang password
        </h1>
        <p className="mt-1 text-sm text-muted">
          Masukkan password baru untuk akun Umrovia Anda.
        </p>
        <Suspense
          fallback={<p className="mt-4 text-sm text-muted">Memuat…</p>}
        >
          <ResetPasswordInner />
        </Suspense>
        <p className="mt-6 text-sm text-muted">
          <Link href="/login" className="text-primary">
            Kembali ke halaman masuk
          </Link>
        </p>
      </div>
    </main>
  );
}
