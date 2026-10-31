"use client";

import { useCallback, useEffect, useState } from "react";
import { usePlatform } from "@/components/platform/PlatformShell";
import { Btn, EmptyState, FormField, LoadingState } from "@/components/workspace/ui";
import { API_BASE, apiFetch, problemMessage } from "@/lib/api";
import { formatIdr } from "@/lib/format";
import { FloatingNotice } from "@/components/workspace/FloatingNotice";

type Topup = {tenant_id: string; tenant: string; id: string; number: string; amount_idr: number; provider: string; payment_reference: string; evidence_ref: string; evidence_file: boolean; requested_by: string; requested_at: string};
type Refund = {tenant_id: string; tenant: string; id: string; amount_idr: number; booking_code: string; reason: string; requested_by: string; requested_at: string};
const when = (value: string) => new Date(value).toLocaleString("id-ID", {dateStyle: "medium", timeStyle: "short"});

export default function PlatformBillingPage() {
  const {can} = usePlatform();
  const [queue, setQueue] = useState<{topups: Topup[]; refunds: Refund[]} | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [settle, setSettle] = useState<{id: string; amount: string; ref: string} | null>(null);
  const [decision, setDecision] = useState<{id: string; tenant_id: string; decision: "APPROVED" | "REJECTED"; reason: string} | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => apiFetch<{topups: Topup[]; refunds: Refund[]}>("/platform/billing/queue").then((r) => (r.ok ? setQueue(r.data) : setError(problemMessage(r.error)))), []);
  useEffect(() => {void load();}, [load]);

  async function call(path: string, body: object, success: string) {
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch(path, {method: "POST", headers: {"Idempotency-Key": crypto.randomUUID()}, body: JSON.stringify(body)});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setMessage(success); setSettle(null); setDecision(null); void load();
  }

  return <div>
    <h1 className="text-2xl font-bold">Billing</h1>
    <p className="mt-1 text-sm text-muted">Verifikasi top-up SaaS Wallet terhadap mutasi rekening platform dan putuskan refund biaya layanan. Petugas tidak dapat memproses permintaan miliknya sendiri.</p>
    <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />
    <FloatingNotice message={message} onDismiss={() => setMessage(null)} />
    {queue === null ? <div className="mt-6"><LoadingState /></div> : <>
      <section className="card mt-6 p-6"><h2 className="font-semibold">Top-up menunggu settlement ({queue.topups.length})</h2>
        {queue.topups.length === 0 ? <div className="mt-4"><EmptyState title="Tidak ada top-up menunggu" /></div> : <ul className="mt-3 divide-y divide-border">{queue.topups.map((t) => <li key={t.id} className="py-4 text-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0"><p className="font-medium">{t.tenant} · {formatIdr(t.amount_idr)}</p>
              <p className="mt-1 break-all text-xs text-muted">{t.number} · ref {t.payment_reference || "—"} · bukti {t.evidence_file ? <a className="text-primary underline" href={`${API_BASE}/api/v1/platform/tenants/${t.tenant_id}/wallet/topups/${t.id}/evidence`} target="_blank" rel="noreferrer">lihat berkas</a> : t.evidence_ref || "—"} · {t.requested_by} · {when(t.requested_at)}</p></div>
            {can("wallet.settle_topup") ? <Btn size="xs" onClick={() => setSettle({id: t.id, amount: String(t.amount_idr), ref: ""})}>Verifikasi dana</Btn> : null}
          </div>
          {settle?.id === t.id ? <form className="settle-form mt-6 grid items-end gap-x-4 gap-y-8 sm:grid-cols-3" onSubmit={(event) => {event.preventDefault(); void call(`/platform/tenants/${t.tenant_id}/wallet/topups/${t.id}/settle`, {amount_idr: Number(settle.amount), provider_txn_id: settle.ref}, `Top-up ${t.number} terverifikasi; saldo travel bertambah.`);}}>
            <FormField label="Nominal diterima (Rp)" htmlFor={`amount-${t.id}`} inputMode="numeric" value={settle.amount} onChange={(event) => setSettle({...settle, amount: event.target.value.replace(/\D/g, "")})} required />
            <FormField label="Referensi mutasi bank" htmlFor={`ref-${t.id}`} maxLength={160} value={settle.ref} onChange={(event) => setSettle({...settle, ref: event.target.value})} required />
            <div className="flex items-center gap-2"><Btn type="submit" loading={busy} disabled={!settle.ref.trim() || !settle.amount}>Konfirmasi</Btn><Btn variant="link" onClick={() => setSettle(null)}>Batal</Btn></div>
          </form> : null}
        </li>)}</ul>}
      </section>
      <section className="card mt-6 p-6"><h2 className="font-semibold">Refund menunggu keputusan ({queue.refunds.length})</h2>
        {queue.refunds.length === 0 ? <div className="mt-4"><EmptyState title="Tidak ada permintaan refund" /></div> : <ul className="mt-3 divide-y divide-border">{queue.refunds.map((r) => <li key={r.id} className="py-4 text-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0"><p className="font-medium">{r.tenant} · {formatIdr(r.amount_idr)} · booking {r.booking_code}</p><p className="mt-1 text-xs text-muted">{r.reason} · {r.requested_by} · {when(r.requested_at)}</p></div>
            {can("billing.approve_adjustment") ? <div className="flex gap-2"><Btn size="xs" onClick={() => setDecision({id: r.id, tenant_id: r.tenant_id, decision: "APPROVED", reason: ""})}>Setujui</Btn><Btn size="xs" variant="tint" onClick={() => setDecision({id: r.id, tenant_id: r.tenant_id, decision: "REJECTED", reason: ""})}>Tolak</Btn></div> : null}
          </div>
          {decision?.id === r.id ? <form className="settle-form mt-6 grid items-end gap-x-4 gap-y-8 sm:grid-cols-[1fr_auto]" onSubmit={(event) => {event.preventDefault(); void call(`/platform/tenants/${r.tenant_id}/wallet/refunds/${r.id}/decide`, {decision: decision.decision, reason: decision.reason}, decision.decision === "APPROVED" ? "Refund disetujui; saldo wallet travel dikreditkan." : "Refund ditolak.");}}>
            <FormField label={decision.decision === "APPROVED" ? "Alasan persetujuan" : "Alasan penolakan"} htmlFor={`decision-${r.id}`} maxLength={500} value={decision.reason} onChange={(event) => setDecision({...decision, reason: event.target.value})} required />
            <div className="flex items-center gap-2"><Btn type="submit" variant={decision.decision === "APPROVED" ? "solid" : "danger"} loading={busy} disabled={!decision.reason.trim()}>Konfirmasi</Btn><Btn variant="link" onClick={() => setDecision(null)}>Batal</Btn></div>
          </form> : null}
        </li>)}</ul>}
      </section>
    </>}
  </div>;
}
