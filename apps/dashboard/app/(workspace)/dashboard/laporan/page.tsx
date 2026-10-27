"use client";

import { useEffect, useRef, useState } from "react";
import { Btn, EmptyState, ErrorState, FormField, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, downloadFromApi, problemMessage, type Agent, type Departure, type Report, type ReportColumn, type ReportSection, type TravelPackage } from "@/lib/api";
import { formatIdr } from "@/lib/format";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";

type Kind = Report["report"];
const TABS: {kind: Kind; label: string; grant: string; hint: string}[] = [
  {kind: "operational", label: "Operasional", grant: "reports.read", hint: "Okupansi, booking, DP, dokumen dan kesiapan per keberangkatan."},
  {kind: "finance", label: "Keuangan", grant: "reports.finance", hint: "Invoice, penerimaan, piutang, kas/bank, pengeluaran dan margin estimasi milik travel."},
  {kind: "sales", label: "Booking & Penjualan", grant: "reports.read", hint: "Booking per tanggal pemesanan dengan gross, diskon dan net per paket dan agen."},
  {kind: "payments", label: "Pembayaran", grant: "reports.finance", hint: "Penerimaan terverifikasi per rekening dan per petugas verifikasi."},
  {kind: "commissions", label: "Komisi Agen", grant: "commissions.read", hint: "Komisi estimasi, earned, disetujui dan dibayar per agen."},
  {kind: "saas", label: "SaaS Wallet", grant: "wallet.read", hint: "Saldo prabayar dan biaya layanan Umrovia — terpisah dari kas travel."},
];
const STATUS = [["", "Semua"], ["DRAFT", "Draft"], ["OPEN", "Pendaftaran dibuka"], ["READY", "Siap berangkat"], ["DEPARTED", "Sudah berangkat"], ["COMPLETED", "Selesai"], ["CANCELED", "Dibatalkan"]];

const iso = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
function presetRange(preset: string): {from: string; to: string} {
  const today = new Date();
  const y = today.getFullYear(), m = today.getMonth();
  switch (preset) {
    case "upcoming": return {from: iso(today), to: iso(new Date(y + 1, m, today.getDate()))};
    case "last_month": return {from: iso(new Date(y, m - 1, 1)), to: iso(new Date(y, m, 0))};
    case "90d": return {from: iso(new Date(y, m, today.getDate() - 89)), to: iso(today)};
    case "year": return {from: iso(new Date(y, 0, 1)), to: iso(today)};
    default: return {from: iso(new Date(y, m, 1)), to: iso(today)};
  }
}
const PRESETS = [["month", "Bulan ini"], ["last_month", "Bulan lalu"], ["90d", "90 hari terakhir"], ["year", "Tahun ini"], ["upcoming", "12 bulan ke depan"], ["custom", "Pilih tanggal"]];

function formatCell(value: string | number | null | undefined, type: ReportColumn["type"]): string {
  if (value === null || value === undefined || value === "") return "—";
  if (type === "money") return formatIdr(Number(value));
  if (type === "int") return Number(value).toLocaleString("id-ID");
  if (type === "percent") return `${Number(value).toLocaleString("id-ID", {maximumFractionDigits: 1})}%`;
  if (type === "date") return new Date(`${value}T00:00:00`).toLocaleDateString("id-ID", {day: "numeric", month: "short", year: "numeric"});
  return String(value);
}
const numeric = (type: ReportColumn["type"]) => type === "money" || type === "int" || type === "percent";

