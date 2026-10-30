"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Btn, EmptyState, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type Agent, type Commission, type CommissionStatus, type Paginated } from "@/lib/api";
import { formatDate, formatIdr } from "@/lib/format";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";
import { FloatingNotice, focusRecord } from "@/components/workspace/FloatingNotice";

type BankAccount = {id: string; bank_name: string; account_masked: string; active: boolean};
type Summary = {statuses: {status: CommissionStatus; label: string; count: number; total_idr: number}[]};
const TONE: Record<CommissionStatus, "neutral" | "success" | "warning" | "danger"> = {ESTIMATED: "neutral", ELIGIBLE: "warning", APPROVED: "warning", PAID: "success", REVERSED: "danger"};

/** MOD-10 §7.3: finance memeriksa komisi layak, menyetujui, lalu membayar (tercatat sebagai pengeluaran). */
export default function CommissionsPage() {
  const {can, loading} = useWorkspacePermissions();
  const canRead = can("commissions.read");
  const canApprove = can("commissions.approve");
  const canPay = can("commissions.pay");
  const [list, setList] = useState<Paginated<Commission> | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [accounts, setAccounts] = useState<BankAccount[]>([]);
  const [filters, setFilters] = useState({status: "ELIGIBLE", agent: ""});
  const [page, setPage] = useState(1);
  const [payAccount, setPayAccount] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const sequence = useRef(0);

  const load = useCallback(() => {
    const current = ++sequence.current;
    const query = new URLSearchParams(Object.entries({...filters, page: String(page)}).filter(([, value]) => value)).toString();
    void apiFetch<Summary>("/commissions/summary").then((result) => {if (result.ok) setSummary(result.data);});
    return apiFetch<Paginated<Commission>>(`/commissions?${query}`).then((result) => {
      if (current !== sequence.current) return;
      if (result.ok) setList(result.data); else setError(problemMessage(result.error));
    });
  }, [filters, page]);
  useEffect(() => {if (!loading && canRead) void load();}, [loading, canRead, load]);
  useEffect(() => {
    if (loading || !canRead) return;
    if (can("agents.read")) void apiFetch<{results: Agent[]}>("/agents?page=1&page_size=100").then((result) => {if (result.ok) setAgents(result.data.results);});
    if (canPay && can("bank_accounts.read")) void apiFetch<{results: BankAccount[]}>("/bank-accounts").then((result) => {if (result.ok) setAccounts(result.data.results.filter((a) => a.active));});
  }, [loading, canRead, canPay, can]);

  async function act(row: Commission, action: "approve" | "pay" | "reverse") {
    let body: Record<string, unknown> = {};
    if (action === "reverse") {
      const reason = window.prompt(`Batalkan komisi ${formatIdr(row.amount_idr)} untuk ${row.agent.name}?${row.status === "PAID" ? " Pengeluaran komisi juga dibatalkan (dana dikembalikan agen)." : ""} Tulis alasan.`);
      if (reason === null) return;
      if (!reason.trim()) {setError("Alasan pembatalan wajib diisi."); return;}
      body = {reason: reason.trim()};
    }
    if (action === "pay") {
      const reference = window.prompt(`Catat pembayaran komisi ${formatIdr(row.amount_idr)} ke ${row.agent.name} hari ini? Isi nomor bukti transfer (opsional).`, "");
      if (reference === null) return;
      body = {reference: reference.trim(), bank_account: payAccount || null};
    }
    setBusy(row.id); setError(null); setMessage(null);
    const result = await apiFetch<Commission>(`/commissions/${row.id}/${action}`, {method: "POST", body: JSON.stringify(body)});
    setBusy(null);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    focusRecord(row.id);
    setMessage(action === "approve" ? `Komisi ${row.booking.code} disetujui.` : action === "pay" ? `Komisi ${row.booking.code} dibayar dan tercatat di Pengeluaran.` : `Komisi ${row.booking.code} dibatalkan.`);
    void load();
  }

  if (loading) return <LoadingState />;
  if (!canRead) return <EmptyState title="Anda tidak memiliki akses komisi agen" />;

  return <div className="workspace-page">
    <RevealText as="h1" variant="title" className="text-2xl font-bold">Komisi Agen</RevealText>
    <p className="mt-1 max-w-3xl text-sm text-muted">Komisi dibuat saat booking beragen direservasi (estimasi), menjadi layak dibayar setelah syarat pembayaran kebijakan tercapai, lalu disetujui dan dibayar. Booking batal membatalkan komisi yang belum dibayar.</p>
    {summary ? <div className="mt-6 grid gap-3 sm:grid-cols-3 lg:grid-cols-5">{summary.statuses.map((row) =>
      <button key={row.status} type="button" className={`card p-4 text-left ${filters.status === row.status ? "border-primary" : ""}`} aria-pressed={filters.status === row.status} onClick={() => {setPage(1); setFilters({...filters, status: row.status});}}>
        <p className="text-xs uppercase tracking-wide text-muted">{row.label}</p>
        <p className="mt-1 text-lg font-semibold tabular-nums">{formatIdr(row.total_idr)}</p>
        <p className="text-xs text-muted">{row.count} komisi</p>
      </button>)}</div> : null}
    <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />
    <FloatingNotice message={message} onDismiss={() => setMessage(null)} />
    <section className="card mt-6 min-w-0 p-6">
      <div className="expense-form grid items-end gap-x-4 gap-y-8 sm:grid-cols-3">
        <FormSelect label="Status" htmlFor="commission-status" value={filters.status} onChange={(event) => {setPage(1); setFilters({...filters, status: event.target.value});}}>
          <option value="">Semua</option>{(summary?.statuses ?? []).map((row) => <option key={row.status} value={row.status}>{row.label}</option>)}
        </FormSelect>
        <FormSelect label="Agen" htmlFor="commission-agent" value={filters.agent} onChange={(event) => {setPage(1); setFilters({...filters, agent: event.target.value});}}>
          <option value="">Semua agen</option>{agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name} ({agent.code})</option>)}
        </FormSelect>
        {canPay ? <FormSelect label="Bayar dari" htmlFor="commission-account" value={payAccount} onChange={(event) => setPayAccount(event.target.value)}>
          <option value="">Tunai</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.bank_name} {account.account_masked}</option>)}
        </FormSelect> : null}
      </div>
      {list === null ? <LoadingState /> : list.results.length === 0 ? <div className="mt-4"><EmptyState title="Tidak ada komisi" description="Komisi muncul setelah booking beragen direservasi dan ada kebijakan komisi yang berlaku." /></div> : <>
        <ul className="mt-4 divide-y divide-border">{list.results.map((row) => <li key={row.id} data-record={row.id} className="py-4 text-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="flex flex-wrap items-center gap-2"><span className="font-medium">{row.agent.name}</span><span className="text-xs text-muted">{row.booking.code} · {row.booking.package_name} · {row.booking.departure_code}</span><StatusBadge tone={TONE[row.status]}>{row.status_label}</StatusBadge></p>
              <p className="mt-1 text-xs text-muted">{row.policy.name} · {row.pax} jamaah · basis {formatIdr(row.basis_idr)}{row.approved_by ? ` · disetujui ${row.approved_by}` : ""}{row.paid_on ? ` · dibayar ${formatDate(row.paid_on)}${row.bank_account ? ` dari ${row.bank_account}` : " (tunai)"}` : ""}{row.reference ? ` · Ref ${row.reference}` : ""}</p>
              {row.reverse_reason ? <p className="mt-1 text-xs text-muted">Alasan batal: {row.reverse_reason}</p> : null}
              {row.review_note ? <p className="mt-1 text-xs text-warning">{row.review_note}</p> : null}
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <span className={`font-semibold tabular-nums ${row.status === "REVERSED" ? "text-muted line-through" : ""}`}>{formatIdr(row.amount_idr)}</span>
              {canApprove && row.status === "ELIGIBLE" ? <Btn size="xs" loading={busy === row.id} onClick={() => void act(row, "approve")}>Setujui</Btn> : null}
              {canPay && row.status === "APPROVED" ? <Btn size="xs" loading={busy === row.id} onClick={() => void act(row, "pay")}>Bayar</Btn> : null}
              {canApprove && row.status !== "REVERSED" ? <Btn size="xs" variant="link" onClick={() => void act(row, "reverse")}>Batalkan</Btn> : null}
            </div>
          </div>
        </li>)}</ul>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm"><Btn size="xs" variant="solid" disabled={!list.previous} onClick={() => setPage((value) => value - 1)}>Sebelumnya</Btn><span>Halaman {page}</span><Btn size="xs" variant="solid" disabled={!list.next} onClick={() => setPage((value) => value + 1)}>Berikutnya</Btn></div>
      </>}
    </section>
  </div>;
}
