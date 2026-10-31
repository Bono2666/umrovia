"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { apiFetch, problemMessage } from "@/lib/api";
import { Btn, BtnLink, FormField } from "@/components/workspace/ui";

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
        <BtnLink href="/forgot-password">
          Minta tautan baru
        </BtnLink>
      </div>
    );
  }

  if (done) {
    return (
      <div className="mt-4 space-y-4">
        <p className="text-sm text-success">
          Password berhasil diperbarui. Silakan masuk dengan password baru.
        </p>
        <BtnLink href="/login">
          Lanjut masuk
        </BtnLink>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="mt-8">
      <FormField
        label="Password baru"
        htmlFor="new_password"
        type="password"
        required
        minLength={8}
        autoComplete="new-password"
        hint="Minimal 8 karakter"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      {message ? (
        <p className="error-message" role="alert">
          {message}
        </p>
      ) : null}
      <div className="form-footer form-footer--narrow">
        <p className="text--t3-sm text--color-small">
          Gunakan password yang belum pernah dipakai di akun lain.
        </p>
      </div>
      <div className="form-submit">
        <Btn type="submit" size="circle-xl" loading={busy}>
          Simpan
        </Btn>
      </div>
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
