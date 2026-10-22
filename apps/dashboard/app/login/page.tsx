"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch, problemMessage, type UserPayload } from "@/lib/api";

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
        <h1 className="text-2xl font-bold text-primary">Umrovia</h1>
        <p className="mt-1 text-sm text-muted">
          Masuk ke workspace travel Anda
        </p>
        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <div>
            <label className="text-sm font-medium" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              className="input mt-1"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="nama@travelanda.com"
            />
          </div>
          <div>
            <label className="text-sm font-medium" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              className="input mt-1"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </div>
          <button type="submit" className="btn-primary w-full" disabled={busy}>
            {busy ? "Memproses…" : "Masuk"}
          </button>
        </form>
        {message && (
          <p className="mt-4 rounded bg-background p-3 text-sm text-danger">
            {message}
          </p>
        )}
        <p className="mt-4 text-sm text-muted">
          <Link href="/forgot-password" className="text-primary">
            Lupa password?
          </Link>
        </p>
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
