"use client";

import { useEffect, useRef, useState } from "react";
import { Btn, EmptyState, ErrorState, FormCheckbox, FormField, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type Paginated, type PlatformAuditRow } from "@/lib/api";

export default function PlatformAuditPage() {
  const [draft, setDraft] = useState({tenant: "", action: ""});
  const [filters, setFilters] = useState({tenant: "", action: "", platform: false});
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paginated<PlatformAuditRow> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sequence = useRef(0);
  useEffect(() => {
    const current = ++sequence.current;
    const params = new URLSearchParams({page: String(page)});
    if (filters.tenant) params.set("tenant", filters.tenant);
    if (filters.action) params.set("action", filters.action);
    if (filters.platform) params.set("platform", "1");
    void apiFetch<Paginated<PlatformAuditRow>>(`/platform/audit?${params}`).then((r) => {
      if (current !== sequence.current) return;
      if (r.ok) setData(r.data); else setError(problemMessage(r.error));
    });
  }, [filters, page]);

  return <div>
    <h1 className="text-2xl font-bold">Audit</h1>
    <p className="mt-1 text-sm text-muted">Jejak aksi seluruh platform. Pelaku tersamar dan rincian perubahan dibatasi ke kolom aman (tanpa teks bebas dari travel).</p>
    {error ? <div className="mt-4"><ErrorState message={error} /></div> : null}
    <section className="card mt-6 p-6">
      <form className="notification-filters grid items-end gap-x-4 gap-y-8 md:grid-cols-4" onSubmit={(event) => {event.preventDefault(); setPage(1); setFilters({...filters, ...draft});}}>
        <FormField label="Slug travel" htmlFor="audit-tenant" value={draft.tenant} onChange={(event) => setDraft({...draft, tenant: event.target.value.trim()})} />
        <FormField label="Awalan aksi (mis. platform., payment.)" htmlFor="audit-action" value={draft.action} onChange={(event) => setDraft({...draft, action: event.target.value.trim()})} />
        <FormCheckbox id="audit-platform" label="Hanya tindakan staf platform" checked={filters.platform} onChange={(checked) => {setPage(1); setFilters({...filters, platform: checked});}} />
        <Btn type="submit">Terapkan</Btn>
      </form>
      {data === null ? <LoadingState /> : data.results.length === 0 ? <div className="mt-4"><EmptyState title="Tidak ada catatan" /></div> : <>
        <div className="mt-6 overflow-x-auto"><table className="w-full min-w-200 text-left text-sm">
          <thead><tr className="border-b border-border text-muted"><th className="py-3 pr-4">Waktu</th><th className="py-3 pr-4">Aksi</th><th className="py-3 pr-4">Travel</th><th className="py-3 pr-4">Pelaku</th><th className="py-3">Rincian</th></tr></thead>
          <tbody>{data.results.map((row) => <tr key={row.id} className="border-b border-border align-top">
            <td className="whitespace-nowrap py-3 pr-4">{new Date(row.occurred_at).toLocaleString("id-ID", {dateStyle: "medium", timeStyle: "medium"})}</td>
            <td className="py-3 pr-4"><span className="font-mono text-xs">{row.action}</span><p className="mt-1 text-xs text-muted">{row.object_type}</p></td>
            <td className="py-3 pr-4">{row.tenant ?? "—"}</td>
            <td className="py-3 pr-4">{row.actor} {row.actor_platform ? <StatusBadge tone="danger">Platform</StatusBadge> : null}</td>
            <td className="py-3 text-xs text-muted">{Object.entries(row.changes).map(([key, value]) => `${key}: ${String(value)}`).join(" · ") || "—"}</td>
          </tr>)}</tbody>
        </table></div>
        <div className="mt-4 flex flex-wrap items-center gap-3 text-sm"><Btn size="xs" variant="solid" disabled={!data.previous} onClick={() => setPage((v) => v - 1)}>Sebelumnya</Btn><span>Halaman {page}</span><Btn size="xs" variant="solid" disabled={!data.next} onClick={() => setPage((v) => v + 1)}>Berikutnya</Btn></div>
      </>}
    </section>
  </div>;
}
