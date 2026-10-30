"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Btn, EmptyState, FormField, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type Paginated, type PlatformTenant } from "@/lib/api";
import { formatDate, formatIdr } from "@/lib/format";
import { STATE_TONE } from "@/components/platform/tone";
import { FloatingNotice } from "@/components/workspace/FloatingNotice";

export default function PlatformTenantsPage() {
  const [state, setState] = useState("");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paginated<PlatformTenant> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sequence = useRef(0);
  const initialized = useRef(false);
  useEffect(() => {
    const current = ++sequence.current;
    // ?state= dari kartu Ringkasan dipakai sekali saat halaman dibuka.
    const fromUrl = initialized.current ? null : new URLSearchParams(window.location.search).get("state");
    initialized.current = true;
    const query = new URLSearchParams(Object.entries({state: fromUrl ?? state, q: search, page: String(page)}).filter(([, v]) => v)).toString();
    void apiFetch<Paginated<PlatformTenant>>(`/platform/tenants?${query}`).then((r) => {
      if (current !== sequence.current) return;
      if (fromUrl) setState(fromUrl);
      if (r.ok) setData(r.data); else setError(problemMessage(r.error));
    });
  }, [state, search, page]);

  return <div>
    <h1 className="text-2xl font-bold">Tenant</h1>
    <p className="mt-1 text-sm text-muted">Metadata usaha, status, kuota dan hitungan. Email pemilik tersamar; data jamaah tidak ditampilkan. Membuka detail tercatat di audit.</p>
    <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />
    <section className="card mt-6 p-6">
      <form className="notification-filters grid items-end gap-x-4 gap-y-8 md:grid-cols-3" onSubmit={(event) => {event.preventDefault(); setPage(1); setSearch(q.trim());}}>
        <FormField label="Cari nama atau slug" htmlFor="tenant-q" value={q} onChange={(event) => setQ(event.target.value)} onBlur={() => {setPage(1); setSearch(q.trim());}} />
        <FormSelect label="Status" htmlFor="tenant-state" value={state} onChange={(event) => {setPage(1); setState(event.target.value);}}>
          <option value="">Semua</option>{["TRIAL", "ACTIVE", "RESTRICTED", "SUSPENDED", "TERMINATED", "PROVISIONING", "PENDING_EMAIL"].map((s) => <option key={s} value={s}>{s}</option>)}
        </FormSelect>
      </form>
      {data === null ? <LoadingState /> : data.results.length === 0 ? <div className="mt-4"><EmptyState title="Tidak ada travel" /></div> : <>
        <div className="mt-4 overflow-x-auto"><table className="w-full min-w-200 text-left text-sm">
          <thead><tr className="border-b border-border text-muted"><th className="py-3 pr-4">Travel</th><th className="py-3 pr-4">Status</th><th className="py-3 pr-4">Trial</th><th className="py-3 pr-4 text-right">Pengguna</th><th className="py-3 pr-4 text-right">Jamaah aktif</th><th className="py-3 pr-4 text-right">Saldo wallet</th><th className="py-3 text-right">Charge tertunda</th></tr></thead>
          <tbody>{data.results.map((t) => <tr key={t.id} className="border-b border-border align-top">
            <td className="py-3 pr-4"><Link href={`/platform/tenant/${t.id}`} className="font-medium text-primary underline">{t.display_name}</Link><p className="mt-1 text-xs text-muted">{t.slug} · {t.legal_name} · {t.owner_email}</p></td>
            <td className="py-3 pr-4"><StatusBadge tone={STATE_TONE[t.state] ?? "neutral"}>{t.state_label}</StatusBadge></td>
            <td className="py-3 pr-4 text-xs">{t.trial ? `${t.trial.status} · s.d. ${formatDate(t.trial.ends_at)}` : "—"}</td>
            <td className="py-3 pr-4 text-right">{t.members}</td>
            <td className="py-3 pr-4 text-right">{t.usage?.active_participants ?? "—"}</td>
            <td className="py-3 pr-4 text-right tabular-nums">{t.usage ? formatIdr(t.usage.wallet_balance_idr) : "—"}</td>
            <td className="py-3 text-right">{t.usage?.pending_charges ?? 0}</td>
          </tr>)}</tbody>
        </table></div>
        <div className="mt-4 flex flex-wrap items-center gap-3 text-sm"><Btn size="xs" variant="solid" disabled={!data.previous} onClick={() => setPage((v) => v - 1)}>Sebelumnya</Btn><span>Halaman {page} · {data.count} travel</span><Btn size="xs" variant="solid" disabled={!data.next} onClick={() => setPage((v) => v + 1)}>Berikutnya</Btn></div>
      </>}
    </section>
  </div>;
}
