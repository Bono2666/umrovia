"use client";

import { useCallback, useEffect, useState } from "react";
import { Btn, EmptyState, FormCheckbox, FormField, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type BankAccount } from "@/lib/api";
import { formatDate, formatIdr } from "@/lib/format";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { FloatingNotice } from "@/components/workspace/FloatingNotice";

type BookRow = {key: string; account: string; opening_idr: number; inflow_idr: number; reversal_idr: number; expense_idr: number; transfer_in_idr: number; transfer_out_idr: number; closing_idr: number; opening_as_of: string | null};
type Book = {from: string; to: string; rows: BookRow[]; totals: Omit<BookRow, "key" | "account" | "opening_as_of">; rules: {maker_checker: boolean}};
type Opening = {id: string; account: string; as_of: string; amount_idr: number; reason: string; status: string; status_label: string; created_by: string | null; decided_by: string | null; decision_note: string};
type Transfer = {id: string; transferred_on: string; from_account: string; to_account: string; amount_idr: number; description: string; reference: string; status: string; void_reason: string; created_by: string | null};

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const digits = (value: string) => Number(value.replace(/[^\d-]/g, "")) || 0;

/** MOD-11: buku kas per rekening, saldo awal berotorisasi, transfer antarrekening, maker-checker kas. */
export function CashPanel({accounts}: {accounts: BankAccount[]}) {
  const {can} = useWorkspacePermissions();
  const canWrite = can("bank_accounts.write");
  const canApprove = can("bank_accounts.approve");
  const [tab, setTab] = useState<"book" | "opening" | "transfers">("book");
  const [range, setRange] = useState(() => {const now = new Date(); return {from: iso(new Date(now.getFullYear(), now.getMonth(), 1)), to: iso(now)};});
  const [book, setBook] = useState<Book | null>(null);
  const [openings, setOpenings] = useState<Opening[] | null>(null);
  const [transfers, setTransfers] = useState<Transfer[] | null>(null);
  const [openingForm, setOpeningForm] = useState({bank_account: "", as_of: iso(new Date()), amount: "", reason: ""});
  const [transferForm, setTransferForm] = useState({from_account: "", to_account: "", transferred_on: iso(new Date()), amount: "", description: "", reference: ""});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const active = accounts.filter((a) => a.active);

  const load = useCallback(() => {
    void apiFetch<Book>(`/cash/book?from=${range.from}&to=${range.to}`).then((r) => {if (r.ok) setBook(r.data); else setError(problemMessage(r.error));});
    void apiFetch<{results: Opening[]}>("/cash/opening-balances").then((r) => {if (r.ok) setOpenings(r.data.results);});
    void apiFetch<{results: Transfer[]}>("/cash/transfers").then((r) => {if (r.ok) setTransfers(r.data.results);});
  }, [range]);
  useEffect(() => {load();}, [load]);

  async function call<T>(path: string, body: unknown, success: (data: T) => string) {
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch<T>(path, {method: path === "/cash/settings" ? "PATCH" : "POST", body: JSON.stringify(body)});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return false;}
    setMessage(success(result.data)); load(); return true;
  }

  const accountOptions = <>{<option value="">Tunai</option>}{active.map((a) => <option key={a.id} value={a.id}>{a.bank_name} {a.account_masked}</option>)}</>;
  const money = (v: number) => <span className="tabular-nums">{formatIdr(v)}</span>;

  return <section className="card mt-6 min-w-0 p-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="font-semibold">Buku kas & bank</h2>
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Bagian kas">
        {([["book", "Saldo per rekening"], ["opening", "Saldo awal"], ["transfers", "Transfer antarrekening"]] as const).map(([key, label]) =>
          <Btn key={key} size="xs" role="tab" aria-selected={tab === key} variant={tab === key ? "solid" : "tint"} onClick={() => setTab(key)}>{label}</Btn>)}
      </div>
    </div>
    <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />
    <FloatingNotice message={message} onDismiss={() => setMessage(null)} />

    {tab === "book" ? <>
      <div className="expense-form mt-6 grid items-end gap-x-4 gap-y-8 sm:grid-cols-3">
        <FormField label="Dari" htmlFor="cash-from" type="date" value={range.from} max={range.to} onChange={(e) => e.target.value && setRange({...range, from: e.target.value})} />
        <FormField label="Sampai" htmlFor="cash-to" type="date" value={range.to} min={range.from} onChange={(e) => e.target.value && setRange({...range, to: e.target.value})} />
        {book ? <FormCheckbox id="cash-maker-checker" label="Maker-checker kas: pengeluaran & koreksi saldo awal disetujui staf lain" checked={book.rules.maker_checker} disabled={!canApprove || busy}
          onChange={(checked) => void call<{maker_checker: boolean}>("/cash/settings", {maker_checker: checked}, (d) => d.maker_checker ? "Maker-checker kas aktif: pengeluaran baru menunggu persetujuan." : "Maker-checker kas dimatikan.")} /> : null}
      </div>
      {book === null ? <LoadingState /> : book.rows.length === 0 ? <div className="mt-4"><EmptyState title="Belum ada mutasi" description="Isi saldo awal rekening, lalu pembayaran, pengeluaran dan transfer akan membentuk saldo." /></div> :
        <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[720px] text-sm">
          <thead><tr className="text-left text-xs text-muted">{["Rekening", "Saldo awal", "Masuk", "Reversal", "Pengeluaran", "Transfer masuk", "Transfer keluar", "Saldo akhir"].map((h, i) => <th key={h} className={`py-2 font-medium ${i ? "text-right" : ""}`}>{h}</th>)}</tr></thead>
          <tbody>{book.rows.map((row) => <tr key={row.key} className="border-t border-border">
            <td className="py-2">{row.account}{row.opening_as_of ? <span className="block text-xs text-muted">saldo awal per {formatDate(row.opening_as_of)}</span> : null}</td>
            {[row.opening_idr, row.inflow_idr, row.reversal_idr, row.expense_idr, row.transfer_in_idr, row.transfer_out_idr].map((v, i) => <td key={i} className="py-2 text-right">{money(v)}</td>)}
            <td className="py-2 text-right font-semibold">{money(row.closing_idr)}</td>
          </tr>)}</tbody>
          <tfoot><tr className="border-t-2 border-border font-semibold"><td className="py-2">Total</td>
            {[book.totals.opening_idr, book.totals.inflow_idr, book.totals.reversal_idr, book.totals.expense_idr, book.totals.transfer_in_idr, book.totals.transfer_out_idr, book.totals.closing_idr].map((v, i) => <td key={i} className="py-2 text-right">{money(v)}</td>)}</tr></tfoot>
        </table></div>}
      <p className="mt-3 text-xs text-muted">Dihitung dari saldo awal, pembayaran terverifikasi, pengeluaran disetujui dan transfer yang dicatat di Umrovia — bukan mutasi rekening bank. Transfer tidak mengubah total kas travel.</p>
    </> : null}

    {tab === "opening" ? <div className="workspace-columns mt-5">
      <div className="min-w-0">
        {openings === null ? <LoadingState /> : openings.length === 0 ? <EmptyState title="Belum ada saldo awal" description="Saldo awal pertama per rekening langsung berlaku; koreksi berikutnya perlu persetujuan." /> :
          <ul className="divide-y divide-border">{openings.map((row) => <li key={row.id} data-record={row.id} className="py-3 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2"><span className="font-medium">{row.account}</span><StatusBadge tone={row.status === "APPROVED" ? "success" : row.status === "PENDING" ? "warning" : "neutral"}>{row.status_label}</StatusBadge></p>
                <p className="mt-1 text-xs text-muted">Per {formatDate(row.as_of)} · {row.created_by ?? "-"}{row.reason ? ` · ${row.reason}` : ""}{row.decided_by ? ` · diputuskan ${row.decided_by}` : ""}{row.decision_note ? ` (${row.decision_note})` : ""}</p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className="font-semibold">{money(row.amount_idr)}</span>
                {canApprove && row.status === "PENDING" ? <>
                  <Btn size="xs" disabled={busy} onClick={() => void call<Opening>(`/cash/opening-balances/${row.id}/approve`, {}, () => `Koreksi saldo awal ${row.account} disetujui.`)}>Setujui</Btn>
                  <Btn size="xs" variant="link" onClick={() => {const note = window.prompt("Alasan menolak koreksi saldo awal:"); if (note) void call<Opening>(`/cash/opening-balances/${row.id}/reject`, {note}, () => "Koreksi ditolak.");}}>Tolak</Btn>
                </> : null}
              </div>
            </div>
          </li>)}</ul>}
      </div>
      {canWrite ? <form className="min-w-0" onSubmit={(e) => {e.preventDefault(); void call<Opening>("/cash/opening-balances", {bank_account: openingForm.bank_account || null, as_of: openingForm.as_of, amount_idr: digits(openingForm.amount), reason: openingForm.reason}, (d) => d.status === "APPROVED" ? `Saldo awal ${d.account} berlaku per ${formatDate(d.as_of)}.` : `Koreksi saldo awal ${d.account} menunggu persetujuan.`).then((ok) => ok && setOpeningForm({...openingForm, amount: "", reason: ""}));}}>
        <h3 className="font-semibold">Isi / koreksi saldo awal</h3>
        <FormSelect label="Rekening" htmlFor="opening-account" value={openingForm.bank_account} onChange={(e) => setOpeningForm({...openingForm, bank_account: e.target.value})}>{accountOptions}</FormSelect>
        <FormField label="Berlaku per tanggal" htmlFor="opening-date" type="date" max={iso(new Date())} value={openingForm.as_of} onChange={(e) => setOpeningForm({...openingForm, as_of: e.target.value})} required hint="Transaksi sebelum tanggal ini dianggap sudah tercakup saldo awal." />
        <FormField label="Saldo (Rp)" htmlFor="opening-amount" inputMode="numeric" thousands="signed" value={openingForm.amount} onChange={(e) => setOpeningForm({...openingForm, amount: e.target.value})} required hint="Boleh negatif untuk cerukan." />
        <FormField label="Alasan (wajib untuk koreksi)" htmlFor="opening-reason" maxLength={240} value={openingForm.reason} onChange={(e) => setOpeningForm({...openingForm, reason: e.target.value})} />
        <Btn type="submit" loading={busy} disabled={!openingForm.amount}>Simpan saldo awal</Btn>
      </form> : null}
    </div> : null}

    {tab === "transfers" ? <div className="workspace-columns mt-5">
      <div className="min-w-0">
        {transfers === null ? <LoadingState /> : transfers.length === 0 ? <EmptyState title="Belum ada transfer" description="Catat setoran tunai ke bank atau pemindahan dana antarrekening." /> :
          <ul className="divide-y divide-border">{transfers.map((row) => <li key={row.id} data-record={row.id} className="py-3 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2"><span className="font-medium">{row.from_account} → {row.to_account}</span>{row.status === "VOIDED" ? <StatusBadge tone="danger">Dibatalkan</StatusBadge> : null}</p>
                <p className="mt-1 text-xs text-muted">{formatDate(row.transferred_on)}{row.description ? ` · ${row.description}` : ""}{row.reference ? ` · Ref ${row.reference}` : ""}{row.void_reason ? ` · batal: ${row.void_reason}` : ""}</p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className={`font-semibold ${row.status === "VOIDED" ? "text-muted line-through" : ""}`}>{money(row.amount_idr)}</span>
                {canWrite && row.status !== "VOIDED" ? <Btn size="xs" variant="link" onClick={() => {const reason = window.prompt("Alasan membatalkan transfer (min. 5 karakter):"); if (reason) void call<Transfer>(`/cash/transfers/${row.id}/void`, {reason}, () => "Transfer dibatalkan.");}}>Batalkan</Btn> : null}
              </div>
            </div>
          </li>)}</ul>}
      </div>
      {canWrite ? <form className="min-w-0" onSubmit={(e) => {e.preventDefault(); void call<Transfer>("/cash/transfers", {from_account: transferForm.from_account || null, to_account: transferForm.to_account || null, transferred_on: transferForm.transferred_on, amount_idr: digits(transferForm.amount), description: transferForm.description, reference: transferForm.reference}, (d) => `Transfer ${formatIdr(d.amount_idr)} ${d.from_account} → ${d.to_account} tercatat.`).then((ok) => ok && setTransferForm({...transferForm, amount: "", description: "", reference: ""}));}}>
        <h3 className="font-semibold">Catat transfer</h3>
        <FormSelect label="Dari" htmlFor="transfer-from" value={transferForm.from_account} onChange={(e) => setTransferForm({...transferForm, from_account: e.target.value})}>{accountOptions}</FormSelect>
        <FormSelect label="Ke" htmlFor="transfer-to" value={transferForm.to_account} onChange={(e) => setTransferForm({...transferForm, to_account: e.target.value})}>{accountOptions}</FormSelect>
        <FormField label="Tanggal" htmlFor="transfer-date" type="date" max={iso(new Date())} value={transferForm.transferred_on} onChange={(e) => setTransferForm({...transferForm, transferred_on: e.target.value})} required />
        <FormField label="Nominal (Rp)" htmlFor="transfer-amount" inputMode="numeric" thousands value={transferForm.amount} onChange={(e) => setTransferForm({...transferForm, amount: e.target.value})} required />
        <FormField label="Keterangan" htmlFor="transfer-description" maxLength={240} value={transferForm.description} onChange={(e) => setTransferForm({...transferForm, description: e.target.value})} />
        <FormField label="Referensi" htmlFor="transfer-reference" maxLength={120} value={transferForm.reference} onChange={(e) => setTransferForm({...transferForm, reference: e.target.value})} />
        <Btn type="submit" loading={busy} disabled={!transferForm.amount || transferForm.from_account === transferForm.to_account}>Simpan transfer</Btn>
      </form> : null}
    </div> : null}
  </section>;
}
