"use client";

import Link from "next/link";
import { useState } from "react";
import { apiFetch, problemMessage } from "@/lib/api";
import { siteUrl } from "@/lib/siteUrls";
import { Btn, FormCheckbox, FormField } from "@/components/workspace/ui";

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
        {/* Struktur form = form kontak web_template 1:1 (form-group ritme
            55px, field float-label, checkbox bulat template, submit
            circle-xl rata kanan). */}
        <form onSubmit={onSubmit} className="mt-8">
          <FormField
            label="Nama travel"
            htmlFor="travel_name"
            required
            value={travelName}
            onChange={(e) => setTravelName(e.target.value)}
            placeholder="PT Bahagia Selamat"
          />
          <FormField
            label="Alamat workspace"
            htmlFor="slug"
            required
            pattern="[a-z0-9-]+"
            value={slug}
            onChange={(e) => setSlug(e.target.value.toLowerCase())}
            placeholder="bahagia-selamat"
            suffix=".umrovia.com"
          />
          <FormField
            label="Email owner"
            htmlFor="reg_email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="owner@travelanda.com"
          />
          <FormField
            label="Password"
            htmlFor="reg_password"
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <div className="form-group">
            <FormCheckbox
              id="agree_terms"
              checked={agreed}
              onChange={setAgreed}
              required
              label={
                <>
                  Saya menyetujui Syarat Layanan dan{" "}
                  <Link href={siteUrl("/kebijakan-privasi")} target="_blank" rel="noreferrer" className="text-primary hover:text-primary-hover">Kebijakan Privasi Umrovia</Link>.
                </>
              }
            />
          </div>
          <div className="form-submit">
            <Btn type="submit" size="circle-xl" loading={busy}>
              Daftar
            </Btn>
          </div>
        </form>
        {message && (
          <div className="mt-4 border border-border p-3 text-sm">
            <p className="text-ink">{message}</p>
            {devUrl && (
              <a
                href={devUrl}
                target="_blank"
                rel="noreferrer"
                className="mt-1 break-all font-medium text-primary hover:text-primary-hover"
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
