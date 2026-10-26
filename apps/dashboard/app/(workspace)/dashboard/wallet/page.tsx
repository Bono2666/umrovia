"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Btn, BtnLink, EmptyState, ErrorState, FormField, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { API_BASE, apiFetch, problemMessage, type Paginated, type SaasCharge, type SaasWallet, type WalletLedger, type WalletTopup } from "@/lib/api";
import { formatDate, formatIdr } from "@/lib/format";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";

const LABELS: Record<string, string> = {CREATED: "Menunggu transfer", PENDING: "Menunggu verifikasi platform", PAID: "Saldo telah masuk", EXPIRED: "Kedaluwarsa", REJECTED: "Ditolak"};
const ONLINE_LABELS: Record<string, string> = {CREATED: "Menunggu pembayaran", PENDING: "Menunggu konfirmasi Midtrans", PAID: "Saldo telah masuk", EXPIRED: "Kedaluwarsa", REJECTED: "Gagal / dibatalkan"};
const topupLabel = (topup: WalletTopup) => (topup.provider === "midtrans" ? ONLINE_LABELS : LABELS)[topup.status] ?? topup.status;
const KIND: Record<string, string> = {TOPUP: "Top-up", DEBIT: "Biaya SaaS", REFUND: "Refund SaaS"};
const CHARGE: Record<string, string> = {POSTED: "Terpotong", PENDING_INSUFFICIENT_FUNDS: "Menunggu saldo", PENDING_WALLET_UNAVAILABLE: "Wallet tidak tersedia", VOID: "Dibatalkan", REFUNDED: "Direfund"};
const PARTICIPANT: Record<string, string> = {AWAITING_DP: "Menunggu DP", DP_VERIFIED_PENDING_CHARGE: "DP terverifikasi", CONFIRMED: "Terkonfirmasi", READY: "Siap", DEPARTED: "Berangkat", COMPLETED: "Selesai", CANCELED: "Batal", REVIEW_REQUIRED: "Perlu review"};
const REFUND: Record<string, string> = {REQUESTED: "Refund diajukan", APPROVED: "Refund disetujui", REJECTED: "Refund ditolak"};
const dateTime = (value: string) => new Date(value).toLocaleString("id-ID", {dateStyle:"long", timeStyle:"short"});

