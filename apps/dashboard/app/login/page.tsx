"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";
import { apiFetch, problemMessage, type UserPayload } from "@/lib/api";
import { isPlatformLogin, isPortalNext, landingPath, nextParam } from "@/lib/landing";
import { UmroviaLogo } from "@/components/UmroviaLogo";
import { Btn, FormField } from "@/components/workspace/ui";

/**
 * Login (S02) — POST /auth/login (session cookie + rate limit, Spec §8.1).
 * Bila sudah sesi aktif, langsung arahkan ke /dashboard.
 *
 * Dipakai bersama staf travel, jamaah dan staf platform. Dari portal (`?next=/portal…`)
 * dan konsol platform (host admin) tidak ada tautan daftar: akun portal hanya lewat
 * undangan travel, akun platform hanya dibuat tim internal.
 */
const noSubscribe = () => () => {};

/** Tujuan login: `next` dari URL; di host admin tanpa `next` → konsol platform. */
function loginNext(): string | null {
  return nextParam() ?? (isPlatformLogin(null) ? "/platform" : null);
}

export default function LoginPage() {
  const router = useRouter();
  // Dibaca dari URL tanpa useSearchParams (butuh Suspense); server selalu false → tanpa mismatch hidrasi.
  const portal = useSyncExternalStore(noSubscribe, () => isPortalNext(nextParam()), () => false);
  const platform = useSyncExternalStore(noSubscribe, () => isPlatformLogin(nextParam()), () => false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    apiFetch<UserPayload>("/me").then((result) => {
      if (active && result.ok) router.replace(landingPath(result.data, loginNext()));
    });
    return () => {
      active = false;
    };
  }, [router]);

  // cacheComponents menyimpan halaman yang ditinggalkan beserta state-nya (React Activity).
  // Tombol sengaja tetap "loading" sampai pindah halaman setelah login sukses; tanpa reset ini,
  // kembali ke /login (mis. keluar dari portal) menampilkan tombol Masuk yang loading terus.
  useEffect(() => () => {
    setBusy(false);
    setPassword("");
  }, []);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    const result = await apiFetch<UserPayload>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    if (result.ok) {
      router.push(landingPath(result.data, loginNext()));
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
        <h1 aria-label="Umrovia"><UmroviaLogo /></h1>
        <p className="mt-3 text-sm text-muted">
          {platform ? "Masuk ke konsol platform" : portal ? "Masuk ke portal jamaah" : "Masuk ke workspace travel atau portal jamaah"}
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
        {platform ? (
          <p className="mt-6 text-sm text-muted">
            Konsol platform hanya untuk tim internal Umrovia.
          </p>
        ) : portal ? (
          <p className="mt-6 text-sm text-muted">
            Akses portal diberikan lewat undangan email dari travel Anda. Belum menerima
            undangan? Hubungi travel tempat Anda mendaftar.
          </p>
        ) : (
          <p className="mt-6 text-sm text-muted">
            Belum punya akun?{" "}
            <Link href="/register" className="font-semibold text-primary">
              Coba gratis 30 hari
            </Link>
          </p>
        )}
      </div>
    </main>
  );
}