export default function ReportsPage() {
  const {can, loading} = useWorkspacePermissions();
  const tabs = TABS.filter((tab) => can(tab.grant));
  const [kind, setKind] = useState<Kind | null>(null);
  const active = kind && tabs.some((tab) => tab.kind === kind) ? kind : tabs[0]?.kind ?? null;
  const [preset, setPreset] = useState("upcoming");
  const [range, setRange] = useState(() => presetRange("upcoming"));
  const [filters, setFilters] = useState({package: "", departure: "", status: "", agent: "", account: "", branch: ""});
  const [branches, setBranches] = useState<{id: string; code: string; name: string}[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [accounts, setAccounts] = useState<{id: string; bank_name: string; account_masked: string}[]>([]);
  const [packages, setPackages] = useState<TravelPackage[]>([]);
  const [departures, setDepartures] = useState<Departure[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sequence = useRef(0);

  const [reloads, setReloads] = useState(0);
  const params = new URLSearchParams({from: range.from, to: range.to});
  const allowed: Record<string, Kind[]> = {status: ["operational"], agent: ["sales", "commissions"], account: ["payments"], branch: ["finance", "sales", "payments", "commissions"]};
  if (active !== "saas") for (const [key, value] of Object.entries(filters)) if (value && (!allowed[key] || (active && allowed[key].includes(active)))) params.set(key, value);
  const query = params.toString();

  useEffect(() => {
    if (!active) return;
    const current = ++sequence.current;
    void apiFetch<Report>(`/reports/${active}?${query}`).then((result) => {
      if (current !== sequence.current) return;
      if (result.ok) {setReport(result.data); setError(null);} else {setReport(null); setError(problemMessage(result.error));}
    });
  }, [active, query, reloads]);
  useEffect(() => {
    void apiFetch<{results: TravelPackage[]}>("/packages").then((result) => {if (result.ok) setPackages(result.data.results);});
    void apiFetch<{results: Departure[]}>("/departures").then((result) => {if (result.ok) setDepartures(result.data.results);});
  }, []);
  const canAgents = can("agents.read");
  const canAccounts = can("bank_accounts.read");
  const canBranches = can("branches.read");
  useEffect(() => {
    if (canBranches) void apiFetch<{results: {id: string; code: string; name: string}[]}>("/branches").then((result) => {if (result.ok) setBranches(result.data.results);});
  }, [canBranches]);
  useEffect(() => {
    if (canAgents) void apiFetch<{results: Agent[]}>("/agents?page=1&page_size=100").then((result) => {if (result.ok) setAgents(result.data.results);});
    if (canAccounts) void apiFetch<{results: {id: string; bank_name: string; account_masked: string}[]}>("/bank-accounts").then((result) => {if (result.ok) setAccounts(result.data.results);});
  }, [canAgents, canAccounts]);

  function choose(next: Kind) {
    setKind(next); setReport(null);
    const nextPreset = next === "operational" ? "upcoming" : "month";
    setPreset(nextPreset); setRange(presetRange(nextPreset));
  }

  if (loading) return <LoadingState />;
  if (!tabs.length || !active) return <EmptyState title="Anda tidak memiliki akses laporan" />;
  const tab = TABS.find((item) => item.kind === active)!;
  const shownDepartures = filters.package ? departures.filter((dep) => dep.package_id === filters.package) : departures;

  return <div className="workspace-page">
    <RevealText as="h1" variant="title" className="text-2xl font-bold">Laporan</RevealText>
    <p className="mt-1 max-w-3xl text-sm text-muted">Dihitung langsung dari transaksi saat dibuka, lengkap dengan cek rekonsiliasi. Unduh sebagai PDF untuk dicetak, atau Excel/CSV untuk diolah.</p>
    <div className="mt-5 flex flex-wrap gap-2" role="tablist" aria-label="Jenis laporan">
      {tabs.map((item) => <Btn key={item.kind} role="tab" aria-selected={item.kind === active} variant={item.kind === active ? "solid" : "tint"} onClick={() => choose(item.kind)}>{item.label}</Btn>)}
    </div>
    <p className="mt-3 text-sm text-muted">{tab.hint}</p>

    <section className="card mt-5 p-6">
      <div className={`report-filters grid items-end gap-x-4 gap-y-8 md:grid-cols-3 ${active === "finance" ? "xl:grid-cols-5" : active === "saas" ? "xl:grid-cols-3" : "xl:grid-cols-6"}`}>
        <FormSelect label="Periode" htmlFor="report-preset" value={preset} onChange={(event) => {setPreset(event.target.value); if (event.target.value !== "custom") setRange(presetRange(event.target.value));}}>
          {PRESETS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </FormSelect>
        <FormField label="Dari" htmlFor="report-from" type="date" value={range.from} max={range.to} onChange={(event) => {if (event.target.value) {setPreset("custom"); setRange({...range, from: event.target.value});}}} />
        <FormField label="Sampai" htmlFor="report-to" type="date" value={range.to} min={range.from} onChange={(event) => {if (event.target.value) {setPreset("custom"); setRange({...range, to: event.target.value});}}} />
        {active !== "saas" ? <>
          <FormSelect label="Paket" htmlFor="report-package" value={filters.package} onChange={(event) => setFilters({...filters, package: event.target.value, departure: ""})}>
            <option value="">Semua paket</option>
            {packages.map((pkg) => <option key={pkg.id} value={pkg.id}>{pkg.name}</option>)}
          </FormSelect>
          <FormSelect label="Keberangkatan" htmlFor="report-departure" value={filters.departure} onChange={(event) => setFilters({...filters, departure: event.target.value})}>
            <option value="">Semua keberangkatan</option>
            {shownDepartures.map((dep) => <option key={dep.id} value={dep.id}>{dep.code} · {dep.package_name}</option>)}
          </FormSelect>
        </> : null}
        {active === "operational" ? <FormSelect label="Status keberangkatan" htmlFor="report-status" value={filters.status} onChange={(event) => setFilters({...filters, status: event.target.value})}>
          {STATUS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </FormSelect> : null}
        {(active === "sales" || active === "commissions") && canAgents ? <FormSelect label="Agen" htmlFor="report-agent" value={filters.agent} onChange={(event) => setFilters({...filters, agent: event.target.value})}>
          <option value="">Semua agen</option>
          {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
        </FormSelect> : null}
        {branches.length > 0 && active !== "operational" && active !== "saas" ? <FormSelect label="Cabang" htmlFor="report-branch" value={filters.branch} onChange={(event) => setFilters({...filters, branch: event.target.value})}>
          <option value="">Semua cabang</option>
          {branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.code} · {branch.name}</option>)}
        </FormSelect> : null}
        {active === "payments" ? <FormSelect label="Rekening" htmlFor="report-account" value={filters.account} onChange={(event) => setFilters({...filters, account: event.target.value})}>
          <option value="">Semua rekening</option><option value="CASH">Tunai</option>
          {accounts.map((account) => <option key={account.id} value={account.id}>{account.bank_name} {account.account_masked}</option>)}
        </FormSelect> : null}
      </div>
      {active === "operational" ? <p className="mt-4 text-xs text-muted">Periode menyaring keberangkatan berdasarkan tanggal berangkat.</p>
        : active === "finance" ? <p className="mt-4 text-xs text-muted">Pembayaran diakui saat diverifikasi; piutang dihitung per saat laporan dibuka.</p>
        : active === "sales" ? <p className="mt-4 text-xs text-muted">Periode menyaring booking berdasarkan tanggal booking dibuat.</p>
        : active === "payments" ? <p className="mt-4 text-xs text-muted">Periode menyaring pembayaran berdasarkan tanggal verifikasi.</p> : null}
    </section>

    {error ? <div className="mt-4"><ErrorState message={error} onRetry={() => setReloads((value) => value + 1)} /></div> : null}
    {!report ? (error ? null : <div className="mt-6"><LoadingState /></div>) : <ReportBody report={report} query={query} />}
  </div>;
}

function ReportBody({report, query}: {report: Report; query: string}) {
  const asOf = new Date(report.as_of).toLocaleString("id-ID", {dateStyle: "long", timeStyle: "short"});
  const allOk = report.checks.every((check) => check.ok);
  return <>
    <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-muted">Per {asOf}{report.environment === "demo" ? " · data demo" : ""}</p>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted">Unduh</span>
        {(["pdf", "xlsx", "csv"] as const).map((file) => <Btn key={file} size="xs" variant="solid" onClick={() => downloadFromApi(`/api/v1/reports/${report.report}?${query}&file=${file}`)}>{file === "xlsx" ? "Excel" : file.toUpperCase()}</Btn>)}
      </div>
    </div>
    {report.note ? <p className="mt-3 border border-border p-3 text-sm text-muted">{report.note}</p> : null}
    {report.kpis.length ? <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
      {report.kpis.map((kpi) => <section key={kpi.key} className="card p-5">
        <p className="text-sm text-muted">{kpi.label}</p>
        <p className="mt-2 text-2xl font-semibold">{formatCell(kpi.value, kpi.type)}</p>
        {kpi.hint ? <p className="mt-1 text-xs text-muted">{kpi.hint}</p> : null}
      </section>)}
    </div> : null}
    {report.checks.length ? <section className="card mt-6 p-6" aria-label="Rekonsiliasi">
      <div className="flex flex-wrap items-center gap-2"><h2 className="font-semibold">Rekonsiliasi</h2>
        <StatusBadge tone={allOk ? "success" : "danger"}>{allOk ? "Semua sesuai" : "Ada selisih"}</StatusBadge></div>
      <ul className="mt-3 space-y-2 text-sm">{report.checks.map((check) => <li key={check.label} className="flex flex-wrap items-baseline gap-2">
        <span className={check.ok ? "text-success" : "text-danger"} aria-hidden="true">{check.ok ? "✓" : "✗"}</span>
        <span>{check.label}</span><span className="text-xs text-muted">{check.detail}</span>
      </li>)}</ul>
    </section> : null}
    {report.sections.map((section) => <SectionTable key={section.key} section={section} />)}
  </>;
}

function SectionTable({section}: {section: ReportSection}) {
  return <section className="card mt-6 p-6">
    <h2 className="font-semibold">{section.title}</h2>
    {section.description ? <p className="mt-1 text-sm text-muted">{section.description}</p> : null}
    {section.rows.length === 0 ? <p className="mt-4 text-sm text-muted">Tidak ada data pada periode ini.</p> : <>
      <div className="mt-4 overflow-x-auto"><table className="w-full min-w-160 text-left text-sm">
        <thead><tr className="border-b border-border text-muted">{section.columns.map((col) => <th key={col.key} className={`py-3 pr-4 font-medium ${numeric(col.type) ? "text-right" : ""}`}>{col.label}</th>)}</tr></thead>
        <tbody>{section.rows.map((row, index) => <tr key={index} className="border-b border-border align-top">
          {section.columns.map((col) => <td key={col.key} className={`py-3 pr-4 ${numeric(col.type) ? "whitespace-nowrap text-right tabular-nums" : ""} ${numeric(col.type) && Number(row[col.key]) < 0 ? "text-danger" : ""}`}>{formatCell(row[col.key], col.type)}</td>)}
        </tr>)}</tbody>
        {section.totals ? <tfoot><tr className="border-t-2 border-foreground/40 font-semibold">
          {section.columns.map((col) => <td key={col.key} className={`py-3 pr-4 ${numeric(col.type) ? "whitespace-nowrap text-right tabular-nums" : ""}`}>{col.key in section.totals! ? formatCell(section.totals![col.key], col.type) : ""}</td>)}
        </tr></tfoot> : null}
      </table></div>
      {section.truncated ? <p className="mt-3 text-xs text-muted">Daftar dipotong pada 500 baris; persempit filter untuk rincian lengkap.</p> : null}
    </>}
  </section>;
}