export default function WalletPage() {
  const {can, loading} = useWorkspacePermissions();
  const canRead = can("wallet.read");
  const [wallet, setWallet] = useState<SaasWallet | null>(null);
  const [ledger, setLedger] = useState<Paginated<WalletLedger> | null>(null);
  const [topups, setTopups] = useState<Paginated<WalletTopup> | null>(null);
  const [charges, setCharges] = useState<Paginated<SaasCharge> | null>(null);
  const [chargePage, setChargePage] = useState(1);
  const [chargeStatus, setChargeStatus] = useState("");
  const [ledgerPage, setLedgerPage] = useState(1);
  const [topupPage, setTopupPage] = useState(1);
  const [filters, setFilters] = useState({from:"", to:"", kind:""});
  const [draftFilters, setDraftFilters] = useState(filters);
  const [amount, setAmount] = useState("");
  const [selected, setSelected] = useState<WalletTopup | null>(null);
  const [reference, setReference] = useState("");
  const [evidence, setEvidence] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const attempt = useRef<{amount: number; method: string; key: string} | null>(null);
  const returned = useRef(false);
  const loadSequence = useRef(0);
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value)).toString();

  const load = useCallback(async () => {
    const sequence = ++loadSequence.current;
    return Promise.all([
      apiFetch<SaasWallet>("/wallet"),
      apiFetch<Paginated<WalletLedger>>(`/wallet/ledger?page=${ledgerPage}&${query}`),
      apiFetch<Paginated<WalletTopup>>(`/wallet/topups?page=${topupPage}`),
      apiFetch<Paginated<SaasCharge>>(`/wallet/charges?page=${chargePage}${chargeStatus ? `&status=${chargeStatus}` : ""}`),
    ]).then((results) => {
    if (sequence !== loadSequence.current) return;
    const [balance, transactions, requests, saasCharges] = results;
    if (saasCharges.ok) setCharges(saasCharges.data);
    if (balance.ok) setWallet(balance.data);
    if (transactions.ok) setLedger(transactions.data);
    if (requests.ok) {
      setTopups(requests.data);
      setSelected((previous) => previous ? requests.data.results.find((row) => row.id === previous.id) ?? previous : null);
    }
    for (const result of results) if (!result.ok) setError(problemMessage(result.error));
    });
  }, [ledgerPage, topupPage, chargePage, chargeStatus, query]);
  useEffect(() => {if (!loading && canRead) void load();}, [loading, canRead, load]);

  async function create(method: "manual" | "midtrans") {
    setBusy(true); setError(null); setMessage(null);
    const value = Number(amount);
    if (!Number.isSafeInteger(value) || value <= 0 || value > 10_000_000_000) {
      setError("Masukkan nominal integer Rp1–Rp10 miliar."); setBusy(false); return;
    }
    if (attempt.current?.amount !== value || attempt.current.method !== method) attempt.current = {amount:value, method, key:crypto.randomUUID()};
    const result = await apiFetch<WalletTopup>("/wallet/topups", {method:"POST", headers:{"Idempotency-Key":attempt.current.key}, body:JSON.stringify({amount_idr:value, method})});
    if (!result.ok) {setBusy(false); setError(problemMessage(result.error)); return;}
    attempt.current = null;
    if (method === "midtrans" && result.data.payment_url) {
      setMessage("Mengarahkan ke halaman pembayaran Midtrans…");
      window.location.assign(result.data.payment_url);
      return;
    }
    setBusy(false); setSelected(result.data); setAmount(""); setReference(""); setEvidence("");
    setMessage("Instruksi top-up dibuat. Saldo bertambah setelah dana diterima dan diverifikasi platform.");
    setTopupPage(1); void load();
  }

  const applyRefresh = useCallback((result: Awaited<ReturnType<typeof apiFetch<WalletTopup>>>) => {
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setSelected(result.data);
    setMessage(result.data.status === "PAID" ? "Pembayaran diterima. Saldo SaaS Wallet sudah bertambah."
      : result.data.status === "REJECTED" || result.data.status === "EXPIRED" ? "Pembayaran tidak berhasil. Anda dapat membuat top-up baru."
      : "Pembayaran belum dikonfirmasi Midtrans. Selesaikan pembayaran atau periksa lagi beberapa saat lagi.");
    void load();
  }, [load]);

  async function refresh(topupId: string) {
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch<WalletTopup>(`/wallet/topups/${topupId}/refresh`, {method:"POST"});
    setBusy(false);
    applyRefresh(result);
  }

  // Kembali dari halaman Midtrans (?topup=…): periksa status sekali, lalu bersihkan URL.
  useEffect(() => {
    if (loading || !canRead || returned.current) return;
    const topupId = new URLSearchParams(window.location.search).get("topup");
    if (!topupId) return;
    returned.current = true;
    window.history.replaceState(null, "", window.location.pathname);
    void apiFetch<WalletTopup>(`/wallet/topups/${topupId}/refresh`, {method:"POST"}).then(applyRefresh);
  }, [loading, canRead, applyRefresh]);

  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (!selected) return;
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch<WalletTopup>(`/wallet/topups/${selected.id}/submit`, {method:"POST", body:JSON.stringify({payment_reference:reference, evidence_ref:evidence})});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setSelected(result.data); setMessage("Bukti diajukan. Menunggu verifikasi dana oleh platform."); void load();
  }

  async function retryCharges() {
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch<{posted: number; pending: number; voided: number}>("/wallet/charges/retry", {method:"POST"});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    const {posted, pending} = result.data;
    setMessage(posted ? `${posted} biaya layanan berhasil dipotong dari saldo.${pending ? ` ${pending} masih menunggu saldo.` : ""}` : pending ? `Saldo belum cukup; ${pending} biaya layanan masih menunggu top-up.` : "Tidak ada biaya yang tertunda.");
    void load();
  }

  async function requestRefund(charge: SaasCharge) {
    const reason = window.prompt(`Alasan permintaan refund biaya SaaS ${formatIdr(charge.unit_price_idr)} untuk ${charge.pilgrim_name} (wajib, minimal 5 karakter). Saldo bertambah setelah disetujui platform:`);
    if (reason === null) return;
    if (reason.trim().length < 5) {setError("Alasan refund minimal 5 karakter."); return;}
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch(`/wallet/charges/${charge.id}/refund-request`, {method:"POST", body:JSON.stringify({reason:reason.trim()})});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setMessage("Permintaan refund diajukan untuk ditinjau platform. Saldo belum berubah."); void load();
  }

  function pick(topup: WalletTopup) {setSelected(topup); setReference(topup.payment_reference); setEvidence(topup.evidence_ref);}

  if (loading) return <LoadingState />;
  if (!canRead) return <EmptyState title="Anda tidak memiliki akses SaaS Wallet" />;

  return <div className="workspace-page">
    <div className="flex flex-wrap items-center justify-between gap-3"><RevealText as="h1" variant="title" className="text-2xl font-bold">SaaS Wallet</RevealText><Btn variant="solid" onClick={() => {setError(null); void load();}}>Perbarui</Btn></div>
    <p className="mt-1 text-sm text-muted">Saldo prabayar untuk biaya layanan Umrovia. Dana DP dan pembayaran jamaah tercatat terpisah pada Pembayaran.</p>
    {error ? <div className="mt-4"><ErrorState message={error} /></div> : null}
    {message ? <p className="mt-4 border border-success/30 bg-success/10 p-3 text-sm text-success" role="status">{message}</p> : null}
    {!wallet ? (error ? null : <div className="mt-6"><LoadingState /></div>) : <>
      {wallet.environment === "demo" ? <p className="mt-4 border border-border p-4 text-sm text-muted">Mode demo tidak memakai saldo atau transaksi wallet nyata. Top-up tersedia setelah travel beralih ke produksi.</p> : null}
      {wallet.tenant_state === "RESTRICTED" ? <p className="mt-4 border border-warning/40 bg-warning/10 p-4 text-sm text-warning" role="status">Ada {wallet.pending_charge_count} biaya layanan tertunda. DP dan layanan jamaah tetap berjalan; konfirmasi peserta baru menunggu saldo mencukupi.</p> : null}
      {wallet.status === "FROZEN" ? <p className="mt-4 text-sm text-danger" role="alert">Wallet dibekukan. Hubungi dukungan untuk peninjauan.</p> : null}
      {!wallet.balance_matches_ledger || wallet.last_reconciliation?.consistent === false ? <p className="mt-4 border border-danger/30 p-4 text-sm text-danger" role="alert">Saldo memerlukan peninjauan rekonsiliasi. Hubungi dukungan platform.</p> : null}
      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        <section className="card p-5"><p className="text-sm text-muted">Saldo tersedia</p><p className="mt-2 text-2xl font-semibold">{formatIdr(wallet.balance_idr)}</p></section>
        <section className="card p-5"><p className="text-sm text-muted">Perkiraan kapasitas saldo</p><p className="mt-2 text-2xl font-semibold">{wallet.estimated_participant_capacity} jamaah</p><p className="mt-1 text-xs text-muted">Tarif standar {formatIdr(wallet.standard_rate_idr)} per booking-jamaah</p></section>
        <section className="card p-5"><p className="text-sm text-muted">Biaya menunggu saldo</p><p className="mt-2 text-2xl font-semibold">{wallet.pending_charge_count} jamaah</p><p className="mt-1 text-xs text-muted">{wallet.pending_charge_count ? `Butuh ${formatIdr(wallet.pending_charge_idr)}. ` : ""}Pembayaran DP tetap sah dan kuitansi tetap tersedia.</p>
          {wallet.pending_charge_count && can("wallet.topup") ? <Btn className="mt-3" size="xs" variant="tint" disabled={busy || wallet.balance_idr <= 0} onClick={() => void retryCharges()}>Proses dengan saldo saat ini</Btn> : null}</section>
      </div>
      <div className="workspace-columns mt-6">
        <section className="card min-w-0 p-6"><h2 className="font-semibold">Riwayat top-up</h2>
          {topups === null ? <LoadingState /> : topups.results.length === 0 ? <div className="mt-4"><EmptyState title="Belum ada top-up" /></div> : <>
            <ul className="mt-3 divide-y divide-border">{topups.results.map((topup) => <li className="py-4 text-sm" key={topup.id}>
              <div className="flex flex-wrap items-center gap-2"><strong>{formatIdr(topup.amount_idr)}</strong><StatusBadge tone={topup.status === "PAID" ? "success" : topup.status === "REJECTED" ? "danger" : "neutral"}>{topupLabel(topup)}</StatusBadge><span className="text-xs text-muted">{topup.provider === "midtrans" ? "Midtrans" : "Transfer manual"}</span></div>
              <p className="mt-2 break-all text-xs text-muted">{topup.number}</p><p className="mt-1 text-muted">{formatDate(topup.created_at)}{topup.paid_at ? ` · saldo masuk ${formatDate(topup.paid_at)}` : ""}</p>
              <Btn className="mt-2" size="xs" variant="link" onClick={() => pick(topup)}>Lihat rincian</Btn>
            </li>)}</ul>
            <div className="mt-3 flex flex-wrap items-center gap-3 text-sm"><Btn size="xs" variant="solid" disabled={!topups.previous} onClick={() => setTopupPage((value) => value - 1)}>Sebelumnya</Btn><span>Halaman {topupPage}</span><Btn size="xs" variant="solid" disabled={!topups.next} onClick={() => setTopupPage((value) => value + 1)}>Berikutnya</Btn></div>
          </>}
        </section>
        <div className="min-w-0 space-y-6">
          {can("wallet.topup") ? <section className="card p-6"><h2 className="font-semibold">Top-up saldo SaaS</h2>
            {wallet.topup_available ? <form className="mt-5" onSubmit={(event) => {event.preventDefault(); void create(wallet.topup_methods.midtrans ? "midtrans" : "manual");}}>
              <FormField label="Nominal top-up (Rp)" htmlFor="wallet-amount" inputMode="numeric" value={amount} onChange={(event) => setAmount(event.target.value)} required hint={wallet.topup_methods.midtrans ? "Bayar online lewat Midtrans (virtual account, e-wallet, kartu); saldo masuk otomatis setelah pembayaran dikonfirmasi." : "Tidak ada minimum top-up yang ditetapkan. Saldo masuk setelah verifikasi dana oleh platform."} />
              <div className="flex flex-wrap items-center gap-2">
                {wallet.topup_methods.midtrans ? <Btn type="submit" disabled={busy || !amount}>Bayar online</Btn> : null}
                {wallet.topup_methods.manual ? <Btn type={wallet.topup_methods.midtrans ? "button" : "submit"} variant={wallet.topup_methods.midtrans ? "tint" : "solid"} disabled={busy || !amount} onClick={wallet.topup_methods.midtrans ? () => void create("manual") : undefined}>{wallet.topup_methods.midtrans ? "Transfer manual" : "Buat instruksi transfer"}</Btn> : null}
              </div>
            </form> : <p className="mt-3 text-sm text-muted">{wallet.environment === "demo" ? "Top-up nyata tidak tersedia di mode demo." : "Top-up belum tersedia. Hubungi dukungan platform."}</p>}
          </section> : null}
          {selected ? <section className="card p-6"><h2 className="font-semibold">Rincian top-up</h2><p className="mt-2 break-all text-xs text-muted">{selected.number}</p>
            <p className="mt-3 text-xl font-semibold">{formatIdr(selected.amount_idr)}</p><p className="mt-1 text-sm">{topupLabel(selected)}</p>
            {selected.provider === "midtrans" ? <div className="mt-4 space-y-2 break-all text-sm">
              <p className="text-muted">Pembayaran online Midtrans{selected.payment_type ? ` · ${selected.payment_type.replace(/_/g, " ")}` : ""}</p>
              {selected.provider_txn_id ? <p>ID transaksi Midtrans: {selected.provider_txn_id}</p> : null}
              {selected.reason ? <p className="text-danger">{selected.reason}</p> : null}
              {selected.payment_url ? <div className="flex flex-wrap gap-2 pt-1">
                <BtnLink size="xs" href={selected.payment_url}>Lanjutkan pembayaran</BtnLink>
                <Btn variant="tint" size="xs" disabled={busy} onClick={() => void refresh(selected.id)}>Periksa status</Btn>
              </div> : null}
            </div> : selected.status === "CREATED" ? <>
              <dl className="mt-4 space-y-2 text-sm"><div><dt className="text-muted">Bank penerima platform</dt><dd>{selected.instructions.bank_name}</dd></div><div><dt className="text-muted">Nama rekening</dt><dd>{selected.instructions.account_name}</dd></div><div><dt className="text-muted">Nomor rekening</dt><dd className="break-all font-semibold">{selected.instructions.account_number}</dd></div><div><dt className="text-muted">Batas transfer</dt><dd>{dateTime(selected.expires_at)}</dd></div></dl>
              {can("wallet.topup") ? <form className="mt-5" onSubmit={submit}><FormField label="Referensi transfer" htmlFor="topup-reference" maxLength={120} value={reference} onChange={(event) => setReference(event.target.value)} required /><FormField label="Lokasi bukti transfer" htmlFor="topup-evidence" maxLength={512} value={evidence} onChange={(event) => setEvidence(event.target.value)} required hint="Cantumkan referensi dokumen atau lokasi bukti untuk diperiksa petugas platform." /><Btn type="submit" disabled={busy || !reference.trim() || !evidence.trim()}>Ajukan verifikasi</Btn></form> : null}
            </> : <div className="mt-4 space-y-2 break-all text-sm"><p>Referensi: {selected.payment_reference || "—"}</p><p>Bukti: {selected.evidence_ref || "—"}</p>{selected.provider_txn_id ? <p>Referensi settlement: {selected.provider_txn_id}</p> : null}{selected.reason ? <p className="text-danger">{selected.reason}</p> : null}{selected.status === "EXPIRED" ? <p>Hubungi dukungan bila dana sudah dikirim.</p> : null}</div>}
          </section> : null}
        </div>
      </div>
      <section className="card mt-6 p-6"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-semibold">Biaya SaaS per jamaah</h2>
          <FormSelect label="Status" htmlFor="charge-status" value={chargeStatus} onChange={(event) => {setChargePage(1); setChargeStatus(event.target.value);}}><option value="">Semua</option><option value="POSTED">Terpotong</option><option value="PENDING">Menunggu saldo</option><option value="REFUNDED">Direfund</option><option value="VOID">Dibatalkan</option></FormSelect></div>
        <p className="mt-1 text-sm text-muted">Satu biaya {formatIdr(wallet.standard_rate_idr)} per booking-jamaah setelah DP terverifikasi. Pembatalan tidak mengembalikan biaya otomatis; refund diajukan untuk ditinjau platform.</p>
        {charges === null ? <LoadingState /> : charges.results.length === 0 ? <div className="mt-4"><EmptyState title="Belum ada biaya layanan" /></div> : <>
          <div className="mt-4 overflow-x-auto"><table className="w-full min-w-160 text-left text-sm"><thead><tr className="border-b border-border text-muted"><th className="py-3 pr-4">Jamaah</th><th className="py-3 pr-4">Status</th><th className="py-3 pr-4">DP terverifikasi</th><th className="py-3 text-right">Biaya</th></tr></thead><tbody>{charges.results.map((row) => <tr key={row.id} className="border-b border-border align-top">
            <td className="py-3 pr-4"><span className="font-medium">{row.pilgrim_name}</span><p className="mt-1 text-xs text-muted">{row.booking_code} · {PARTICIPANT[row.participant_status] ?? row.participant_status}</p></td>
            <td className="py-3 pr-4"><StatusBadge tone={row.status === "POSTED" ? "success" : row.status === "PENDING" ? "warning" : "neutral"}>{CHARGE[row.saas_charge_status] ?? row.saas_charge_status}</StatusBadge>
              {row.refund ? <p className="mt-1 text-xs text-muted">{REFUND[row.refund.status]}{row.refund.decision_reason ? ` · ${row.refund.decision_reason}` : ""}</p> : null}
              {row.void_reason ? <p className="mt-1 text-xs text-muted">{row.void_reason}</p> : null}
              {row.refundable && can("wallet.refund_request") ? <div className="mt-1"><Btn size="xs" variant="link" disabled={busy} onClick={() => void requestRefund(row)}>Ajukan refund</Btn></div> : null}</td>
            <td className="py-3 pr-4">{formatDate(row.eligible_at)}{row.charged_at ? <p className="mt-1 text-xs text-muted">Dipotong {formatDate(row.charged_at)}</p> : null}</td>
            <td className="py-3 text-right">{formatIdr(row.unit_price_idr)}</td></tr>)}</tbody></table></div>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-sm"><Btn size="xs" variant="solid" disabled={!charges.previous} onClick={() => setChargePage((value) => value - 1)}>Sebelumnya</Btn><span>Halaman {chargePage}</span><Btn size="xs" variant="solid" disabled={!charges.next} onClick={() => setChargePage((value) => value + 1)}>Berikutnya</Btn></div>
        </>}
      </section>
      <section className="card mt-6 p-6"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-semibold">Mutasi wallet</h2>{can("wallet.export") ? <a className="text-sm text-primary underline" href={`${API_BASE}/api/v1/wallet/ledger/export?${query}`}>Unduh CSV</a> : null}</div>
        <form className="wallet-filters mt-6 grid items-end gap-4 sm:grid-cols-4" onSubmit={(event) => {event.preventDefault(); setLedgerPage(1); setFilters(draftFilters);}}>
          <FormField label="Dari tanggal (UTC)" htmlFor="ledger-from" type="date" value={draftFilters.from} onChange={(event) => setDraftFilters({...draftFilters,from:event.target.value})} />
          <FormField label="Sampai tanggal (UTC)" htmlFor="ledger-to" type="date" value={draftFilters.to} onChange={(event) => setDraftFilters({...draftFilters,to:event.target.value})} />
          <FormSelect label="Jenis mutasi" htmlFor="ledger-kind" value={draftFilters.kind} onChange={(event) => setDraftFilters({...draftFilters,kind:event.target.value})}><option value="">Semua</option><option value="TOPUP">Top-up</option><option value="DEBIT">Biaya SaaS</option><option value="REFUND">Refund SaaS</option></FormSelect>
          <Btn type="submit">Terapkan</Btn>
        </form>
        {ledger === null ? <LoadingState /> : ledger.results.length === 0 ? <div className="mt-4"><EmptyState title="Belum ada mutasi pada periode ini" /></div> : <>
          <div className="mt-4 overflow-x-auto"><table className="w-full min-w-140 text-left text-sm"><thead><tr className="border-b border-border text-muted"><th className="py-3 pr-4">Tanggal</th><th className="py-3 pr-4">Keterangan</th><th className="py-3 pr-4 text-right">Mutasi</th><th className="py-3 text-right">Saldo setelah</th></tr></thead><tbody>{ledger.results.map((row) => <tr key={row.id} className="border-b border-border"><td className="py-3 pr-4">{formatDate(row.created_at)}</td><td className="py-3 pr-4"><span>{KIND[row.kind] ?? row.kind}</span><p className="mt-1 max-w-72 break-all text-xs text-muted">{row.reference_id}</p></td><td className={`py-3 pr-4 text-right font-medium ${row.signed_amount_idr > 0 ? "text-success" : "text-foreground"}`}>{row.signed_amount_idr > 0 ? "+" : "−"}{formatIdr(Math.abs(row.signed_amount_idr))}</td><td className="py-3 text-right">{formatIdr(row.balance_after_idr)}</td></tr>)}</tbody></table></div>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-sm"><Btn size="xs" variant="solid" disabled={!ledger.previous} onClick={() => setLedgerPage((value) => value - 1)}>Sebelumnya</Btn><span>Halaman {ledgerPage}</span><Btn size="xs" variant="solid" disabled={!ledger.next} onClick={() => setLedgerPage((value) => value + 1)}>Berikutnya</Btn></div>
        </>}
        {wallet.last_reconciliation ? <p className="mt-4 text-xs text-muted">Rekonsiliasi terakhir {formatDate(wallet.last_reconciliation.at)} · {wallet.last_reconciliation.consistent ? "Sesuai" : "Perlu ditinjau"}</p> : null}
      </section>
    </>}
  </div>;
}
