"use client";

import Link from "next/link";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { Btn, FormField } from "@/components/workspace/ui";

type ForgotResponse = { status: string; dev_reset_url?: string };

/**
 * Lupa password (S02) — POST /auth/password/forgot (Spec §8.1).
 * Respons selalu generik ("if_registered") — anti-enumerasi.
 */
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [devUrl, setDevUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    const result = await apiFetch<ForgotResponse>("/auth/password/forgot", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    setBusy(false);
    if (result.ok) {
      setSent(true);
      setDevUrl(result.data.dev_reset_url ?? null);
    }
  }

  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <div className="card w-full max-w-md p-8">
        <h1 className="text-2xl font-bold tracking-tight text-ink">Lupa password</h1>
        <p className="mt-1 text-sm text-muted">
          Masukkan email akun Anda — kami kirim tautan untuk mengatur ulang
          password.
        </p>

        {!sent ? (
          <form onSubmit={onSubmit} className="mt-8">
            <FormField
              label="Email"
              htmlFor="fp_email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="nama@travelanda.com"
            />
            <div className="form-footer form-footer--narrow">
              <p className="text--t3-sm text--color-small">
                Tautan reset berlaku 60 menit dan hanya dikirim bila email
                terdaftar.
              </p>
            </div>
            <div className="form-submit">
              <Btn type="submit" size="circle-xl" loading={busy}>
                Kirim
              </Btn>
            </div>
          </form>
        ) : (
          <div className="mt-4 space-y-3 border border-border p-3 text-sm">
            <p className="text-ink">
              Jika email terdaftar, tautan reset sudah dikirim. Periksa kotak
              masuk Anda (berlaku 60 menit).
            </p>
            {devUrl && (
              <a
                href={devUrl}
                target="_blank"
                rel="noreferrer"
                className="break-all font-medium text-primary hover:text-primary-hover"
              >
                Buka tautan reset (mode pengembangan)
              </a>
            )}
          </div>
        )}

        <p className="mt-6 text-sm text-muted">
          <Link href="/login" className="text-primary">
            Kembali ke halaman masuk
          </Link>
        </p>
      </div>
    </main>
  );
}
