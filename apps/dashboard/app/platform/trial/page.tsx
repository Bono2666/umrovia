"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { STATE_TONE } from "@/components/platform/tone";
import { EmptyState, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type PlatformTrial } from "@/lib/api";
import { formatDate, formatRemaining } from "@/lib/format";
import { FloatingNotice } from "@/components/workspace/FloatingNotice";

type Row = PlatformTrial & {tenant_id: string; slug: string; display_name: string; tenant_state: string};

export default function PlatformTrialsPage() {
  const [status, setStatus] = useState("");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void apiFetch<{results: Row[]}>(`/platform/trials${status ? `?status=${status}` : ""}`).then((r) => (r.ok ? setRows(r.data.results) : setError(problemMessage(r.error))));
  }, [status]);
  return <div>
    <h1 className="text-2xl font-bold">Trial</h1>
    <p className="mt-1 text-sm text-muted">Trial 30 hari tanpa tagihan; berakhir otomatis menjadi aktif. Perpanjangan dilakukan dari detail tenant dan wajib beralasan.</p>
    <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />
    <section className="card mt-6 p-6">
      <div className="notification-filters grid max-w-xs"><FormSelect label="Status trial" htmlFor="trial-status" value={status} onChange={(event) => setStatus(event.target.value)}>
        <option value="">Semua</option><option value="RUNNING">Berjalan</option><option value="EXTENDED">Diperpanjang</option><option value="CONVERTED_EARLY">Konversi dini</option><option value="EXPIRED_CONVERTED">Berakhir → aktif</option>
      </FormSelect></div>
      {rows === null ? <LoadingState /> : rows.length === 0 ? <div className="mt-4"><EmptyState title="Tidak ada trial" /></div> : (
        <div className="mt-4 overflow-x-auto"><table className="w-full min-w-180 text-left text-sm">
          <thead><tr className="border-b border-border text-muted"><th className="py-3 pr-4">Travel</th><th className="py-3 pr-4">Status trial</th><th className="py-3 pr-4">Mulai</th><th className="py-3 pr-4">Berakhir</th><th className="py-3 text-right">Data dummy</th></tr></thead>
          <tbody>{rows.map((row) => <tr key={row.tenant_id} className="border-b border-border">
            <td className="py-3 pr-4"><Link href={`/platform/tenant/${row.tenant_id}`} className="font-medium text-primary underline">{row.display_name}</Link> <StatusBadge tone={STATE_TONE[row.tenant_state] ?? "neutral"}>{row.tenant_state}</StatusBadge></td>
            <td className="py-3 pr-4">{row.status}</td>
            <td className="py-3 pr-4">{formatDate(row.started_at)}</td>
            <td className="py-3 pr-4">{formatDate(row.ends_at)}{row.converted_at ? "" : <span className="block text-xs text-muted">{formatRemaining(row.ends_at)}</span>}</td>
            <td className="py-3 text-right">{row.dummy_used} / {row.dummy_limit}</td>
          </tr>)}</tbody>
        </table></div>
      )}
    </section>
  </div>;
}
