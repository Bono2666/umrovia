"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { UmroviaMark } from "@/components/UmroviaMark";
import { LogoutButton } from "@/components/LogoutButton";
import { Btn, BtnLink, FormField, LoadingState } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type PortalInviteInfo, type UserPayload } from "@/lib/api";

/**
 * Terima undangan portal jamaah (S14, Spec §8.4 accept-invite). Email undangan
 * membuktikan kepemilikan untuk akun baru; email yang sudah punya akun wajib
 * login dulu lalu kembali ke tautan ini (`next` dibatasi ke path portal).
 */
export default function PortalInvitePage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [info, setInfo] = useState<PortalInviteInfo | null>(null);
  const [me, setMe] = useState<UserPayload | null>(null);
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const raw = new URLSearchParams(window.location.search).get("token") ?? "";
    Promise.all([
      apiFetch<PortalInviteInfo>(`/portal/invites/inspect?token=${encodeURIComponent(raw)}`),
      apiFetch<UserPayload>("/me"),
    ]).then(([invite, session]) => {
      setToken(raw);
      if (session.ok) setMe(session.data);
      if (invite.ok) {
        setInfo(invite.data);
        setFullName(invite.data.pilgrim_name);
      } else {
        setInfo({ valid: false, code: "invalid", detail: problemMessage(invite.error), travel_name: "", pilgrim_name: "", email: "", account_exists: false });
      }
    });
  }, []);

  async function accept(event?: React.FormEvent) {
    event?.preventDefault();
    setError(null);
    if (info && !info.account_exists && password !== confirm) {
      setError("Konfirmasi password tidak sama.");
      return;
    }
    setBusy(true);
    const result = await apiFetch<{ access_id: string }>("/portal/accept-invite", {
      method: "POST",
      body: JSON.stringify({ token, password, full_name: fullName }),
    });
    setBusy(false);
    if (result.ok) {
      router.replace("/portal");
      return;
    }
    setError(problemMessage(result.error));
  }

  const next = `/portal/undangan?token=${encodeURIComponent(token)}`;

  return (
    <main className="workspace-shell flex flex-1 items-center justify-center p-6">
      <div className="card w-full max-w-md p-8">
        <p className="flex items-center gap-2.5 text-2xl font-bold tracking-tight text-ink">
          <UmroviaMark className="h-8 w-8 shrink-0" />
          Portal Jamaah
        </p>
        {info === null ? (
          <div className="mt-6"><LoadingState label="Memeriksa undangan…" /></div>
        ) : !info.valid ? (
          <>
            <p className="mt-4 text-sm text-danger" role="alert">{info.detail || "Tautan undangan tidak valid."}</p>
            <p className="mt-4 text-sm text-muted">
              Sudah pernah mengaktifkan akses? <Link className="font-semibold text-primary" href="/login?next=/portal">Masuk ke portal</Link>
            </p>
          </>
        ) : (
          <>
            <h1 className="mt-4 text-xl font-semibold">Assalamu&apos;alaikum, {info.pilgrim_name}</h1>
            <p className="mt-2 text-sm text-muted">
              <strong className="text-foreground">{info.travel_name}</strong> mengundang Anda ke portal jamaah untuk melihat jadwal,
              status pembayaran dan mengunggah dokumen perjalanan. Undangan untuk <strong className="text-foreground">{info.email}</strong>.
            </p>
            {error ? <p className="error-message mt-4" role="alert">{error}</p> : null}
            {info.account_exists ? (
              me ? (
                <div className="mt-6 space-y-4">
                  <p className="text-sm">Anda masuk sebagai <strong>{me.email}</strong>.</p>
                  <div className="flex flex-wrap items-center gap-3">
                    <Btn loading={busy} onClick={() => void accept()}>Terima undangan</Btn>
                    <LogoutButton onLoggedOut={() => setMe(null)} />
                  </div>
                </div>
              ) : (
                <div className="mt-6 space-y-3">
                  <p className="text-sm">Email ini sudah memiliki akun Umrovia. Masuk dulu, lalu Anda akan kembali ke halaman ini.</p>
                  <BtnLink href={`/login?next=${encodeURIComponent(next)}`}>Masuk untuk menerima</BtnLink>
                </div>
              )
            ) : me ? (
              <div className="mt-6 space-y-3">
                <p className="text-sm">Anda sedang masuk sebagai <strong>{me.email}</strong>. Keluar dulu untuk membuat akun jamaah dengan email undangan.</p>
                <LogoutButton onLoggedOut={() => setMe(null)} />
              </div>
            ) : (
              <form className="mt-4" onSubmit={accept}>
                <FormField label="Nama lengkap" htmlFor="portal-name" value={fullName} onChange={(event) => setFullName(event.target.value)} required maxLength={150} autoComplete="name" />
                <FormField label="Buat password" htmlFor="portal-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required autoComplete="new-password" hint="Minimal 8 karakter, jangan hanya angka." />
                <FormField label="Ulangi password" htmlFor="portal-confirm" type="password" value={confirm} onChange={(event) => setConfirm(event.target.value)} required autoComplete="new-password" />
                <Btn type="submit" loading={busy} disabled={!password || !confirm}>Aktifkan akses</Btn>
              </form>
            )}
          </>
        )}
      </div>
    </main>
  );
}
