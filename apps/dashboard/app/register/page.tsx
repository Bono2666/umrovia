"use client";

import Link from "next/link";
import { useState } from "react";
import { apiFetch, problemMessage } from "@/lib/api";

type RegisterResponse = {
  status: string;
  message?: string;
  dev_verification_url?: string;
};

/**
 * Registrasi travel baru (S02) — POST /auth/register (Spec §7.1, §8.1):
 * email, password, nama travel, slug, persetujuan T&C → link verifikasi email.
 */
export default function RegisterPage() {
  const [travelName, setTravelName] = useState("");
  const [slug, setSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [devUrl, setDevUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    setDevUrl(null);
    const result = await apiFetch<RegisterResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        travel_name: travelName,
        slug,
        agree_terms: agreed,
      }),
    });
    setBusy(false);
    if (result.ok) {
      setMessage(result.data.message ?? "Link verifikasi sudah dikirim.");
      setDevUrl(result.data.dev_verification_url ?? null);
      return;
    }
    setMessage(problemMessage(result.error));
  }

  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <div className="card w-full max-w-md p-8">
        <h1 className="text-2xl font-bold tracking-tight text-ink">
          Coba Umrovia gratis
        </h1>
        <p className="mt-1 text-sm text-muted">
          30 hari trial · tanpa kartu kredit · 20 booking dummy
        </p>
        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <div>
            <label className="text-sm font-medium" htmlFor="travel_name">
              Nama travel
            </label>
            <input
              id="travel_name"
              required
              className="input mt-1"
              value={travelName}
              onChange={(e) => setTravelName(e.target.value)}
              placeholder="PT Bahagia Selamat"
            />
          </div>
          <div>
            <label className="text-sm font-medium" htmlFor="slug">
              Alamat workspace
            </label>
            <div className="mt-1 flex items-center gap-2">
              <input
                id="slug"
                required
                pattern="[a-z0-9-]+"
                className="input"
                value={slug}
                onChange={(e) => setSlug(e.target.value.toLowerCase())}
                placeholder="bahagia-selamat"
              />
              <span className="text-sm whitespace-nowrap text-muted">
                .umrovia.com
              </span>
            </div>
          </div>
          <div>
            <label className="text-sm font-medium" htmlFor="reg_email">
              Email owner
            </label>
            <input
              id="reg_email"
              type="email"
              required
              className="input mt-1"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="owner@travelanda.com"
            />
          </div>
          <div>
            <label className="text-sm font-medium" htmlFor="reg_password">
              Password
            </label>
            <input
              id="reg_password"
              type="password"
              required
              minLength={8}
              className="input mt-1"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <label className="flex items-start gap-2 text-sm text-muted">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              required
              className="mt-0.5"
            />
            Saya menyetujui Syarat Layanan dan Kebijakan Privasi Umrovia.
          </label>
          <button type="submit" className="btn btn--solid btn--lg w-full" disabled={busy}>
            {busy ? "Membuat workspace…" : "Buat workspace"}
          </button>
        </form>
        {message && (
          <div className="mt-4 border border-border p-3 text-sm">
            <p className="text-ink">{message}</p>
            {devUrl && (
              <a
                href={devUrl}
                target="_blank"
                rel="noreferrer"
                className="mt-1 break-all font-medium text-primary underline"
              >
                Buka link verifikasi (mode pengembangan)
              </a>
            )}
          </div>
        )}
        <p className="mt-6 text-sm text-muted">
          Sudah punya akun?{" "}
          <Link href="/login" className="font-semibold text-primary">
            Masuk
          </Link>
        </p>
      </div>
    </main>
  );
}
