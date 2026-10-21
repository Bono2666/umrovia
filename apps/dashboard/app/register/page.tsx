"use client";

import Link from "next/link";
import { useState } from "react";
import { apiFetch } from "@/lib/api";

/**
 * Registrasi travel baru (S01 placeholder UI — provisioning di S02/F02, Spec §7.1).
 * Field mengikuti alur signup: email, password, nama travel, slug, persetujuan T&C.
 */
export default function RegisterPage() {
  const [travelName, setTravelName] = useState("");
  const [slug, setSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const result = await apiFetch<{ detail?: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        travel_name: travelName,
        slug,
        agree_terms: agreed,
      }),
    });
    setMessage(
      result.ok
        ? "Pendaftaran dikirim (stub). Cek email untuk verifikasi."
        : `Registrasi belum aktif di S01 — akan diisi pada S02. (${result.error.code})`,
    );
  }

  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <div className="card w-full max-w-md p-8">
        <h1 className="text-2xl font-bold text-primary">
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
          <button type="submit" className="btn-primary w-full">
            Buat workspace
          </button>
        </form>
        {message && <p className="mt-4 text-sm text-muted">{message}</p>}
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
