"use client";

import { useCallback, useEffect, useState } from "react";
import { Btn, EmptyState, ErrorState, FormField, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type Branch, type MembershipRow } from "@/lib/api";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";

const EMPTY = {code: "", name: "", manager_name: "", phone: "", address: ""};

/** MOD-03: cabang/unit kerja dan cabang default staf (isian awal booking, pengeluaran, transfer). */
export default function BranchesPage() {
  const {can, loading} = useWorkspacePermissions();
  const canManage = can("branches.manage");
  const [rows, setRows] = useState<Branch[] | null>(null);
  const [members, setMembers] = useState<MembershipRow[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState<Branch | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(() => apiFetch<{results: Branch[]}>("/branches").then((result) => {
    if (result.ok) setRows(result.data.results); else setError(problemMessage(result.error));
  }), []);
  useEffect(() => {
    if (loading || !can("branches.read")) return;
    void load();
    if (canManage && can("memberships.read")) void apiFetch<{results: MembershipRow[]}>("/memberships").then((result) => {if (result.ok) setMembers(result.data.results.filter((m) => m.status === "ACTIVE"));});
  }, [loading, can, canManage, load]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch<Branch>(editing ? `/branches/${editing.id}` : "/branches", {method: editing ? "PATCH" : "POST", body: JSON.stringify(form)});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setMessage(editing ? `Cabang ${result.data.code} diperbarui.` : `Cabang ${result.data.code} · ${result.data.name} ditambahkan.`);
    setEditing(null); setForm(EMPTY); void load();
  }

  async function toggle(branch: Branch) {
    setError(null); setMessage(null);
    const result = await apiFetch<Branch>(`/branches/${branch.id}`, {method: "PATCH", body: JSON.stringify({active: !branch.active})});
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setMessage(branch.active ? `${branch.code} dinonaktifkan; transaksi lama tetap tercatat.` : `${branch.code} diaktifkan kembali.`);
    void load();
  }

  async function assign(member: MembershipRow, branches: string[], branch: string | null) {
    setError(null); setMessage(null);
    const result = await apiFetch<{branch: Branch | null; branches: Branch[]}>(`/memberships/${member.id}/branch`, {method: "POST", body: JSON.stringify({branches, branch})});
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setMembers((prev) => prev.map((m) => m.id === member.id ? {...m, branch: result.data.branch, branches: result.data.branches} : m));
    setMessage(`Penugasan cabang ${member.user.full_name || member.user.email} disimpan.`);
    void load();
  }

  if (loading) return <LoadingState />;
  if (!can("branches.read")) return <EmptyState title="Anda tidak memiliki akses data cabang" />;
  const active = (rows ?? []).filter((b) => b.active);

  return <div className="workspace-page">
    <RevealText as="h1" variant="title" className="text-2xl font-bold">Cabang</RevealText>
    <p className="mt-1 max-w-3xl text-sm text-muted">Kantor cabang atau unit kerja. Booking, lead, pengeluaran dan transfer kas ditandai per cabang. Peran berakses “cabang sendiri” (default: Sales, Operations, Document Reviewer) hanya melihat cabang yang ditugaskan; Owner, Admin dan Finance melihat semua cabang. Atur cakupan peran di Pengguna & Role.</p>
    {error ? <div className="mt-4"><ErrorState message={error} /></div> : null}
    {message ? <p className="mt-4 border border-success/30 bg-success/10 p-3 text-sm text-success" role="status">{message}</p> : null}
    <div className="workspace-columns mt-6">
      <section className="card min-w-0 p-6">
        <h2 className="font-semibold">Daftar cabang</h2>
        {rows === null ? <LoadingState /> : rows.length === 0 ? <div className="mt-4"><EmptyState title="Belum ada cabang" description="Tanpa cabang, semua transaksi tercatat untuk kantor pusat." /></div> :
          <ul className="mt-4 divide-y divide-border">{rows.map((branch) => <li key={branch.id} className="py-4 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2"><span className="font-semibold">{branch.code}</span><span>{branch.name}</span>{branch.active ? null : <StatusBadge tone="neutral">Nonaktif</StatusBadge>}</p>
                <p className="mt-1 text-xs text-muted">{[branch.manager_name ? `PJ ${branch.manager_name}` : "", branch.phone, branch.address, `${branch.member_count ?? 0} staf`].filter(Boolean).join(" · ")}</p>
              </div>
              {canManage ? <div className="flex shrink-0 gap-3">
                <Btn size="xs" variant="link" onClick={() => {setEditing(branch); setForm({code: branch.code, name: branch.name, manager_name: branch.manager_name, phone: branch.phone, address: branch.address});}}>Ubah</Btn>
                <Btn size="xs" variant="link" onClick={() => void toggle(branch)}>{branch.active ? "Nonaktifkan" : "Aktifkan"}</Btn>
              </div> : null}
            </div>
          </li>)}</ul>}
        {canManage && members.length > 0 && active.length > 0 ? <>
          <h3 className="mt-8 font-semibold">Penugasan staf</h3>
          <p className="mt-1 text-xs text-muted">Staf dengan peran berakses <strong>cabang sendiri</strong> hanya melihat booking, invoice, lead, pengeluaran dan komisi cabang yang dicentang, ditambah data tanpa cabang. Cabang default dipakai sebagai isian awal transaksi baru.</p>
          <ul className="mt-4 divide-y divide-border">{members.map((member) => {
            const assigned = (member.branches ?? []).map((b) => b.id);
            const toggle = (id: string, on: boolean) => {
              const next = on ? [...assigned, id] : assigned.filter((x) => x !== id);
              void assign(member, next, member.branch && next.includes(member.branch.id) ? member.branch.id : next[0] ?? null);
            };
            return <li key={member.id} className="py-3 text-sm">
              <p className="flex flex-wrap items-center gap-2"><span className="font-medium">{member.user.full_name || member.user.email}</span><span className="text-xs text-muted">{member.role ?? "-"}</span>
                <StatusBadge tone={member.branch_scope === "OWN" ? "warning" : "neutral"}>{member.branch_scope === "OWN" ? "Cabang sendiri" : "Semua cabang"}</StatusBadge></p>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">{active.map((branch) => <label key={branch.id} className="flex items-center gap-1.5">
                <input type="checkbox" checked={assigned.includes(branch.id)} onChange={(event) => toggle(branch.id, event.target.checked)} />{branch.code}
              </label>)}</div>
              {assigned.length > 1 ? <FormSelect label="Cabang default" htmlFor={`member-branch-${member.id}`} value={member.branch?.id ?? ""} onChange={(event) => void assign(member, assigned, event.target.value || null)}>
                {active.filter((b) => assigned.includes(b.id)).map((branch) => <option key={branch.id} value={branch.id}>{branch.code} · {branch.name}</option>)}
              </FormSelect> : null}
              {member.branch_scope === "OWN" && assigned.length === 0 ? <p className="mt-1 text-xs text-warning">Belum ditugaskan: hanya melihat data tanpa cabang.</p> : null}
            </li>;
          })}</ul>
        </> : null}
      </section>
      {canManage ? <section className="card min-w-0 p-6"><h2 className="font-semibold">{editing ? `Ubah ${editing.code}` : "Tambah cabang"}</h2>
        <form className="mt-5" onSubmit={save}>
          <FormField label="Kode" htmlFor="branch-code" maxLength={16} value={form.code} onChange={(event) => setForm({...form, code: event.target.value.toUpperCase()})} required hint="2–16 huruf/angka, mis. JKT, BKS-01." />
          <FormField label="Nama cabang" htmlFor="branch-name" maxLength={120} value={form.name} onChange={(event) => setForm({...form, name: event.target.value})} required />
          <FormField label="Penanggung jawab" htmlFor="branch-manager" maxLength={160} value={form.manager_name} onChange={(event) => setForm({...form, manager_name: event.target.value})} />
          <FormField label="Telepon" htmlFor="branch-phone" maxLength={32} value={form.phone} onChange={(event) => setForm({...form, phone: event.target.value})} />
          <FormField label="Alamat" htmlFor="branch-address" maxLength={500} value={form.address} onChange={(event) => setForm({...form, address: event.target.value})} />
          <div className="flex flex-wrap gap-3">
            <Btn type="submit" loading={busy} disabled={!form.code.trim() || !form.name.trim()}>{editing ? "Simpan perubahan" : "Tambah cabang"}</Btn>
            {editing ? <Btn type="button" variant="tint" onClick={() => {setEditing(null); setForm(EMPTY);}}>Batal</Btn> : null}
          </div>
        </form>
      </section> : null}
    </div>
  </div>;
}
