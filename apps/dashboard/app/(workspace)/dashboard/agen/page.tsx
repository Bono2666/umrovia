"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Btn, EmptyState, ErrorState, FormField, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type Agent, type CommissionPolicy, type Paginated } from "@/lib/api";
import { formatDate, formatIdr } from "@/lib/format";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";
import { FloatingNotice, focusRecord } from "@/components/workspace/FloatingNotice";

type Package = {id: string; name: string};
const EMPTY_AGENT = {code: "", name: "", phone: "", email: "", business_id: "", area: "", level: "", bank_name: "", bank_account_name: "", bank_account_number: "", notes: ""};
const EMPTY_POLICY = {name: "", agent: "", package: "", kind: "FIXED_PER_PAX", amount: "", percent: "", trigger: "DP_VERIFIED", valid_from: "", valid_until: ""};
const digits = (value: string) => Number(value.replace(/\D/g, ""));

/** MOD-10: master agen (kredit penjualan booking) dan kebijakan komisi yang disnapshot saat reservasi. */
export default function AgentsPage() {
  const {can, loading} = useWorkspacePermissions();
  const canRead = can("agents.read");
  const canManage = can("agents.manage");
  const canPolicies = can("commissions.policies");
  const canSeePolicies = can("commissions.read");
  const [tab, setTab] = useState<"agents" | "policies">("agents");
  const [list, setList] = useState<Paginated<Agent> | null>(null);
  const [policies, setPolicies] = useState<CommissionPolicy[] | null>(null);
  const [packages, setPackages] = useState<Package[]>([]);
  const [agentOptions, setAgentOptions] = useState<Agent[]>([]);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState({q: "", active: "1"});
  const [form, setForm] = useState(EMPTY_AGENT);
  const [editing, setEditing] = useState<Agent | null>(null);
  const [policyForm, setPolicyForm] = useState(EMPTY_POLICY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const sequence = useRef(0);

  const load = useCallback(() => {
    const current = ++sequence.current;
    const params = new URLSearchParams(Object.entries({...query, page: String(page)}).filter(([, value]) => value)).toString();
    return apiFetch<Paginated<Agent>>(`/agents?${params}`).then((result) => {
      if (current !== sequence.current) return;
      if (result.ok) setList(result.data); else setError(problemMessage(result.error));
    });
  }, [query, page]);
  const loadPolicies = useCallback(() => apiFetch<{results: CommissionPolicy[]}>("/commission-policies").then((result) => {
    if (result.ok) setPolicies(result.data.results); else setError(problemMessage(result.error));
  }), []);
  useEffect(() => {if (!loading && canRead) void load();}, [loading, canRead, load]);
  useEffect(() => {
    if (loading || !canSeePolicies || tab !== "policies") return;
    void loadPolicies();
    void apiFetch<{results: Package[]}>("/packages").then((result) => {if (result.ok) setPackages(result.data.results);});
    void apiFetch<{results: Agent[]}>("/agents?active=1&page_size=100&page=1").then((result) => {if (result.ok) setAgentOptions(result.data.results);});
  }, [loading, canSeePolicies, tab, loadPolicies]);

  function startEdit(agent: Agent) {
    setEditing(agent); setError(null); setMessage(null);
    setForm({code: agent.code, name: agent.name, phone: agent.phone, email: agent.email, business_id: agent.business_id, area: agent.area, level: agent.level,
      bank_name: agent.bank_name, bank_account_name: agent.bank_account_name, bank_account_number: "", notes: agent.notes});
  }

  async function saveAgent(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true); setError(null); setMessage(null);
    const body: Record<string, string> = {...form};
    if (!body.bank_account_number) delete body.bank_account_number;
    if (!editing && !body.code) delete body.code;
    const result = await apiFetch<Agent>(editing ? `/agents/${editing.id}` : "/agents", {method: editing ? "PATCH" : "POST", body: JSON.stringify(body)});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    focusRecord(result.data.id);
    setMessage(editing ? `Data agen ${result.data.name} diperbarui.` : `Agen ${result.data.name} (${result.data.code}) ditambahkan.`);
    setEditing(null); setForm(EMPTY_AGENT); void load();
  }

  async function toggleActive(agent: Agent) {
    setError(null); setMessage(null);
    const result = await apiFetch<Agent>(`/agents/${agent.id}`, {method: "PATCH", body: JSON.stringify({active: !agent.active})});
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    focusRecord(agent.id);
    setMessage(result.data.active ? `${agent.name} diaktifkan kembali.` : `${agent.name} dinonaktifkan; booking lama tetap tercatat atas namanya.`);
    void load();
  }

  async function savePolicy(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch<CommissionPolicy>("/commission-policies", {method: "POST", body: JSON.stringify({
      name: policyForm.name, kind: policyForm.kind, trigger: policyForm.trigger, agent: policyForm.agent || null, package: policyForm.package || null,
      amount_idr: policyForm.kind === "FIXED_PER_PAX" ? digits(policyForm.amount) : 0, percent: policyForm.kind === "PERCENT_NET" ? policyForm.percent || "0" : "0",
      valid_from: policyForm.valid_from || null, valid_until: policyForm.valid_until || null,
    })});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    focusRecord(result.data.id);
    setMessage(`Kebijakan "${result.data.name}" berlaku untuk booking yang direservasi berikutnya.`);
    setPolicyForm(EMPTY_POLICY); void loadPolicies();
  }

  async function togglePolicy(policy: CommissionPolicy) {
    setError(null); setMessage(null);
    const result = await apiFetch<CommissionPolicy>(`/commission-policies/${policy.id}`, {method: "PATCH", body: JSON.stringify({active: !policy.active})});
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    void loadPolicies();
  }

  if (loading) return <LoadingState />;
  if (!canRead) return <EmptyState title="Anda tidak memiliki akses data agen" />;

  const policyValue = (p: CommissionPolicy) => p.kind === "FIXED_PER_PAX" ? `${formatIdr(p.amount_idr)} / jamaah` : `${p.percent}% dari harga bersih`;
  const scope = (p: CommissionPolicy) => [p.agent ? p.agent.name : "Semua agen", p.package ? p.package.name : "semua paket"].join(" · ");
  const period = (p: CommissionPolicy) => p.valid_from || p.valid_until ? `${p.valid_from ? formatDate(p.valid_from) : "…"} – ${p.valid_until ? formatDate(p.valid_until) : "…"}` : "Tanpa batas waktu";

  return <div className="workspace-page">
    <RevealText as="h1" variant="title" className="text-2xl font-bold">Agen</RevealText>
    <p className="mt-1 max-w-3xl text-sm text-muted">Agen yang mendapat kredit penjualan booking. Komisi dihitung dari kebijakan yang berlaku saat booking direservasi dan baru layak dibayar setelah syarat pembayaran tercapai.</p>
    {canSeePolicies ? <div className="mt-5 flex flex-wrap gap-2" role="tablist" aria-label="Bagian agen">
      {([["agents", "Daftar agen"], ["policies", "Kebijakan komisi"]] as const).map(([key, label]) =>
        <Btn key={key} role="tab" aria-selected={tab === key} variant={tab === key ? "solid" : "tint"} onClick={() => {setTab(key); setError(null); setMessage(null);}}>{label}</Btn>)}
    </div> : null}
    {error ? <div className="mt-4"><ErrorState message={error} /></div> : null}
    <FloatingNotice message={message} onDismiss={() => setMessage(null)} />

    {tab === "agents" ? <div className="workspace-columns mt-6">
      <section className="card min-w-0 p-6">
        <h2 className="font-semibold">Daftar agen</h2>
        <div className="expense-form mt-6 grid items-end gap-x-4 gap-y-8 sm:grid-cols-2">
          <FormField label="Cari" htmlFor="agent-search" placeholder="Nama, kode, telepon, area" value={query.q} onChange={(event) => {setPage(1); setQuery({...query, q: event.target.value});}} />
          <FormSelect label="Status" htmlFor="agent-filter-active" value={query.active} onChange={(event) => {setPage(1); setQuery({...query, active: event.target.value});}}>
            <option value="1">Aktif</option><option value="0">Nonaktif</option><option value="">Semua</option>
          </FormSelect>
        </div>
        {list === null ? <LoadingState /> : list.results.length === 0 ? <div className="mt-4"><EmptyState title="Belum ada agen" description="Tambahkan agen agar booking dapat dikreditkan dan komisinya dihitung." /></div> : <>
          <ul className="mt-4 divide-y divide-border">{list.results.map((agent) => <li key={agent.id} data-record={agent.id} className="py-4 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2"><span className="font-medium">{agent.name}</span><span className="text-xs text-muted">{agent.code}</span>{agent.active ? null : <StatusBadge tone="neutral">Nonaktif</StatusBadge>}</p>
                <p className="mt-1 text-xs text-muted">{[agent.phone, agent.area, agent.level, agent.bank_name ? `${agent.bank_name} ${agent.bank_account_masked}` : ""].filter(Boolean).join(" · ") || "Belum ada kontak"}</p>
                <p className="mt-1 text-xs text-muted">{agent.booking_count} booking aktif · komisi berjalan {formatIdr(agent.commission_open_idr)} · dibayar {formatIdr(agent.commission_paid_idr)}</p>
              </div>
              {canManage ? <div className="flex shrink-0 items-center gap-3">
                <Btn size="xs" variant="link" onClick={() => startEdit(agent)}>Ubah</Btn>
                <Btn size="xs" variant="link" onClick={() => void toggleActive(agent)}>{agent.active ? "Nonaktifkan" : "Aktifkan"}</Btn>
              </div> : null}
            </div>
          </li>)}</ul>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-sm"><Btn size="xs" variant="solid" disabled={!list.previous} onClick={() => setPage((value) => value - 1)}>Sebelumnya</Btn><span>Halaman {page}</span><Btn size="xs" variant="solid" disabled={!list.next} onClick={() => setPage((value) => value + 1)}>Berikutnya</Btn></div>
        </>}
      </section>
      {canManage ? <section className="card min-w-0 p-6"><h2 className="font-semibold">{editing ? `Ubah ${editing.name}` : "Tambah agen"}</h2>
        <form className="mt-6" onSubmit={saveAgent}>
          <FormField label="Nama" htmlFor="agent-name" maxLength={160} value={form.name} onChange={(event) => setForm({...form, name: event.target.value})} required />
          <FormField label="Kode (opsional)" htmlFor="agent-code" maxLength={32} value={form.code} onChange={(event) => setForm({...form, code: event.target.value})} hint={editing ? undefined : "Kosongkan untuk kode otomatis AG-xxxxxx."} />
          <FormField label="Telepon" htmlFor="agent-phone" maxLength={32} value={form.phone} onChange={(event) => setForm({...form, phone: event.target.value})} />
          <FormField label="Email" htmlFor="agent-email" type="email" value={form.email} onChange={(event) => setForm({...form, email: event.target.value})} />
          <FormField label="Area / cabang" htmlFor="agent-area" maxLength={120} value={form.area} onChange={(event) => setForm({...form, area: event.target.value})} />
          <FormField label="Level (opsional)" htmlFor="agent-level" maxLength={40} value={form.level} onChange={(event) => setForm({...form, level: event.target.value})} />
          <FormField label="Identitas bisnis" htmlFor="agent-business" maxLength={64} value={form.business_id} onChange={(event) => setForm({...form, business_id: event.target.value})} hint="NIK, NPWP atau NIB." />
          <FormField label="Bank" htmlFor="agent-bank" maxLength={100} value={form.bank_name} onChange={(event) => setForm({...form, bank_name: event.target.value})} />
          <FormField label="Nama pemilik rekening" htmlFor="agent-bank-owner" maxLength={160} value={form.bank_account_name} onChange={(event) => setForm({...form, bank_account_name: event.target.value})} />
          <FormField label="Nomor rekening" htmlFor="agent-bank-number" inputMode="numeric" maxLength={40} value={form.bank_account_number} onChange={(event) => setForm({...form, bank_account_number: event.target.value})}
            hint={editing?.bank_account_masked ? `Tersimpan ${editing.bank_account_masked}. Isi hanya untuk mengganti.` : "Hanya 4 digit terakhir yang disimpan."} />
          <FormField label="Catatan" htmlFor="agent-notes" maxLength={2000} value={form.notes} onChange={(event) => setForm({...form, notes: event.target.value})} />
          <div className="flex flex-wrap gap-3">
            <Btn type="submit" loading={busy} disabled={!form.name.trim()}>{editing ? "Simpan perubahan" : "Tambah agen"}</Btn>
            {editing ? <Btn type="button" variant="tint" onClick={() => {setEditing(null); setForm(EMPTY_AGENT);}}>Batal</Btn> : null}
          </div>
        </form>
      </section> : null}
    </div> : <div className="workspace-columns mt-6">
      <section className="card min-w-0 p-6">
        <h2 className="font-semibold">Kebijakan komisi</h2>
        <p className="mt-1 text-sm text-muted">Bila beberapa kebijakan cocok, yang paling spesifik dipakai: agen + paket, lalu agen, lalu paket, lalu umum. Perubahan tidak mengubah komisi yang sudah tercatat.</p>
        {policies === null ? <LoadingState /> : policies.length === 0 ? <div className="mt-4"><EmptyState title="Belum ada kebijakan komisi" description="Tanpa kebijakan, booking beragen tidak menghasilkan komisi." /></div> :
          <ul className="mt-4 divide-y divide-border">{policies.map((policy) => <li key={policy.id} data-record={policy.id} className="py-4 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2"><span className="font-medium">{policy.name}</span>{policy.active ? <StatusBadge tone="success">Aktif</StatusBadge> : <StatusBadge tone="neutral">Nonaktif</StatusBadge>}</p>
                <p className="mt-1 text-xs text-muted">{policyValue(policy)} · {policy.trigger_label} · {scope(policy)} · {period(policy)}</p>
              </div>
              {canPolicies ? <Btn size="xs" variant="link" onClick={() => void togglePolicy(policy)}>{policy.active ? "Nonaktifkan" : "Aktifkan"}</Btn> : null}
            </div>
          </li>)}</ul>}
      </section>
      {canPolicies ? <section className="card min-w-0 p-6"><h2 className="font-semibold">Tambah kebijakan</h2>
        <form className="mt-5" onSubmit={savePolicy}>
          <FormField label="Nama kebijakan" htmlFor="policy-name" maxLength={120} value={policyForm.name} onChange={(event) => setPolicyForm({...policyForm, name: event.target.value})} required />
          <FormSelect label="Jenis" htmlFor="policy-kind" value={policyForm.kind} onChange={(event) => setPolicyForm({...policyForm, kind: event.target.value})}>
            <option value="FIXED_PER_PAX">Nominal tetap per jamaah</option><option value="PERCENT_NET">Persentase harga bersih</option>
          </FormSelect>
          {policyForm.kind === "FIXED_PER_PAX"
            ? <FormField label="Nominal per jamaah (Rp)" htmlFor="policy-amount" inputMode="numeric" value={policyForm.amount} onChange={(event) => setPolicyForm({...policyForm, amount: event.target.value})} required hint={digits(policyForm.amount) > 0 ? formatIdr(digits(policyForm.amount)) : "Tanpa titik atau koma"} />
            : <FormField label="Persentase (%)" htmlFor="policy-percent" inputMode="decimal" value={policyForm.percent} onChange={(event) => setPolicyForm({...policyForm, percent: event.target.value.replace(",", ".")})} required hint="Dari harga bersih setelah diskon, mis. 2.5" />}
          <FormSelect label="Layak dibayar" htmlFor="policy-trigger" value={policyForm.trigger} onChange={(event) => setPolicyForm({...policyForm, trigger: event.target.value})}>
            <option value="DP_VERIFIED">Setelah DP terverifikasi</option><option value="FULLY_PAID">Setelah lunas</option>
          </FormSelect>
          <FormSelect label="Agen" htmlFor="policy-agent" value={policyForm.agent} onChange={(event) => setPolicyForm({...policyForm, agent: event.target.value})}>
            <option value="">Semua agen</option>{agentOptions.map((agent) => <option key={agent.id} value={agent.id}>{agent.name} ({agent.code})</option>)}
          </FormSelect>
          <FormSelect label="Paket" htmlFor="policy-package" value={policyForm.package} onChange={(event) => setPolicyForm({...policyForm, package: event.target.value})}>
            <option value="">Semua paket</option>{packages.map((pkg) => <option key={pkg.id} value={pkg.id}>{pkg.name}</option>)}
          </FormSelect>
          <FormField label="Berlaku mulai (opsional)" htmlFor="policy-from" type="date" value={policyForm.valid_from} onChange={(event) => setPolicyForm({...policyForm, valid_from: event.target.value})} />
          <FormField label="Berlaku sampai (opsional)" htmlFor="policy-until" type="date" value={policyForm.valid_until} onChange={(event) => setPolicyForm({...policyForm, valid_until: event.target.value})} />
          <Btn type="submit" loading={busy} disabled={!policyForm.name.trim()}>Simpan kebijakan</Btn>
        </form>
      </section> : null}
    </div>}
  </div>;
}
