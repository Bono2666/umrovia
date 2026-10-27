"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Btn, EmptyState, ErrorState, FormField, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type Departure, type Paginated, type TravelExpense } from "@/lib/api";
import { formatDate, formatIdr } from "@/lib/format";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";

const CATEGORIES = [
  ["TICKET", "Tiket pesawat"], ["HOTEL", "Hotel"], ["VISA", "Visa & dokumen"], ["TRANSPORT", "Transportasi darat"], ["CATERING", "Konsumsi"],
  ["GUIDE", "Muthawif & tour leader"], ["EQUIPMENT", "Perlengkapan jamaah"], ["MARKETING", "Pemasaran"], ["OFFICE", "Operasional kantor"], ["OTHER", "Lainnya"],
];
type BankAccount = {id: string; bank_name: string; account_masked: string; active: boolean};
const today = () => {const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;};
const EMPTY = {spent_on: "", category: "HOTEL", amount: "", departure: "", bank_account: "", description: "", reference: ""};

export default function ExpensesPage() {
  const {can, loading} = useWorkspacePermissions();
  const canRead = can("expenses.read");
  const canWrite = can("expenses.write");
  const [list, setList] = useState<(Paginated<TravelExpense> & {total_idr: number}) | null>(null);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({category: "", status: "RECORDED", departure: ""});
  const [departures, setDepartures] = useState<Departure[]>([]);
  const [accounts, setAccounts] = useState<BankAccount[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const sequence = useRef(0);

  const load = useCallback(() => {
    const current = ++sequence.current;
    const query = new URLSearchParams(Object.entries({...filters, page: String(page)}).filter(([, value]) => value)).toString();
    return apiFetch<Paginated<TravelExpense> & {total_idr: number}>(`/expenses?${query}`).then((result) => {
      if (current !== sequence.current) return;
      if (result.ok) setList(result.data); else setError(problemMessage(result.error));
    });
  }, [filters, page]);
  useEffect(() => {if (!loading && canRead) void load();}, [loading, canRead, load]);
  useEffect(() => {
    if (loading || !canRead) return;
    void apiFetch<{results: Departure[]}>("/departures").then((result) => {if (result.ok) setDepartures(result.data.results);});
    if (can("bank_accounts.read")) void apiFetch<{results: BankAccount[]}>("/bank-accounts").then((result) => {if (result.ok) setAccounts(result.data.results.filter((a) => a.active));});
  }, [loading, canRead, can]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true); setError(null); setMessage(null);
    const amount = Number(form.amount.replace(/\D/g, ""));
    const result = await apiFetch<TravelExpense>("/expenses", {method: "POST", body: JSON.stringify({
      spent_on: form.spent_on || today(), category: form.category, amount_idr: amount, description: form.description,
      reference: form.reference, departure: form.departure || null, bank_account: form.bank_account || null,
    })});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setMessage(`Pengeluaran ${formatIdr(result.data.amount_idr)} (${result.data.category_label}) tercatat.`);
    setForm({...EMPTY, category: form.category, bank_account: form.bank_account});
    setPage(1); void load();
  }

  async function voidExpense(row: TravelExpense) {
    const reason = window.prompt(`Batalkan pengeluaran ${formatIdr(row.amount_idr)} — ${row.description}? Tulis alasan (minimal 5 karakter). Catatan tetap tersimpan sebagai riwayat.`);
    if (reason === null) return;
    if (reason.trim().length < 5) {setError("Alasan pembatalan minimal 5 karakter."); return;}
    setError(null); setMessage(null);
    const result = await apiFetch<TravelExpense>(`/expenses/${row.id}/void`, {method: "POST", body: JSON.stringify({reason: reason.trim()})});
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setMessage("Pengeluaran dibatalkan. Catat ulang bila nominal atau datanya perlu dikoreksi."); void load();
  }

  if (loading) return <LoadingState />;
  if (!canRead) return <EmptyState title="Anda tidak memiliki akses pengeluaran" />;

  return <div className="workspace-page">
    <RevealText as="h1" variant="title" className="text-2xl font-bold">Pengeluaran</RevealText>
    <p className="mt-1 max-w-3xl text-sm text-muted">Catat biaya perjalanan dan operasional travel agar laporan kas/bank dan margin estimasi per keberangkatan lengkap. Pengeluaran tidak diedit; batalkan lalu catat ulang bila perlu koreksi.</p>
    {error ? <div className="mt-4"><ErrorState message={error} /></div> : null}
    {message ? <p className="mt-4 border border-success/30 bg-success/10 p-3 text-sm text-success" role="status">{message}</p> : null}
    <div className="workspace-columns mt-6">
      <section className="card min-w-0 p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="font-semibold">Daftar pengeluaran</h2>
          {list ? <p className="text-sm text-muted">Total tercatat <span className="font-semibold text-foreground">{formatIdr(list.total_idr)}</span></p> : null}
        </div>
        <div className="expense-form mt-6 grid items-end gap-x-4 gap-y-8 sm:grid-cols-3">
          <FormSelect label="Kategori" htmlFor="expense-filter-category" value={filters.category} onChange={(event) => {setPage(1); setFilters({...filters, category: event.target.value});}}>
            <option value="">Semua</option>{CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </FormSelect>
          <FormSelect label="Keberangkatan" htmlFor="expense-filter-departure" value={filters.departure} onChange={(event) => {setPage(1); setFilters({...filters, departure: event.target.value});}}>
            <option value="">Semua</option>{departures.map((dep) => <option key={dep.id} value={dep.id}>{dep.code} · {dep.package_name}</option>)}
          </FormSelect>
          <FormSelect label="Status" htmlFor="expense-filter-status" value={filters.status} onChange={(event) => {setPage(1); setFilters({...filters, status: event.target.value});}}>
            <option value="RECORDED">Tercatat</option><option value="VOIDED">Dibatalkan</option><option value="">Semua</option>
          </FormSelect>
        </div>
        {list === null ? <LoadingState /> : list.results.length === 0 ? <div className="mt-4"><EmptyState title="Belum ada pengeluaran" description="Pengeluaran yang dicatat muncul di sini dan di laporan keuangan." /></div> : <>
          <ul className="mt-4 divide-y divide-border">{list.results.map((row) => <li key={row.id} className="py-4 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2"><span className="font-medium">{row.description}</span>{row.status === "VOIDED" ? <StatusBadge tone="danger">Dibatalkan</StatusBadge> : null}</p>
                <p className="mt-1 text-xs text-muted">{formatDate(row.spent_on)} · {row.category_label} · {row.bank_account?.label ?? "Tunai"}{row.departure ? ` · ${row.departure.code}` : " · Umum/kantor"}{row.reference ? ` · Ref ${row.reference}` : ""}</p>
                {row.void_reason ? <p className="mt-1 text-xs text-muted">Alasan batal: {row.void_reason}</p> : null}
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className={`font-semibold tabular-nums ${row.status === "VOIDED" ? "text-muted line-through" : ""}`}>{formatIdr(row.amount_idr)}</span>
                {canWrite && row.status === "RECORDED" ? <Btn size="xs" variant="link" onClick={() => void voidExpense(row)}>Batalkan</Btn> : null}
              </div>
            </div>
          </li>)}</ul>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-sm"><Btn size="xs" variant="solid" disabled={!list.previous} onClick={() => setPage((value) => value - 1)}>Sebelumnya</Btn><span>Halaman {page}</span><Btn size="xs" variant="solid" disabled={!list.next} onClick={() => setPage((value) => value + 1)}>Berikutnya</Btn></div>
        </>}
      </section>
      {canWrite ? <section className="card min-w-0 p-6"><h2 className="font-semibold">Catat pengeluaran</h2>
        <form className="mt-5" onSubmit={submit}>
          <FormField label="Tanggal" htmlFor="expense-date" type="date" max={today()} value={form.spent_on || today()} onChange={(event) => setForm({...form, spent_on: event.target.value})} required />
          <FormSelect label="Kategori" htmlFor="expense-category" value={form.category} onChange={(event) => setForm({...form, category: event.target.value})}>
            {CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </FormSelect>
          <FormField label="Nominal (Rp)" htmlFor="expense-amount" inputMode="numeric" value={form.amount} onChange={(event) => setForm({...form, amount: event.target.value})} required
            hint={Number(form.amount.replace(/\D/g, "")) > 0 ? formatIdr(Number(form.amount.replace(/\D/g, ""))) : "Tanpa titik atau koma"} />
          <FormField label="Keterangan" htmlFor="expense-description" maxLength={240} value={form.description} onChange={(event) => setForm({...form, description: event.target.value})} required />
          <FormSelect label="Keberangkatan" htmlFor="expense-departure" value={form.departure} onChange={(event) => setForm({...form, departure: event.target.value})}>
            <option value="">Umum / kantor (tanpa keberangkatan)</option>
            {departures.map((dep) => <option key={dep.id} value={dep.id}>{dep.code} · {dep.package_name}</option>)}
          </FormSelect>
          <FormSelect label="Dibayar dari" htmlFor="expense-account" value={form.bank_account} onChange={(event) => setForm({...form, bank_account: event.target.value})}>
            <option value="">Tunai</option>
            {accounts.map((account) => <option key={account.id} value={account.id}>{account.bank_name} {account.account_masked}</option>)}
          </FormSelect>
          <FormField label="Referensi (opsional)" htmlFor="expense-reference" maxLength={120} value={form.reference} onChange={(event) => setForm({...form, reference: event.target.value})} hint="Nomor nota, invoice vendor atau bukti transfer." />
          <Btn type="submit" loading={busy} disabled={!form.amount || !form.description.trim()}>Simpan pengeluaran</Btn>
        </form>
      </section> : null}
    </div>
  </div>;
}
