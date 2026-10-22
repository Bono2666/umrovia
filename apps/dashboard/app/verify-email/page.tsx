"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { apiFetch, problemMessage } from "@/lib/api";

type VerifyResponse = { status: string; email?: string };
type ResendResponse = { status: string; message?: string };

function VerifyEmailInner() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [state, setState] = useState<"loading" | "verified" | "error">(() =>
    token ? "loading" : "error",
  );
  const [message, setMessage] = useState(() =>
    token ? "" : "Token verifikasi tidak ada di tautan. Minta link baru.",
  );
  const [resendEmail, setResendEmail] = useState("");
  const [resendDone, setResendDone] = useState(false);

  useEffect(() => {
    if (!token) return;
    let active = true;
    apiFetch<VerifyResponse>("/auth/verify-email", {
      method: "POST",
      body: JSON.stringify({ token }),
    }).then((result) => {
      if (!active) return;
      if (result.ok) {
        setState("verified");
      } else {
        setState("error");
        setMessage(problemMessage(result.error));
      }
    });
    return () => {
      active = false;
    };
  }, [token]);

  async function onResend(event: React.FormEvent) {
    event.preventDefault();
    await apiFetch<ResendResponse>("/auth/resend-verification", {
      method: "POST",
      body: JSON.stringify({ email: resendEmail }),
    });
    setResendDone(true); // respons selalu generik (anti-enumeration)
  }

  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <div className="card w-full max-w-md p-8">
        <h1 className="text-2xl font-bold tracking-tight text-ink">Verifikasi email</h1>

        {state === "loading" && (
          <p className="mt-4 text-sm text-muted">Memverifikasi…</p>
        )}

        {state === "verified" && (
          <div className="mt-4 space-y-4">
            <p className="text-sm text-success">
              Email terverifikasi — workspace travel Anda sudah aktif.
            </p>
            <Link href="/login" className="btn-primary block w-full text-center">
              Lanjut masuk
            </Link>
          </div>
        )}

        {state === "error" && (
          <div className="mt-4 space-y-4">
            <p className="text-sm text-danger">{message}</p>
            {!resendDone ? (
              <form onSubmit={onResend} className="space-y-3">
                <label className="text-sm font-medium" htmlFor="resend_email">
                  Minta link verifikasi baru
                </label>
                <input
                  id="resend_email"
                  type="email"
                  required
                  className="input mt-1 w-full"
                  value={resendEmail}
                  onChange={(e) => setResendEmail(e.target.value)}
                  placeholder="nama@travelanda.com"
                />
                <button type="submit" className="btn-primary w-full">
                  Kirim ulang link
                </button>
              </form>
            ) : (
              <p className="text-sm text-muted">
                Jika email terdaftar, link baru sudah dikirim. Periksa kotak
                masuk Anda.
              </p>
            )}
            <p className="text-sm text-muted">
              <Link href="/login" className="text-primary">
                Kembali ke halaman masuk
              </Link>
            </p>
          </div>
        )}
      </div>
    </main>
  );
}

/** Verifikasi email (S02) — POST /auth/verify-email (Spec §7.1 langkah 2–3, T07). */
export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <main className="flex flex-1 items-center justify-center p-6">
          <p className="text-sm text-muted">Memverifikasi…</p>
        </main>
      }
    >
      <VerifyEmailInner />
    </Suspense>
  );
}
