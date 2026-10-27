"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { LogoutButton } from "@/components/LogoutButton";
import { UmroviaMark } from "@/components/UmroviaMark";
import { ThemeToggle } from "@/components/workspace/ThemeToggle";
import { Btn, ErrorState, FormField, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type PlatformSession, type UserPayload } from "@/lib/api";

type Ctx = {session: PlatformSession; can: (perm: string) => boolean; refresh: () => void};
const PlatformContext = createContext<Ctx | null>(null);
export function usePlatform(): Ctx {
  const value = useContext(PlatformContext);
  if (!value) throw new Error("usePlatform di luar PlatformShell");
  return value;
}

const NAV = [
  {href: "/platform", label: "Ringkasan", perm: "platform.console_view"},
  {href: "/platform/tenant", label: "Tenant", perm: "platform.console_view"},
  {href: "/platform/trial", label: "Trial", perm: "platform.console_view"},
  {href: "/platform/billing", label: "Billing", perm: "billing"},
  {href: "/platform/dukungan", label: "Dukungan", perm: "platform.support_manage"},
  {href: "/platform/audit", label: "Audit", perm: "platform.audit_view"},
  {href: "/platform/tarif", label: "Tarif", perm: "platform.console_view"},
];

/**
 * Konsol platform (S18, admin.umrovia.com → /platform): staf platform + MFA.
 * Otorisasi sesungguhnya di server (izin Django + MFA segar per endpoint);
 * shell ini hanya memandu pendaftaran/verifikasi MFA dan menyembunyikan menu.
 */
export function PlatformShell({children}: {children: React.ReactNode}) {
  const router = useRouter();
  const pathname = usePathname();
  const [session, setSession] = useState<PlatformSession | null>(null);
  const [state, setState] = useState<"loading" | "denied" | "ok">("loading");

  const refresh = useCallback(() => {
    void apiFetch<UserPayload>("/me").then((me) => {
      if (!me.ok) {router.replace("/login?next=/platform"); return;}
      void apiFetch<PlatformSession>("/platform/me").then((result) => {
        if (!result.ok) {setState("denied"); return;}
        setSession(result.data); setState("ok");
      });
    });
  }, [router]);
  useEffect(() => {refresh();}, [refresh]);

  if (state === "loading") return <div className="workspace-shell min-h-screen p-8"><LoadingState label="Memuat konsol platform…" /></div>;
  if (state === "denied" || !session) return <Centered title="Akses konsol platform ditolak">
    <p className="mt-2 text-sm text-muted">Akun ini bukan staf platform Umrovia. Konsol hanya untuk tim internal; role travel (termasuk Owner) tidak memberi akses.</p>
    <div className="mt-4 flex justify-center gap-3"><Link className="text-sm text-primary underline" href="/dashboard">Ke dashboard travel</Link><LogoutButton /></div>
  </Centered>;
  if (!session.mfa.enrolled) return <MfaEnroll onDone={refresh} />;
  if (!session.mfa.verified) return <MfaVerify email={session.email} onDone={refresh} />;

  const can = (perm: string) => perm === "billing"
    ? session.permissions.includes("wallet.settle_topup") || session.permissions.includes("billing.approve_adjustment")
    : session.permissions.includes(perm);
  const items = NAV.filter((item) => can(item.perm));
  return <PlatformContext.Provider value={{session, can, refresh}}>
    <div className="workspace-shell min-h-screen">
      <header className="sticky top-0 z-30 border-b border-border bg-surface">
        <div className="flex h-14 items-center gap-3 px-4">
          <Link href="/platform" className="flex items-center gap-2 text-lg font-semibold tracking-tight text-ink"><UmroviaMark className="h-7 w-7 shrink-0" />Umrovia<span className="text-primary">.</span></Link>
          <StatusBadge tone="danger">Konsol platform</StatusBadge>
          <div className="ml-auto flex items-center gap-3">
            <ThemeToggle />
            <span className="hidden text-sm text-muted sm:inline">{session.email}</span>
            <LogoutButton />
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto border-t border-border px-4" aria-label="Menu konsol platform">
          {items.map((item) => {
            const active = item.href === "/platform" ? pathname === "/platform" : pathname.startsWith(item.href);
            return <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined}
              className={`whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium ${active ? "border-primary text-primary" : "border-transparent text-ink hover:text-primary"}`}>{item.label}</Link>;
          })}
        </nav>
      </header>
      <main className="mx-auto w-full max-w-7xl p-4 sm:p-6">{children}</main>
    </div>
  </PlatformContext.Provider>;
}

