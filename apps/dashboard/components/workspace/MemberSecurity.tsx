"use client";

import { useEffect, useState } from "react";
import { Btn, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type MembershipRow } from "@/lib/api";
import { FloatingNotice } from "@/components/workspace/FloatingNotice";

export type LoginRow = {action: string; label: string; occurred_at: string; ip: string | null; user_agent: string; reason: string};

/** Ringkas user agent → "Chrome · macOS". */
export function deviceLabel(agent: string) {
  if (!agent) return "Perangkat tidak dikenal";
  const browser = /Edg\//.test(agent) ? "Edge" : /Chrome\//.test(agent) ? "Chrome" : /Firefox\//.test(agent) ? "Firefox" : /Safari\//.test(agent) ? "Safari" : "Browser";
  const os = /Android/.test(agent) ? "Android" : /iPhone|iPad/.test(agent) ? "iOS" : /Mac OS X/.test(agent) ? "macOS" : /Windows/.test(agent) ? "Windows" : /Linux/.test(agent) ? "Linux" : "";
  return [browser, os].filter(Boolean).join(" · ");
}

export function LoginHistory({rows}: {rows: LoginRow[]}) {
  if (rows.length === 0) return <p className="mt-3 text-sm text-muted">Belum ada aktivitas masuk tercatat.</p>;
  return <ul className="mt-3 divide-y divide-border text-sm">{rows.map((row, index) => <li key={`${row.occurred_at}-${index}`} className="flex flex-wrap items-center justify-between gap-2 py-2">
    <span className="flex items-center gap-2"><StatusBadge tone={row.action === "auth.login_failed" ? "danger" : row.action === "auth.login" ? "success" : "neutral"}>{row.label}</StatusBadge>
      <span className="text-xs text-muted">{deviceLabel(row.user_agent)}{row.ip ? ` · ${row.ip}` : ""}{row.reason === "invalid_credentials" ? " · sandi salah" : ""}</span></span>
    <span className="text-xs text-muted">{new Date(row.occurred_at).toLocaleString("id-ID", {dateStyle: "medium", timeStyle: "short"})}</span>
  </li>)}</ul>;
}

/** AUTH-05: Owner menangguhkan/mengaktifkan anggota, mengirim reset sandi, mengakhiri sesi, melihat riwayat masuk. */
export function MemberSecurity({member, self, onChanged, onClose}: {member: MembershipRow; self: boolean; onChanged: (message: string) => void; onClose: () => void}) {
  const [rows, setRows] = useState<LoginRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void apiFetch<{results: LoginRow[]}>(`/memberships/${member.id}/logins`).then((r) => {if (r.ok) setRows(r.data.results); else setError(problemMessage(r.error));});
  }, [member.id]);

  async function act(action: string, confirmText: string, done: string) {
    if (!window.confirm(confirmText)) return;
    setBusy(true); setError(null);
    const result = await apiFetch(`/memberships/${member.id}/${action}`, {method: "POST", body: "{}"});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    onChanged(done);
  }
  const who = member.user.full_name || member.user.email;
  return <section className="card mt-6 p-6" aria-label={`Keamanan akun ${who}`}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="font-semibold">Keamanan akun · {who}</h2>
      <Btn size="xs" variant="tint" onClick={onClose}>Tutup</Btn>
    </div>
    <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />
    {!self ? <div className="mt-4 flex flex-wrap gap-2">
      {member.status === "ACTIVE" ? <Btn size="xs" variant="danger" disabled={busy} onClick={() => void act("suspend", `Tangguhkan ${who}? Ia tidak dapat membuka workspace ini sampai diaktifkan kembali.`, `${who} ditangguhkan.`)}>Tangguhkan</Btn> : null}
      {member.status === "SUSPENDED" ? <Btn size="xs" disabled={busy} onClick={() => void act("reactivate", `Aktifkan kembali ${who}?`, `${who} aktif kembali.`)}>Aktifkan kembali</Btn> : null}
      <Btn size="xs" variant="tint" disabled={busy} onClick={() => void act("reset-password", `Kirim tautan reset sandi ke ${member.user.email}?`, `Tautan reset sandi dikirim ke ${member.user.email}.`)}>Kirim reset sandi</Btn>
      <Btn size="xs" variant="tint" disabled={busy} onClick={() => void act("revoke-sessions", `Keluarkan ${who} dari semua perangkat sekarang?`, `Semua sesi ${who} diakhiri.`)}>Akhiri semua sesi</Btn>
    </div> : <p className="mt-3 text-sm text-muted">Untuk akun Anda sendiri, gunakan halaman Akun Saya.</p>}
    <h3 className="mt-6 text-sm font-semibold">Riwayat masuk terakhir</h3>
    {rows === null ? <LoadingState /> : <LoginHistory rows={rows} />}
  </section>;
}
