"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Btn, ErrorState, LoadingState } from "@/components/workspace/ui";
import { LoginHistory, type LoginRow } from "@/components/workspace/MemberSecurity";
import { apiFetch, problemMessage } from "@/lib/api";
import { RevealText } from "@/components/marketing/RevealText";

/** AUTH-02/03: riwayat masuk akun sendiri dan keluar dari semua perangkat. */
export default function AccountPage() {
  const router = useRouter();
  const [rows, setRows] = useState<LoginRow[] | null>(null);
  const [me, setMe] = useState<{email: string; full_name: string} | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void apiFetch<{results: LoginRow[]}>("/me/logins").then((r) => {if (r.ok) setRows(r.data.results); else setError(problemMessage(r.error));});
    void apiFetch<{email: string; full_name: string}>("/me").then((r) => {if (r.ok) setMe(r.data);});
  }, []);

  async function logoutAll() {
    if (!window.confirm("Keluar dari semua perangkat, termasuk perangkat ini? Anda perlu masuk kembali.")) return;
    setBusy(true);
    const result = await apiFetch("/auth/logout-all", {method: "POST", body: "{}"});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    router.replace("/login");
  }

  return <div className="workspace-page">
    <RevealText as="h1" variant="title" className="text-2xl font-bold">Akun Saya</RevealText>
    <p className="mt-1 max-w-3xl text-sm text-muted">Sesi berakhir otomatis setelah 2 jam tanpa aktivitas dan paling lama 12 jam sejak masuk. Bila ada aktivitas masuk yang tidak Anda kenali, keluarkan semua perangkat lalu ganti sandi.</p>
    {error ? <div className="mt-4"><ErrorState message={error} /></div> : null}
    <div className="workspace-columns mt-6">
      <section className="card min-w-0 p-6">
        <h2 className="font-semibold">Riwayat masuk</h2>
        {rows === null ? <LoadingState /> : <LoginHistory rows={rows} />}
      </section>
      <section className="card min-w-0 p-6">
        <h2 className="font-semibold">Sesi & keamanan</h2>
        {me ? <p className="mt-2 text-sm">{me.full_name || me.email}<span className="block text-xs text-muted">{me.email}</span></p> : null}
        <p className="mt-4 text-sm text-muted">Mengakhiri sesi di semua browser dan ponsel yang sedang masuk dengan akun ini.</p>
        <Btn className="mt-4" variant="danger" loading={busy} onClick={() => void logoutAll()}>Keluar dari semua perangkat</Btn>
        <p className="mt-6 text-sm text-muted">Lupa atau ingin mengganti sandi? Gunakan tautan “Lupa sandi” di halaman masuk; semua sesi lama otomatis berakhir setelah sandi diganti.</p>
      </section>
    </div>
  </div>;
}
