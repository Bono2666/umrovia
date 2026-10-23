"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, problemMessage, type UserPayload } from "@/lib/api";
import { Btn, FormField } from "@/components/workspace/ui";

/**
 * Login (S02) — POST /auth/login (session cookie + rate limit, Spec §8.1).
 * Bila sudah sesi aktif, langsung arahkan ke /dashboard.
 */
export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    apiFetch<UserPayload>("/me").then((result) => {
      if (active && result.ok) router.replace("/dashboard");
    });
    return () => {
      active = false;
    };
  }, [router]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    const result = await apiFetch<UserPayload>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    if (result.ok) {
      router.push("/dashboard");
      return;
    }
    setBusy(false);
    if (result.error.code === "email_not_verified") {
      setMessage(
        "Email belum diverifikasi. Cek kotak masuk Anda — atau minta link baru di halaman registrasi.",
      );
    } else {
      setMessage(problemMessage(result.error));
    }
  }

  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <div className="card w-full max-w-md p-8">
        <h1 className="text-2xl font-bold tracking-tight text-ink">Umrovia</h1>
        <p className="mt-1 text-sm text-muted">
          Masuk ke workspace travel Anda
        </p>
        {/* Struktur form = form kontak web_template 1:1: form-group per
            field, error-message, form-footer--narrow, submit circle-xl
            rata kanan (template: .text--right:md). */}
        <form onSubmit={onSubmit} className="mt-8">
          <FormField
            label="Email"
            htmlFor="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="nama@travelanda.com"
          />
          <FormField
            label="Password"
            htmlFor="password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
          />
          {message ? (
            <p className="error-message" role="alert">
              {message}
            </p>
          ) : null}
          <div className="form-footer form-footer--narrow">
            <p className="text--t3-sm text--color-small">
              Lupa password?{" "}
              <Link href="/forgot-password" className="text-primary">
                Pulihkan lewat email
              </Link>
            </p>
          </div>
          <div className="form-submit">
            <Btn type="submit" size="circle-xl" loading={busy}>
              Masuk
            </Btn>
          </div>
        </form>
        <p className="mt-6 text-sm text-muted">
          Belum punya akun?{" "}
          <Link href="/register" className="font-semibold text-primary">
            Coba gratis 30 hari
          </Link>
        </p>
      </div>
    </main>
  );
}
