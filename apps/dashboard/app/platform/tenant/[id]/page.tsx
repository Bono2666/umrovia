"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { usePlatform } from "@/components/platform/PlatformShell";
import { STATE_TONE } from "@/components/platform/tone";
import { Btn, ErrorState, FormField, FormTextarea, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type PlatformTenantDetail } from "@/lib/api";
import { formatDate, formatIdr } from "@/lib/format";
import { FloatingNotice } from "@/components/workspace/FloatingNotice";

type Pending = {kind: "suspend" | "reactivate" | "termination" | "extend" | "approve" | "reject"; requestId?: string} | null;
const ACTION_TEXT: Record<string, {title: string; hint: string; button: string; danger?: boolean}> = {
  suspend: {title: "Tangguhkan travel", hint: "Dashboard dan portal jamaah travel ditutup seketika; data tidak berubah. Owner tetap bisa membuka tiket Bantuan.", button: "Tangguhkan", danger: true},
  reactivate: {title: "Aktifkan kembali", hint: "Status sebelum penangguhan dipulihkan.", button: "Aktifkan kembali"},
  termination: {title: "Ajukan pengakhiran", hint: "Memerlukan persetujuan admin platform lain. Data tidak dihapus; retensi mengikuti kebijakan.", button: "Ajukan pengakhiran", danger: true},
  extend: {title: "Perpanjang trial", hint: "1–30 hari per pengajuan, dicatat beserta alasannya.", button: "Perpanjang"},
  approve: {title: "Setujui pengakhiran", hint: "Travel berstatus Diakhiri dan tidak dapat diaktifkan kembali dari konsol.", button: "Setujui pengakhiran", danger: true},
  reject: {title: "Tolak pengakhiran", hint: "Travel tetap ditangguhkan; dapat diaktifkan kembali.", button: "Tolak pengajuan"},
};
const when = (value: string) => new Date(value).toLocaleString("id-ID", {dateStyle: "medium", timeStyle: "short"});

