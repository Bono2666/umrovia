"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Btn, EmptyState, FormCheckbox, FormField, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { API_BASE, apiFetch, problemMessage, type Booking, type Paginated, type PaymentRules, type TravelInvoice } from "@/lib/api";
import { formatDate, formatIdr } from "@/lib/format";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";
import { FloatingNotice, focusRecord } from "@/components/workspace/FloatingNotice";

type LineEdit = {discount: string; extra: string; note: string};
const rupiah = (value: string) => Number(value.replace(/\D/g, "")) || 0;

const LABELS: Record<string, string> = { ISSUED: "Terbit", PARTIALLY_PAID: "Dibayar sebagian", PAID: "Lunas", VOIDED: "Dibatalkan" };

export default function InvoicePage() {
  const { can, loading } = useWorkspacePermissions();
  const [invoices, setInvoices] = useState<TravelInvoice[] | null>(null);
  const [page, setPage] = useState(1);
  const [pageInfo, setPageInfo] = useState<{count: number; next: string | null; previous: string | null}>({count: 0, next: null, previous: null});
  const [candidates, setCandidates] = useState<Booking[]>([]);
  const [bookingId, setBookingId] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [buyerName, setBuyerName] = useState("");
  const [rules, setRules] = useState<PaymentRules>({});
  const [target, setTarget] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [revising, setRevising] = useState<TravelInvoice | null>(null);
  const [revision, setRevision] = useState<{reason: string; buyer: string; due: string; lines: Record<string, LineEdit>}>({reason: "", buyer: "", due: "", lines: {}});
  const canIssue = can("invoices.issue");
  const canDiscount = can("bookings.discount");
  const load = useCallback(() => {
    apiFetch<Paginated<TravelInvoice>>(`/invoices?page=${page}`).then((result) => {  // paginasi server (S19)
      if (result.ok) {setInvoices(result.data.results); setPageInfo({count: result.data.count, next: result.data.next, previous: result.data.previous});}
      else setError(problemMessage(result.error));
    });
    if (canIssue) apiFetch<{results: Booking[]}>("/invoices/candidates").then((result) => {
      if (result.ok) setCandidates(result.data.results);
    });
  }, [canIssue, page]);
  useEffect(() => { if (!loading) load(); }, [loading, load]);
  useEffect(() => {
    apiFetch<PaymentRules>("/payments/settings").then((result) => {
      if (result.ok) { setRules(result.data); setTarget(result.data.dp_minimum_idr ? String(result.data.dp_minimum_idr) : ""); }
    });
  }, []);

  async function issue(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch<TravelInvoice>(`/bookings/${bookingId}/issue-invoice`, {method:"POST", body: JSON.stringify({...(dueAt ? {due_at: dueAt} : {}), ...(buyerName.trim() ? {buyer_name: buyerName.trim()} : {})})});
    setBusy(false);
    if (!result.ok) { setError(problemMessage(result.error)); return; }
    focusRecord(result.data.id);
    setMessage(`Invoice ${result.data.invoice_number} terbit sebesar ${formatIdr(result.data.total_idr)}.`);
    setBookingId(""); setBuyerName(""); load();
  }

  async function openRevision(invoice: TravelInvoice) {
    setError(null); setMessage(null);
    const result = await apiFetch<TravelInvoice>(`/invoices/${invoice.id}`);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setRevising(result.data);
    setRevision({reason: "", buyer: result.data.buyer_name, due: result.data.due_at, lines: Object.fromEntries(result.data.lines.map((line) => [line.participant_id, {
      discount: line.discount_idr ? String(line.discount_idr) : "", extra: line.extra_idr ? String(line.extra_idr) : "", note: "",
    }]))});
  }

  async function revise(event: React.FormEvent) {
    event.preventDefault();
    if (!revising) return;
    setBusy(true); setError(null); setMessage(null);
    const changedLines = revising.lines.filter((line) => {
      const edit = revision.lines[line.participant_id];
      return edit && (rupiah(edit.discount) !== (line.discount_idr ?? 0) || rupiah(edit.extra) !== (line.extra_idr ?? 0) || edit.note.trim());
    });
    const body = {
      reason: revision.reason.trim(),
      ...(revision.buyer.trim() !== revising.buyer_name ? {buyer_name: revision.buyer.trim()} : {}),
      ...(revision.due && revision.due !== revising.due_at ? {due_at: revision.due} : {}),
      ...(changedLines.length ? {adjustments: changedLines.map((line) => {
        const edit = revision.lines[line.participant_id];
        return {participant_id: line.participant_id, discount_idr: rupiah(edit.discount), extra_idr: rupiah(edit.extra), note: edit.note.trim()};
      })} : {}),
    };
    const result = await apiFetch<TravelInvoice>(`/invoices/${revising.id}/revise`, {method: "POST", body: JSON.stringify(body)});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    focusRecord(result.data.id);
    setMessage(`Invoice ${result.data.invoice_number} direvisi ke versi ${result.data.version}: total ${formatIdr(result.data.total_idr)}. Versi lama tetap tersimpan.`);
    setRevising(null); load();
  }

  async function saveRules(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch<PaymentRules>("/payments/settings", {method:"PATCH", body:JSON.stringify({dp_policy:"any_positive",dp_minimum_idr:target === "" ? 0 : Number(target),maker_checker:!!rules.maker_checker})});
    setBusy(false);
    if (!result.ok) { setError(problemMessage(result.error)); return; }
    setRules(result.data); setMessage("Aturan pembayaran tersimpan.");
  }

  if (loading) return <LoadingState />;
  if (!can("invoices.read")) return <EmptyState title="Anda tidak memiliki akses invoice" />;

  return <div className="workspace-page">
    <RevealText as="h1" variant="title" className="text-2xl font-bold">Invoice</RevealText>
    <p className="mt-1 text-sm text-muted">Tagihan dari harga booking yang sudah tersimpan. Pembayaran terverifikasi memperbarui sisa tagihan.</p>
    <FloatingNotice message={message} onDismiss={() => setMessage(null)} />
    <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />
    <div className="workspace-columns mt-6">
      <section className="card p-6">
        <h2 className="font-semibold">Daftar invoice</h2>
        {invoices === null ? <LoadingState /> : invoices.length === 0 ? <div className="mt-4"><EmptyState title="Belum ada invoice" description="Invoice terbit otomatis saat booking direservasi." /></div> :
          <ul className="mt-4 divide-y divide-border">
            {invoices.map((invoice) => <li key={invoice.id} data-record={invoice.id} className="py-4 text-sm">
              <div className="flex flex-wrap items-center gap-2"><span className="font-semibold">{invoice.invoice_number}</span>{invoice.version > 1 ? <StatusBadge tone="warning">Revisi {invoice.version}</StatusBadge> : null}<StatusBadge tone={invoice.status === "PAID" ? "success" : invoice.status === "VOIDED" ? "danger" : "neutral"}>{LABELS[invoice.status] ?? invoice.status}</StatusBadge>{invoice.overdue ? <StatusBadge tone="danger">Lewat jatuh tempo</StatusBadge> : null}</div>
              <p className="mt-1 text-muted">{invoice.booking_code} · {invoice.buyer_name} · jatuh tempo {formatDate(invoice.due_at)}</p>
              <p className="mt-2">Total <strong>{formatIdr(invoice.total_idr)}</strong> · terbayar {formatIdr(invoice.paid_idr)}</p>
              {invoice.discount_idr || invoice.extra_idr ? <p className="mt-1 text-xs text-muted">Harga paket {formatIdr(invoice.gross_idr)}{invoice.discount_idr ? ` · diskon ${formatIdr(invoice.discount_idr)}` : ""}{invoice.extra_idr ? ` · tambahan ${formatIdr(invoice.extra_idr)}` : ""}</p> : null}
              <p className="mt-1 font-semibold">Sisa tagihan {formatIdr(invoice.balance_idr)}</p>
              <details className="mt-2"><summary className="cursor-pointer text-xs text-muted">Rincian tagihan</summary><ul className="mt-2 space-y-1">{invoice.lines.map((line) => <li key={line.participant_id} className="flex justify-between gap-3"><span>{line.description}</span><span className="shrink-0">{formatIdr(line.amount_idr)}</span></li>)}</ul></details>
              <div className="mt-3 flex flex-wrap gap-3"><a className="text-primary underline" href={`${API_BASE}/api/v1/invoices/${invoice.id}/pdf`}>Unduh invoice PDF</a>{can("payments.read") ? <Link href={`/dashboard/pembayaran?invoice=${invoice.id}`} className="text-primary underline">Lihat pembayaran</Link> : null}
                {canIssue && (invoice.status === "ISSUED" || (invoice.status === "PAID" && invoice.total_idr === 0)) && invoice.paid_idr === 0 ? <button type="button" className="text-primary underline" onClick={() => void openRevision(invoice)}>Revisi</button> : null}</div>
            </li>)}
          </ul>}
        {pageInfo.previous || pageInfo.next ? <div className="mt-4 flex flex-wrap items-center gap-3 text-sm"><Btn size="xs" variant="solid" disabled={!pageInfo.previous} onClick={() => setPage((value) => value - 1)}>Sebelumnya</Btn><span>Halaman {page} · {pageInfo.count} invoice</span><Btn size="xs" variant="solid" disabled={!pageInfo.next} onClick={() => setPage((value) => value + 1)}>Berikutnya</Btn></div> : null}
      </section>
      <div className="space-y-6">
        {revising ? <section className="card p-6" id="invoice-revision"><h2 className="font-semibold">Revisi {revising.invoice_number}</h2>
          <p className="mt-2 text-sm text-muted">Revisi hanya untuk invoice yang belum memiliki pembayaran tercatat. Nomor invoice tetap; versi {revising.version} diarsipkan beserta PDF-nya.</p>
          {revising.revisions?.length ? <ul className="mt-3 space-y-1 text-xs text-muted">{revising.revisions.map((row) => <li key={row.version}>
            Versi {row.version} · {formatIdr(row.total_idr)} · {formatDate(row.revised_at)} · {row.reason}{row.revised_by ? ` — ${row.revised_by}` : ""} · <a className="text-primary underline" href={`${API_BASE}/api/v1/invoices/${revising.id}/revisions/${row.version}/pdf`}>PDF</a>
          </li>)}</ul> : null}
          {revising.revisable === false ? <p className="mt-4 text-sm text-danger">Invoice ini sudah memiliki pembayaran tercatat. Tolak atau reversal pembayaran terlebih dahulu.</p> : <form className="mt-6" onSubmit={revise}>
            <FormField label="Nama pelanggan" htmlFor="revise-buyer" maxLength={160} value={revision.buyer} onChange={(event) => setRevision({...revision, buyer: event.target.value})} />
            <FormField label="Jatuh tempo" htmlFor="revise-due" type="date" value={revision.due} onChange={(event) => setRevision({...revision, due: event.target.value})} />
            {revising.lines.map((line) => {
              const edit = revision.lines[line.participant_id] ?? {discount: "", extra: "", note: ""};
              const update = (patch: Partial<LineEdit>) => setRevision({...revision, lines: {...revision.lines, [line.participant_id]: {...edit, ...patch}}});
              return <div key={line.participant_id} className="border-t border-border/60 pt-4">
                <p className="text-sm font-medium">{line.pilgrim_name} <span className="text-xs text-muted">· harga paket {formatIdr(line.gross_idr ?? line.amount_idr)}</span></p>
                {canDiscount ? <FormField label="Diskon (Rp)" htmlFor={`revise-discount-${line.participant_id}`} inputMode="numeric" thousands value={edit.discount} onChange={(event) => update({discount: event.target.value})} /> : null}
                <FormField label="Biaya tambahan (Rp)" htmlFor={`revise-extra-${line.participant_id}`} inputMode="numeric" thousands value={edit.extra} onChange={(event) => update({extra: event.target.value})} />
                <FormField label="Alasan penyesuaian" htmlFor={`revise-note-${line.participant_id}`} maxLength={200} value={edit.note} onChange={(event) => update({note: event.target.value})} hint="Wajib bila ada diskon atau biaya tambahan." />
              </div>;
            })}
            <FormField label="Alasan revisi" htmlFor="revise-reason" maxLength={500} value={revision.reason} onChange={(event) => setRevision({...revision, reason: event.target.value})} required hint="Tercatat di audit dan tercetak di invoice revisi." />
            <div className="flex flex-wrap gap-2">
              <Btn type="submit" disabled={busy || !revision.reason.trim()}>{busy ? "Memproses…" : "Terbitkan revisi"}</Btn>
              <Btn type="button" variant="tint" onClick={() => setRevising(null)}>Batal</Btn>
            </div>
          </form>}
        </section> : null}
        {canIssue ? <section className="card p-6"><h2 className="font-semibold">Terbitkan invoice</h2>
          <p className="mt-2 text-sm text-muted">Invoice terbit otomatis saat kursi booking direservasi. Gunakan formulir ini hanya bila penerbitan otomatis gagal (mis. konfigurasi pajak) atau untuk booking lama.</p>
          <form onSubmit={issue} className="mt-6">
            <FormSelect label="Booking yang sudah direservasi" htmlFor="invoice-booking" value={bookingId} onChange={(event) => setBookingId(event.target.value)} required>
              <option value="">— pilih booking —</option>{candidates.map((booking) => <option key={booking.id} value={booking.id}>{booking.code} · {booking.participant_count} peserta · {formatIdr(booking.total_amount)}</option>)}
            </FormSelect>
            <FormField label="Jatuh tempo" htmlFor="invoice-due" type="date" hint="Opsional; mengikuti konfigurasi invoice travel, atau tujuh hari bila belum diatur." value={dueAt} onChange={(event) => setDueAt(event.target.value)} />
            <FormField label="Nama pelanggan / penanggung jawab" htmlFor="invoice-buyer" maxLength={160} value={buyerName} onChange={(event) => setBuyerName(event.target.value)} hint="Opsional; bila kosong, memakai nama jamaah pertama pada booking." />
            <Btn type="submit" disabled={busy || !bookingId}>{busy ? "Memproses…" : "Terbitkan invoice"}</Btn>
          </form>
        </section> : null}
        <section className="card p-6"><h2 className="font-semibold">Aturan DP travel</h2>
          <p className="mt-2 text-sm text-muted">Setiap alokasi pembayaran terverifikasi di atas Rp0 memenuhi syarat DP. Target minimum bersifat opsional; pembayaran di bawah target tetap dapat dicatat dan diverifikasi.</p>
          {can("tenant.settings.write") ? <form className="mt-6" onSubmit={saveRules}>
            <FormField label="Target minimum DP per jamaah (Rp)" htmlFor="dp-target" inputMode="numeric" thousands value={target} onChange={(event) => setTarget(event.target.value)} hint="Kosongkan bila tidak ada target. Perubahan berlaku untuk invoice berikutnya." />
            <FormCheckbox id="payment-maker-checker" label="Verifikator harus berbeda dari pencatat pembayaran" checked={!!rules.maker_checker} onChange={(checked) => setRules((prev) => ({...prev,maker_checker:checked}))} />
            <Btn type="submit" className="mt-4" disabled={busy}>Simpan aturan</Btn>
          </form> : <p className="mt-3 text-sm">Target saat ini: {rules.dp_minimum_idr ? formatIdr(rules.dp_minimum_idr) : "Tidak ditentukan"}</p>}
        </section>
      </div>
    </div>
  </div>;
}
