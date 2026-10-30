"use client";

import { useCallback, useEffect, useState } from "react";
import { Btn, EmptyState, ErrorState, FormField, FormSelect, FormTextarea, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { TICKET_TONE, TicketThread } from "@/components/support/TicketThread";
import { apiFetch, problemMessage, type Paginated, type SupportTicket } from "@/lib/api";
import { RevealText } from "@/components/marketing/RevealText";
import { FloatingNotice, focusDetail, focusRecord } from "@/components/workspace/FloatingNotice";

const CATEGORIES = [["TECHNICAL", "Kendala teknis"], ["BILLING", "SaaS Wallet & tagihan"], ["ACCOUNT", "Akun & akses"], ["DATA", "Data & privasi"], ["OTHER", "Lainnya"]];
const EMPTY = {subject: "", category: "TECHNICAL", body: ""};

/** Bantuan (S18): tiket dukungan travel ke tim Umrovia. Tetap tersedia saat workspace ditangguhkan. */
export default function SupportPage() {
  const [list, setList] = useState<Paginated<SupportTicket> | null>(null);
  const [selected, setSelected] = useState<SupportTicket | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(() => apiFetch<Paginated<SupportTicket>>("/support/tickets").then((result) => {
    if (result.ok) setList(result.data); else setError(problemMessage(result.error));
  }), []);
  useEffect(() => {void load();}, [load]);

  async function open(id: string) {
    setCreating(false); setError(null); setMessage(null);
    const result = await apiFetch<SupportTicket>(`/support/tickets/${id}`);
    if (result.ok) {setSelected(result.data); focusDetail();} else setError(problemMessage(result.error));
  }

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch<SupportTicket>("/support/tickets", {method: "POST", body: JSON.stringify(form)});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setForm(EMPTY); setCreating(false); setSelected(result.data);
    focusRecord(result.data.id);
    setMessage(`Tiket ${result.data.number} terkirim. Tim Umrovia akan membalas di sini dan lewat email.`);
    void load();
  }

  async function reply(body: string) {
    if (!selected) return false;
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch<SupportTicket>(`/support/tickets/${selected.id}/messages`, {method: "POST", body: JSON.stringify({body})});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return false;}
    setSelected(result.data); void load();
    return true;
  }

  async function resolve() {
    if (!selected) return;
    const result = await apiFetch<SupportTicket>(`/support/tickets/${selected.id}/resolve`, {method: "POST"});
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setSelected(result.data); focusRecord(result.data.id); setMessage("Tiket ditandai selesai. Balas kapan saja untuk membukanya kembali."); void load();
  }

  return <div className="workspace-page">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <RevealText as="h1" variant="title" className="text-2xl font-bold">Bantuan</RevealText>
      <Btn onClick={() => {setCreating(true); setSelected(null); setMessage(null);}}>Buat tiket</Btn>
    </div>
    <p className="mt-1 max-w-3xl text-sm text-muted">Hubungi tim Umrovia untuk kendala akun, SaaS Wallet atau teknis. Tim dukungan hanya melihat isi tiket dan ringkasan workspace, bukan data jamaah Anda.</p>
    {error ? <div className="mt-4"><ErrorState message={error} /></div> : null}
    <FloatingNotice message={message} onDismiss={() => setMessage(null)} />
    <div className="workspace-columns mt-6">
      <section className="card min-w-0 p-6"><h2 className="font-semibold">Tiket travel</h2>
        {list === null ? <LoadingState /> : list.results.length === 0 ? <div className="mt-4"><EmptyState title="Belum ada tiket" description="Buat tiket bila Anda butuh bantuan tim Umrovia." /></div> : (
          <ul className="mt-3 divide-y divide-border">{list.results.map((ticket) => <li key={ticket.id} data-record={ticket.id}>
            <button type="button" aria-current={selected?.id === ticket.id} onClick={() => void open(ticket.id)} className={`w-full py-3 text-left text-sm ${selected?.id === ticket.id ? "text-primary" : ""}`}>
              <span className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium">{ticket.subject}</span><StatusBadge tone={TICKET_TONE[ticket.status] ?? "neutral"}>{ticket.status_label}</StatusBadge></span>
              <span className="mt-1 block text-xs text-muted">{ticket.number} · {ticket.category_label} · {ticket.opened_by} · {new Date(ticket.last_message_at).toLocaleString("id-ID", {dateStyle: "medium", timeStyle: "short"})}</span>
            </button>
          </li>)}</ul>
        )}
      </section>
      {creating ? <section className="card min-w-0 p-6"><h2 className="font-semibold">Tiket baru</h2>
        <form className="mt-5" onSubmit={create}>
          <FormField label="Judul" htmlFor="ticket-subject" maxLength={160} value={form.subject} onChange={(event) => setForm({...form, subject: event.target.value})} required />
          <FormSelect label="Kategori" htmlFor="ticket-category" value={form.category} onChange={(event) => setForm({...form, category: event.target.value})}>
            {CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </FormSelect>
          <FormTextarea label="Ceritakan kendalanya" htmlFor="ticket-body" rows={6} maxLength={5000} value={form.body} onChange={(event) => setForm({...form, body: event.target.value})} required
            hint="Sertakan langkah yang dilakukan dan kode booking/invoice bila relevan. Jangan cantumkan NIK, nomor paspor, password atau kode OTP." />
          <div className="flex flex-wrap gap-2">
            <Btn type="submit" loading={busy} disabled={form.subject.trim().length < 5 || form.body.trim().length < 5}>Kirim tiket</Btn>
            <Btn variant="link" onClick={() => setCreating(false)}>Batal</Btn>
          </div>
        </form>
      </section> : selected ? (
        <TicketThread ticket={selected} busy={busy} onReply={(body) => reply(body)}
          actions={selected.status !== "RESOLVED" ? <Btn size="xs" variant="tint" onClick={() => void resolve()}>Tandai selesai</Btn> : null} />
      ) : <section className="card min-w-0 p-6 text-sm text-muted">Pilih tiket untuk melihat percakapan, atau buat tiket baru.</section>}
    </div>
  </div>;
}
