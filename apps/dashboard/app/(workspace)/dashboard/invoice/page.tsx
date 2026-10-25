"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Btn, EmptyState, ErrorState, FormCheckbox, FormField, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { API_BASE, apiFetch, problemMessage, type Booking, type PaymentRules, type TravelInvoice } from "@/lib/api";
import { formatDate, formatIdr } from "@/lib/format";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";

const LABELS: Record<string, string> = { ISSUED: "Terbit", PARTIALLY_PAID: "Dibayar sebagian", PAID: "Lunas", VOIDED: "Dibatalkan" };

export default function InvoicePage() {
  const { can, loading } = useWorkspacePermissions();
  const [invoices, setInvoices] = useState<TravelInvoice[] | null>(null);
  const [candidates, setCandidates] = useState<Booking[]>([]);
  const [bookingId, setBookingId] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [buyerName, setBuyerName] = useState("");
  const [rules, setRules] = useState<PaymentRules>({});
  const [target, setTarget] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const canIssue = can("invoices.issue");
  const load = useCallback(() => {
    apiFetch<{results: TravelInvoice[]}>("/invoices").then((result) => {
      if (result.ok) setInvoices(result.data.results);
      else setError(problemMessage(result.error));
    });
    if (canIssue) apiFetch<{results: Booking[]}>("/invoices/candidates").then((result) => {
      if (result.ok) setCandidates(result.data.results);
    });
  }, [canIssue]);
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
    setMessage(`Invoice ${result.data.invoice_number} terbit sebesar ${formatIdr(result.data.total_idr)}.`);
    setBookingId(""); setBuyerName(""); load();
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
    <h1 className="text-2xl font-bold">Invoice</h1>
    <p className="mt-1 text-sm text-muted">Tagihan dari harga booking yang sudah tersimpan. Pembayaran terverifikasi memperbarui sisa tagihan.</p>
    {message ? <p className="mt-4 border border-success/30 bg-success/10 p-3 text-sm text-success" role="status">{message}</p> : null}
    {error ? <div className="mt-4"><ErrorState message={error} /></div> : null}
    <div className="workspace-columns mt-6">
      <section className="card p-6">
        <h2 className="font-semibold">Daftar invoice</h2>
        {invoices === null ? <LoadingState /> : invoices.length === 0 ? <div className="mt-4"><EmptyState title="Belum ada invoice" description="Reservasi booking, lalu terbitkan invoice." /></div> :
          <ul className="mt-4 divide-y divide-border">
            {invoices.map((invoice) => <li key={invoice.id} className="py-4 text-sm">
              <div className="flex flex-wrap items-center gap-2"><span className="font-semibold">{invoice.invoice_number}</span><StatusBadge tone={invoice.status === "PAID" ? "success" : invoice.status === "VOIDED" ? "danger" : "neutral"}>{LABELS[invoice.status] ?? invoice.status}</StatusBadge>{invoice.overdue ? <StatusBadge tone="danger">Lewat jatuh tempo</StatusBadge> : null}</div>
              <p className="mt-1 text-muted">{invoice.booking_code} · {invoice.buyer_name} · jatuh tempo {formatDate(invoice.due_at)}</p>
              <p className="mt-2">Total <strong>{formatIdr(invoice.total_idr)}</strong> · terbayar {formatIdr(invoice.paid_idr)}</p>
              <p className="mt-1 font-semibold">Sisa tagihan {formatIdr(invoice.balance_idr)}</p>
              <details className="mt-2"><summary className="cursor-pointer text-xs text-muted">Rincian tagihan</summary><ul className="mt-2 space-y-1">{invoice.lines.map((line) => <li key={line.participant_id} className="flex justify-between gap-3"><span>{line.description}</span><span className="shrink-0">{formatIdr(line.amount_idr)}</span></li>)}</ul></details>
              <div className="mt-3 flex flex-wrap gap-3"><a className="text-primary underline" href={`${API_BASE}/api/v1/invoices/${invoice.id}/pdf`}>Unduh invoice PDF</a>{can("payments.read") ? <Link href={`/dashboard/pembayaran?invoice=${invoice.id}`} className="text-primary underline">Lihat pembayaran</Link> : null}</div>
            </li>)}
          </ul>}
      </section>
      <div className="space-y-6">
        {canIssue ? <section className="card p-6"><h2 className="font-semibold">Terbitkan invoice</h2>
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
            <FormField label="Target minimum DP per jamaah (Rp)" htmlFor="dp-target" inputMode="numeric" value={target} onChange={(event) => setTarget(event.target.value)} hint="Kosongkan bila tidak ada target. Perubahan berlaku untuk invoice berikutnya." />
            <FormCheckbox id="payment-maker-checker" label="Verifikator harus berbeda dari pencatat pembayaran" checked={!!rules.maker_checker} onChange={(checked) => setRules((prev) => ({...prev,maker_checker:checked}))} />
            <Btn type="submit" className="mt-4" disabled={busy}>Simpan aturan</Btn>
          </form> : <p className="mt-3 text-sm">Target saat ini: {rules.dp_minimum_idr ? formatIdr(rules.dp_minimum_idr) : "Tidak ditentukan"}</p>}
        </section>
      </div>
    </div>
  </div>;
}
