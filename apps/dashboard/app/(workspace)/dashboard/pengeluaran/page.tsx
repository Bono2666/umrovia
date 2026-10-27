"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Btn, EmptyState, ErrorState, FormField, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { API_BASE, apiFetch, apiUpload, problemMessage, type Departure, type Paginated, type TravelExpense } from "@/lib/api";
import { formatDate, formatIdr } from "@/lib/format";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";

const CATEGORIES = [
  ["TICKET", "Tiket pesawat"], ["HOTEL", "Hotel"], ["VISA", "Visa & dokumen"], ["TRANSPORT", "Transportasi darat"], ["CATERING", "Konsumsi"],
  ["GUIDE", "Muthawif & tour leader"], ["EQUIPMENT", "Perlengkapan jamaah"], ["MARKETING", "Pemasaran"], ["COMMISSION", "Komisi agen"], ["OFFICE", "Operasional kantor"], ["OTHER", "Lainnya"],
];
type BankAccount = {id: string; bank_name: string; account_masked: string; active: boolean};
const today = () => {const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;};
const EMPTY = {spent_on: "", category: "HOTEL", amount: "", departure: "", bank_account: "", description: "", reference: "", payee: ""};
const APPROVAL: Record<TravelExpense["approval_status"], {label: string; tone: "success" | "warning" | "danger"}> = {
  APPROVED: {label: "Disetujui", tone: "success"}, PENDING: {label: "Menunggu persetujuan", tone: "warning"}, REJECTED: {label: "Ditolak", tone: "danger"},
};

