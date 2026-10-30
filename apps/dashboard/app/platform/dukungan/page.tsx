"use client";

import { useCallback, useEffect, useState } from "react";
import { TICKET_TONE, TicketThread } from "@/components/support/TicketThread";
import { Btn, EmptyState, ErrorState, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type Paginated, type SupportTicket } from "@/lib/api";
import { formatIdr } from "@/lib/format";
import { focusDetail } from "@/components/workspace/FloatingNotice";

const STATUSES = [["OPEN", "Terbuka"], ["IN_PROGRESS", "Diproses"], ["WAITING_TENANT", "Menunggu travel"], ["RESOLVED", "Selesai"]];

export default function PlatformSupportPage() {
  const [filter, setFilter] = useState("active");
  const [list, setList] = useState<Paginated<SupportTicket> | null>(null);
  const [ticket, setTicket] = useState<SupportTicket | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => apiFetch<Paginated<SupportTicket>>(`/platform/support/tickets?status=${filter}`).then((r) => (r.ok ? setList(r.data) : setError(problemMessage(r.error)))), [filter]);
  useEffect(() => {void load();}, [load]);

  async function open(id: string) {
    const r = await apiFetch<SupportTicket>(`/platform/support/tickets/${id}`);
    if (r.ok) {setTicket(r.data); focusDetail();} else setError(problemMessage(r.error));
  }
  async function reply(body: string, internal: boolean) {
    if (!ticket) return false;
    setBusy(true); setError(null);
    const r = await apiFetch<SupportTicket>(`/platform/support/tickets/${ticket.id}/messages`, {method: "POST", body: JSON.stringify({body, internal})});
    setBusy(false);
    if (!r.ok) {setError(problemMessage(r.error)); return false;}
    setTicket({...r.data, diagnosis: ticket.diagnosis}); void load();
    return true;
  }
  async function update(change: Record<string, string | boolean>) {
    if (!ticket) return;
    const r = await apiFetch<SupportTicket>(`/platform/support/tickets/${ticket.id}`, {method: "PATCH", body: JSON.stringify(change)});
    if (!r.ok) {setError(problemMessage(r.error)); return;}
    setTicket({...r.data, diagnosis: ticket.diagnosis}); void load();
  }

  const d = ticket?.diagnosis;
  return <div>
    <h1 className="text-2xl font-bold">Dukungan</h1>
    <p className="mt-1 text-sm text-muted">Tiket dari travel. Diagnosis hanya berisi metadata dan hitungan workspace; data jamaah tidak dapat diakses dari konsol.</p>
    {error ? <div className="mt-4"><ErrorState message={error} /></div> : null}
    <div className="workspace-columns mt-6">
      <section className="card min-w-0 p-6">
        <div className="notification-filters grid max-w-xs"><FormSelect label="Tampilkan" htmlFor="ticket-filter" value={filter} onChange={(event) => {setFilter(event.target.value); setTicket(null);}}>
          <option value="active">Belum selesai</option>{STATUSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </FormSelect></div>
        {list === null ? <LoadingState /> : list.results.length === 0 ? <div className="mt-4"><EmptyState title="Tidak ada tiket" /></div> : <ul className="mt-3 divide-y divide-border">{list.results.map((t) => <li key={t.id}>
          <button type="button" aria-current={ticket?.id === t.id} onClick={() => void open(t.id)} className={`w-full py-3 text-left text-sm ${ticket?.id === t.id ? "text-primary" : ""}`}>
            <span className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium">{t.subject}</span><StatusBadge tone={TICKET_TONE[t.status] ?? "neutral"}>{t.status_label}</StatusBadge></span>
            <span className="mt-1 block text-xs text-muted">{t.number} · {t.tenant?.display_name} · {t.category_label}{t.priority === "HIGH" ? " · prioritas tinggi" : ""} · {new Date(t.last_message_at).toLocaleString("id-ID", {dateStyle: "medium", timeStyle: "short"})}</span>
          </button>
        </li>)}</ul>}
      </section>
      <div className="min-w-0 space-y-6">
        {ticket ? <>
          <TicketThread ticket={ticket} platform busy={busy} onReply={reply} actions={<>
            <FormSelect htmlFor="ticket-status" aria-label="Status tiket" value={ticket.status} onChange={(event) => void update({status: event.target.value})}>
              {STATUSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </FormSelect>
            <Btn size="xs" variant="tint" onClick={() => void update({priority: ticket.priority === "HIGH" ? "NORMAL" : "HIGH"})}>{ticket.priority === "HIGH" ? "Prioritas normal" : "Prioritas tinggi"}</Btn>
            <Btn size="xs" variant="link" onClick={() => void update({assign_to_me: true})}>{ticket.assigned_to ? `Ditangani ${ticket.assigned_to}` : "Tangani tiket ini"}</Btn>
          </>} />
          {d ? <section className="card p-6"><h2 className="font-semibold">Diagnosis workspace</h2>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-muted">Status travel</dt><dd>{d.state_label}</dd></div>
              <div><dt className="text-muted">Lingkungan</dt><dd>{d.environments.join(", ") || "—"}</dd></div>
              <div><dt className="text-muted">Trial</dt><dd>{d.trial ? `${d.trial.status} · ${d.trial.dummy_used}/${d.trial.dummy_limit} data dummy` : "—"}</dd></div>
              <div><dt className="text-muted">Pengguna</dt><dd>{d.members}</dd></div>
              <div><dt className="text-muted">Saldo wallet</dt><dd>{d.usage ? formatIdr(d.usage.wallet_balance_idr) : "—"}</dd></div>
              <div><dt className="text-muted">Charge tertunda</dt><dd>{d.usage?.pending_charges ?? 0}</dd></div>
              <div><dt className="text-muted">Booking aktif</dt><dd>{d.usage?.active_bookings ?? 0}</dd></div>
              <div><dt className="text-muted">Jamaah aktif</dt><dd>{d.usage?.active_participants ?? 0}</dd></div>
            </dl>
          </section> : null}
        </> : <section className="card p-6 text-sm text-muted">Pilih tiket untuk membaca percakapan.</section>}
      </div>
    </div>
  </div>;
}
