"use client";

import Link from "next/link";
import { useState } from "react";
import { apiFetch } from "@/lib/api";

/**
 * Login (S01 placeholder UI — endpoint /auth/login diimplementasikan di S02/F02).
 * Spec §8.1: POST /auth/login, rate limit, session/JWT + CSRF untuk cookie auth.
 */
export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const result = await apiFetch<{ detail?: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setMessage(
      result.ok
        ? "Login berhasil (stub)."
        : `Login belum aktif di S01 — akan diisi pada S02. (${result.error.code})`,
    );
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
          <button type="submit" className="btn-primary w-full">
            Masuk
          </button>
        </form>
        {message && <p className="mt-4 text-sm text-muted">{message}</p>}
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