function Centered({title, children}: {title: string; children: React.ReactNode}) {
  return <div className="workspace-shell flex min-h-screen items-center justify-center p-6">
    <div className="card w-full max-w-md p-8"><p className="flex items-center gap-2 font-semibold"><UmroviaMark className="h-6 w-6" />{title}</p>{children}</div>
  </div>;
}

function MfaEnroll({onDone}: {onDone: () => void}) {
  const [password, setPassword] = useState("");
  const [secret, setSecret] = useState<{secret: string; otpauth_uri: string} | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function start(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    const result = await apiFetch<{secret: string; otpauth_uri: string}>("/platform/mfa/setup", {method: "POST", body: JSON.stringify({password})});
    setBusy(false);
    if (result.ok) {setSecret(result.data); setPassword("");} else setError(problemMessage(result.error));
  }
  async function confirm(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    const result = await apiFetch<PlatformSession & {recovery_codes: string[]}>("/platform/mfa/confirm", {method: "POST", body: JSON.stringify({code})});
    setBusy(false);
    if (result.ok) setCodes(result.data.recovery_codes); else setError(problemMessage(result.error));
  }

  if (codes) return <Centered title="Simpan kode pemulihan">
    <p className="mt-2 text-sm text-muted">MFA aktif. Simpan 10 kode ini di tempat aman; tiap kode hanya bisa dipakai sekali bila perangkat autentikator tidak tersedia. Kode tidak akan ditampilkan lagi.</p>
    <ol className="mt-4 grid grid-cols-2 gap-2 font-mono text-sm">{codes.map((item) => <li key={item} className="border border-border px-2 py-1 text-center">{item}</li>)}</ol>
    <Btn className="mt-5" onClick={onDone}>Saya sudah menyimpan, lanjutkan</Btn>
  </Centered>;
  return <Centered title="Aktifkan MFA konsol platform">
    <p className="mt-2 text-sm text-muted">Konsol platform wajib memakai aplikasi autentikator (Google Authenticator, Microsoft Authenticator, 1Password, dsb.).</p>
    {error ? <div className="mt-4"><ErrorState message={error} /></div> : null}
    {!secret ? <form className="mt-5" onSubmit={start}>
      <FormField label="Konfirmasi password" htmlFor="mfa-password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
      <Btn type="submit" loading={busy} disabled={!password}>Mulai pendaftaran</Btn>
    </form> : <form className="mt-5" onSubmit={confirm}>
      <p className="text-sm">Tambahkan akun baru di aplikasi autentikator dengan kunci berikut (jenis: berbasis waktu):</p>
      <p className="mt-2 break-all border border-border bg-surface p-3 font-mono text-sm tracking-wider">{secret.secret.match(/.{1,4}/g)?.join(" ")}</p>
      <a className="mt-2 inline-block text-xs text-primary underline" href={secret.otpauth_uri}>Buka di aplikasi autentikator (perangkat ini)</a>
      <div className="mt-4"><FormField label="Kode 6 digit dari aplikasi" htmlFor="mfa-code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))} required /></div>
      <Btn type="submit" loading={busy} disabled={code.length !== 6}>Aktifkan MFA</Btn>
    </form>}
  </Centered>;
}

function MfaVerify({email, onDone}: {email: string; onDone: () => void}) {
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    const result = await apiFetch<PlatformSession>("/platform/mfa/verify", {method: "POST", body: JSON.stringify(recovery ? {recovery_code: code} : {code})});
    setBusy(false);
    if (result.ok) onDone(); else {setError(problemMessage(result.error)); setCode("");}
  }
  return <Centered title="Verifikasi MFA">
    <p className="mt-2 text-sm text-muted">Masuk sebagai {email}. Masukkan {recovery ? "salah satu kode pemulihan" : "kode 6 digit dari aplikasi autentikator"} untuk membuka konsol.</p>
    {error ? <div className="mt-4"><ErrorState message={error} /></div> : null}
    <form className="mt-5" onSubmit={submit}>
      <FormField label={recovery ? "Kode pemulihan" : "Kode autentikator"} htmlFor="mfa-verify" inputMode={recovery ? "text" : "numeric"} autoComplete="one-time-code" maxLength={recovery ? 20 : 6} value={code}
        onChange={(event) => setCode(recovery ? event.target.value : event.target.value.replace(/\D/g, ""))} required />
      <div className="flex flex-wrap items-center gap-3">
        <Btn type="submit" loading={busy} disabled={recovery ? code.trim().length < 8 : code.length !== 6}>Verifikasi</Btn>
        <Btn variant="link" onClick={() => {setRecovery(!recovery); setCode(""); setError(null);}}>{recovery ? "Pakai kode autentikator" : "Pakai kode pemulihan"}</Btn>
      </div>
    </form>
    <div className="mt-4"><LogoutButton /></div>
  </Centered>;
}