export default function ExpensesPage() {
  const {can, loading} = useWorkspacePermissions();
  const canRead = can("expenses.read");
  const canWrite = can("expenses.write");
  const canApprove = can("expenses.approve");
  const [list, setList] = useState<(Paginated<TravelExpense> & {total_idr: number; pending_count: number}) | null>(null);
  const [evidence, setEvidence] = useState<File | null>(null);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({category: "", status: "RECORDED", departure: "", approval: ""});
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
    return apiFetch<Paginated<TravelExpense> & {total_idr: number; pending_count: number}>(`/expenses?${query}`).then((result) => {
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
      reference: form.reference, departure: form.departure || null, bank_account: form.bank_account || null, payee: form.payee,
    })});
    if (!result.ok) {setBusy(false); setError(problemMessage(result.error)); return;}
    let note = "";
    if (evidence) {
      const upload = new FormData(); upload.append("file", evidence);
      const uploaded = await apiUpload<TravelExpense>(`/expenses/${result.data.id}/evidence`, upload);
      note = uploaded.ok ? " Bukti terlampir." : ` Bukti gagal diunggah: ${problemMessage(uploaded.error)}`;
    }
    setBusy(false); setEvidence(null);
    setMessage(`Pengeluaran ${formatIdr(result.data.amount_idr)} (${result.data.category_label}) tercatat${result.data.approval_status === "PENDING" ? " dan menunggu persetujuan" : ""}.${note}`);
    setForm({...EMPTY, category: form.category, bank_account: form.bank_account});
    setPage(1); void load();
  }

  async function decide(row: TravelExpense, approve: boolean) {
    let reason = "";
    if (!approve) {
      const input = window.prompt(`Tolak pengeluaran ${formatIdr(row.amount_idr)} — ${row.description}? Tulis alasan.`);
      if (input === null) return;
      reason = input.trim();
    }
    setError(null); setMessage(null);
    const result = await apiFetch<TravelExpense>(`/expenses/${row.id}/${approve ? "approve" : "reject"}`, {method: "POST", body: JSON.stringify({reason})});
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setMessage(approve ? "Pengeluaran disetujui dan masuk laporan kas." : "Pengeluaran ditolak."); void load();
  }

  async function attach(row: TravelExpense, file: File | undefined) {
    if (!file) return;
    setError(null); setMessage(null);
    const upload = new FormData(); upload.append("file", file);
    const result = await apiUpload<TravelExpense>(`/expenses/${row.id}/evidence`, upload);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setMessage("Bukti pengeluaran terlampir."); void load();
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
          {list ? <p className="text-sm text-muted">Total disetujui <span className="font-semibold text-foreground">{formatIdr(list.total_idr)}</span>{list.pending_count ? <> · <button type="button" className="text-warning underline" onClick={() => {setPage(1); setFilters({...filters, approval: "PENDING"});}}>{list.pending_count} menunggu persetujuan</button></> : null}</p> : null}
        </div>
        <div className="expense-form mt-6 grid items-end gap-x-4 gap-y-8 sm:grid-cols-2 xl:grid-cols-4">
          <FormSelect label="Kategori" htmlFor="expense-filter-category" value={filters.category} onChange={(event) => {setPage(1); setFilters({...filters, category: event.target.value});}}>
            <option value="">Semua</option>{CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </FormSelect>
          <FormSelect label="Keberangkatan" htmlFor="expense-filter-departure" value={filters.departure} onChange={(event) => {setPage(1); setFilters({...filters, departure: event.target.value});}}>
            <option value="">Semua</option>{departures.map((dep) => <option key={dep.id} value={dep.id}>{dep.code} · {dep.package_name}</option>)}
          </FormSelect>
          <FormSelect label="Status" htmlFor="expense-filter-status" value={filters.status} onChange={(event) => {setPage(1); setFilters({...filters, status: event.target.value});}}>
            <option value="RECORDED">Tercatat</option><option value="VOIDED">Dibatalkan</option><option value="">Semua</option>
          </FormSelect>
          <FormSelect label="Persetujuan" htmlFor="expense-filter-approval" value={filters.approval} onChange={(event) => {setPage(1); setFilters({...filters, approval: event.target.value});}}>
            <option value="">Semua</option><option value="PENDING">Menunggu persetujuan</option><option value="APPROVED">Disetujui</option><option value="REJECTED">Ditolak</option>
          </FormSelect>
        </div>
        {list === null ? <LoadingState /> : list.results.length === 0 ? <div className="mt-4"><EmptyState title="Belum ada pengeluaran" description="Pengeluaran yang dicatat muncul di sini dan di laporan keuangan." /></div> : <>
          <ul className="mt-4 divide-y divide-border">{list.results.map((row) => <li key={row.id} className="py-4 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2"><span className="font-medium">{row.description}</span>{row.status === "VOIDED" ? <StatusBadge tone="danger">Dibatalkan</StatusBadge> : row.approval_status !== "APPROVED" ? <StatusBadge tone={APPROVAL[row.approval_status].tone}>{APPROVAL[row.approval_status].label}</StatusBadge> : null}</p>
                <p className="mt-1 text-xs text-muted">{formatDate(row.spent_on)} · {row.category_label} · {row.bank_account?.label ?? "Tunai"}{row.departure ? ` · ${row.departure.code}` : " · Umum/kantor"}{row.reference ? ` · Ref ${row.reference}` : ""}{row.payee ? ` · ke ${row.payee}` : ""}{row.branch ? ` · ${row.branch.code}` : ""}</p>
                <p className="mt-1 text-xs text-muted">Dicatat {row.created_by_name ?? "-"}{row.approved_by_name ? ` · ${row.approval_status === "REJECTED" ? "ditolak" : "disetujui"} ${row.approved_by_name}` : ""}{row.rejection_reason ? ` (${row.rejection_reason})` : ""}
                  {row.has_evidence ? <> · <a className="text-primary underline" href={`${API_BASE}/api/v1/expenses/${row.id}/evidence`} target="_blank" rel="noreferrer">Lihat bukti</a></> : null}
                  {!row.has_evidence && canWrite && row.status === "RECORDED" ? <> · <label className="cursor-pointer text-primary underline">Lampirkan bukti<input type="file" accept="application/pdf,image/jpeg,image/png" className="sr-only" onChange={(event) => void attach(row, event.target.files?.[0])} /></label></> : null}
                </p>
                {row.void_reason ? <p className="mt-1 text-xs text-muted">Alasan batal: {row.void_reason}</p> : null}
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className={`font-semibold tabular-nums ${row.status === "VOIDED" ? "text-muted line-through" : ""}`}>{formatIdr(row.amount_idr)}</span>
                {canApprove && row.status === "RECORDED" && row.approval_status === "PENDING" ? <>
                  <Btn size="xs" onClick={() => void decide(row, true)}>Setujui</Btn>
                  <Btn size="xs" variant="link" onClick={() => void decide(row, false)}>Tolak</Btn>
                </> : null}
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
          <FormField label="Penerima dana (opsional)" htmlFor="expense-payee" maxLength={160} value={form.payee} onChange={(event) => setForm({...form, payee: event.target.value})} hint="Vendor, hotel, maskapai atau nama penerima." />
          <div className="form-group">
            <label className="text-sm" htmlFor="expense-evidence">Bukti (PDF/JPG/PNG, opsional)</label>
            <input id="expense-evidence" type="file" accept="application/pdf,image/jpeg,image/png" className="mt-1 block w-full text-sm" onChange={(event) => setEvidence(event.target.files?.[0] ?? null)} />
          </div>
          <FormField label="Referensi (opsional)" htmlFor="expense-reference" maxLength={120} value={form.reference} onChange={(event) => setForm({...form, reference: event.target.value})} hint="Nomor nota, invoice vendor atau bukti transfer." />
          <Btn type="submit" loading={busy} disabled={!form.amount || !form.description.trim()}>Simpan pengeluaran</Btn>
        </form>
      </section> : null}
    </div>
  </div>;
}