export default function PlatformTenantDetailPage() {
  const {id} = useParams<{id: string}>();
  const {can} = usePlatform();
  const [tenant, setTenant] = useState<PlatformTenantDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending>(null);
  const [reason, setReason] = useState("");
  const [days, setDays] = useState("7");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => apiFetch<PlatformTenantDetail>(`/platform/tenants/${id}`).then((r) => (r.ok ? setTenant(r.data) : setError(problemMessage(r.error)))), [id]);
  useEffect(() => {void load();}, [load]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!pending || !tenant) return;
    setBusy(true); setError(null); setMessage(null);
    const path = pending.kind === "extend" ? `/platform/trials/${tenant.id}/extend`
      : pending.kind === "approve" || pending.kind === "reject" ? `/platform/tenants/${tenant.id}/termination/${pending.requestId}/decide`
      : `/platform/tenants/${tenant.id}/${pending.kind}`;
    const body = pending.kind === "extend" ? {reason, days: Number(days)} : pending.kind === "approve" || pending.kind === "reject" ? {reason, decision: pending.kind} : {reason};
    const result = await apiFetch(path, {method: "POST", body: JSON.stringify(body)});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setMessage(`${ACTION_TEXT[pending.kind].title}: berhasil dan tercatat di audit.`);
    setPending(null); setReason(""); void load();
  }

  if (error && !tenant) return <ErrorState message={error} />;
  if (!tenant) return <LoadingState />;
  const manage = can("platform.tenant_manage");
  const open = tenant.lifecycle_requests.find((r) => r.status === "PENDING");
  const trialRunning = tenant.trial && !tenant.trial.converted_at;

  return <div>
    <Link href="/platform/tenant" className="text-sm text-primary underline">← Semua tenant</Link>
    <div className="mt-3 flex flex-wrap items-center gap-3"><h1 className="text-2xl font-bold">{tenant.display_name}</h1><StatusBadge tone={STATE_TONE[tenant.state] ?? "neutral"}>{tenant.state_label}</StatusBadge></div>
    <p className="mt-1 text-sm text-muted">{tenant.legal_name} · {tenant.slug} · dibuat {formatDate(tenant.created_at)} · lingkungan {tenant.environments.join(", ") || "—"}</p>
    {tenant.suspended_at ? <p className="mt-3 border border-danger/30 bg-danger/10 p-3 text-sm text-danger">Ditangguhkan {when(tenant.suspended_at)} — {tenant.suspension_reason}</p> : null}
    <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />
    <FloatingNotice message={message} onDismiss={() => setMessage(null)} />

    <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {[["Saldo wallet", tenant.usage ? formatIdr(tenant.usage.wallet_balance_idr) : "—"], ["Charge tertunda", `${tenant.usage?.pending_charges ?? 0} · ${formatIdr(tenant.usage?.pending_charge_idr ?? 0)}`],
        ["Booking / jamaah aktif", `${tenant.usage?.active_bookings ?? 0} / ${tenant.usage?.active_participants ?? 0}`], ["Tiket dukungan aktif", String(tenant.open_tickets)]].map(([label, value]) => (
        <section key={label} className="card p-5"><p className="text-sm text-muted">{label}</p><p className="mt-2 text-xl font-semibold">{value}</p></section>
      ))}
    </div>

    <div className="workspace-columns mt-6">
      <div className="min-w-0 space-y-6">
        <section className="card p-6"><h2 className="font-semibold">Trial</h2>
          {tenant.trial ? <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
            <div><dt className="text-muted">Status</dt><dd>{tenant.trial.status}</dd></div>
            <div><dt className="text-muted">Berakhir</dt><dd>{formatDate(tenant.trial.ends_at)}</dd></div>
            <div><dt className="text-muted">Data dummy</dt><dd>{tenant.trial.dummy_used} / {tenant.trial.dummy_limit}</dd></div>
            <div><dt className="text-muted">Dikonversi</dt><dd>{tenant.trial.converted_at ? formatDate(tenant.trial.converted_at) : "Belum"}</dd></div>
          </dl> : <p className="mt-2 text-sm text-muted">Tidak ada trial.</p>}
        </section>
        <section className="card p-6"><h2 className="font-semibold">Pengguna travel</h2>
          <ul className="mt-3 divide-y divide-border text-sm">{tenant.members_detail.map((m) => <li key={m.email + m.joined_at} className="flex flex-wrap justify-between gap-2 py-2"><span>{m.email}</span><span className="text-muted">{m.role ?? "—"} · {m.status}</span></li>)}</ul>
          <p className="mt-3 text-xs text-muted">Email tersamar. Konsol tidak memberi akses ke data operasional travel.</p>
        </section>
        <section className="card p-6"><h2 className="font-semibold">Riwayat tindakan platform</h2>
          {tenant.history.length === 0 ? <p className="mt-2 text-sm text-muted">Belum ada.</p> : <ol className="mt-3 space-y-2 text-sm">{tenant.history.map((h) => <li key={h.id}>
            <span className="font-medium">{h.action.replace("platform.", "")}</span> <span className="text-xs text-muted">· {h.actor} · {when(h.occurred_at)}</span>
            {h.changes.reason ? <p className="text-xs text-muted">{String(h.changes.reason)}</p> : null}
          </li>)}</ol>}
        </section>
      </div>
      <div className="min-w-0 space-y-6">
        {manage ? <section className="card p-6"><h2 className="font-semibold">Tindakan</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {["TRIAL", "ACTIVE", "RESTRICTED"].includes(tenant.state) ? <Btn variant="danger" size="xs" onClick={() => setPending({kind: "suspend"})}>Tangguhkan</Btn> : null}
            {tenant.state === "SUSPENDED" && !open ? <Btn size="xs" onClick={() => setPending({kind: "reactivate"})}>Aktifkan kembali</Btn> : null}
            {tenant.state === "SUSPENDED" && !open ? <Btn variant="tint" size="xs" onClick={() => setPending({kind: "termination"})}>Ajukan pengakhiran</Btn> : null}
            {trialRunning ? <Btn variant="tint" size="xs" onClick={() => setPending({kind: "extend"})}>Perpanjang trial</Btn> : null}
          </div>
          {open ? <div className="mt-4 border border-warning/40 bg-warning/10 p-4 text-sm">
            <p className="font-semibold">Pengajuan pengakhiran menunggu persetujuan</p>
            <p className="mt-1 text-muted">Oleh {open.requested_by} · {when(open.requested_at)} — {open.reason}</p>
            <p className="mt-2 text-xs text-muted">Keputusan harus diambil admin platform selain pengaju.</p>
            <div className="mt-3 flex flex-wrap gap-2"><Btn variant="danger" size="xs" onClick={() => setPending({kind: "approve", requestId: open.id})}>Setujui</Btn><Btn variant="tint" size="xs" onClick={() => setPending({kind: "reject", requestId: open.id})}>Tolak</Btn></div>
          </div> : null}
          {pending ? <form className="mt-5 border-t border-border pt-5" onSubmit={submit}>
            <p className="font-semibold">{ACTION_TEXT[pending.kind].title}</p>
            <p className="mt-1 text-sm text-muted">{ACTION_TEXT[pending.kind].hint}</p>
            <div className="mt-4">
              {pending.kind === "extend" ? <FormField label="Jumlah hari (1–30)" htmlFor="extend-days" inputMode="numeric" thousands value={days} onChange={(event) => setDays(event.target.value.replace(/\D/g, ""))} required /> : null}
              <FormTextarea label="Alasan (dicatat di audit)" htmlFor="action-reason" rows={3} maxLength={240} value={reason} onChange={(event) => setReason(event.target.value)} required hint="Minimal 10 karakter." />
            </div>
            <div className="flex flex-wrap gap-2">
              <Btn type="submit" variant={ACTION_TEXT[pending.kind].danger ? "danger" : "solid"} loading={busy} disabled={reason.trim().length < 10}>{ACTION_TEXT[pending.kind].button}</Btn>
              <Btn variant="link" onClick={() => {setPending(null); setReason("");}}>Batal</Btn>
            </div>
          </form> : null}
        </section> : null}
        {tenant.lifecycle_requests.length ? <section className="card p-6"><h2 className="font-semibold">Pengajuan lifecycle</h2>
          <ul className="mt-3 space-y-3 text-sm">{tenant.lifecycle_requests.map((r) => <li key={r.id} className="border-b border-border pb-3">
            <p><StatusBadge tone={r.status === "APPROVED" ? "danger" : r.status === "PENDING" ? "warning" : "neutral"}>{r.status}</StatusBadge> <span className="ml-1">{r.kind}</span></p>
            <p className="mt-1 text-xs text-muted">Diajukan {r.requested_by} · {when(r.requested_at)}{r.decided_by ? ` · diputuskan ${r.decided_by}` : ""}</p>
          </li>)}</ul>
        </section> : null}
      </div>
    </div>
  </div>;
}
