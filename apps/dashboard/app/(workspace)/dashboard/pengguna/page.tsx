"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Btn,
  EmptyState,
  FormField,
  FormSelect,
  FormTextarea,
  LoadingState,
  StatusBadge,
} from "@/components/workspace/ui";
import {
  apiFetch,
  hasPermission,
  problemMessage,
  type MembershipRow,
  type RoleRow,
  type UserPayload,
} from "@/lib/api";
import { RevealText } from "@/components/marketing/RevealText";
import { MemberSecurity } from "@/components/workspace/MemberSecurity";
import { FloatingNotice, focusRecord } from "@/components/workspace/FloatingNotice";

/**
 * Pengguna & Role (S06, §4.1): daftar membership + undang staf
 * (POST /memberships), ganti role (PATCH), cabut akses (DELETE), dan role
 * custom: tambah/ubah/hapus (POST/PATCH/DELETE /roles; hapus hanya bila tak dipakai). Aksi ditutup berdasarkan permission
 * klien (`memberships.write/.manage`) — server tetap menegaskan ulang.
 */
const MEMBER_STATUS: Record<string, string> = { ACTIVE: "Aktif", INVITED: "Diundang", SUSPENDED: "Ditangguhkan", REVOKED: "Dicabut" };

export default function PenggunaPage() {
  const [perms, setPerms] = useState<string[] | null>(null);
  const [currentEmail, setCurrentEmail] = useState<string | null>(null);
  const [rows, setRows] = useState<MembershipRow[] | null>(null);
  const [roles, setRoles] = useState<RoleRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [noAccess, setNoAccess] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRoleId, setInviteRoleId] = useState("");
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editingMember, setEditingMember] = useState<string | null>(null);
  const [roleDraft, setRoleDraft] = useState("");
  const [roleBusy, setRoleBusy] = useState(false);
  const [editingRole, setEditingRole] = useState<RoleRow | null>(null);
  const [creatingRole, setCreatingRole] = useState(false);
  const [roleName, setRoleName] = useState("");
  const [roleScope, setRoleScope] = useState<"ALL" | "OWN">("ALL");
  const [rolePermissions, setRolePermissions] = useState("");

  const load = useCallback(() => {
    // Permission workspace aktif (mirror resolusi di WorkspaceShell).
    apiFetch<UserPayload>("/me").then((result) => {
      if (!result.ok) {
        setNoAccess(true);
        return;
      }
      const { memberships, active_tenant_slug } = result.data;
      setCurrentEmail(result.data.email.toLowerCase());
      const active =
        memberships.find((m) => m.tenant.slug === (active_tenant_slug ?? "")) ??
        memberships.find((m) => m.status === "ACTIVE");
      setPerms(active?.permissions ?? []);
    });
    apiFetch<{ results: MembershipRow[] }>("/memberships").then((result) => {
      if (result.ok) setRows(result.data.results);
      else if (result.error.status === 403) setNoAccess(true);
      else setError(problemMessage(result.error));
    });
    apiFetch<{ results: RoleRow[] }>("/roles").then((result) => {
      if (result.ok) setRoles(result.data.results);
    });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const canInvite = perms ? hasPermission(perms, "memberships.write") : false;
  const canManage = perms ? hasPermission(perms, "memberships.manage") : false;
  const canReadRoles = perms ? hasPermission(perms, "roles.read") : true;
  const canWriteRoles = perms ? hasPermission(perms, "roles.write") : false;
  const hasSidePanels = canInvite || (canReadRoles && roles.length > 0);
  // Backend menolak mencabut/menurunkan Owner aktif terakhir; UI tidak menawarkannya.
  const activeOwners = rows?.filter((row) => row.role === "Owner" && row.status === "ACTIVE").length ?? 0;
  const isLastOwner = (row: MembershipRow) => row.role === "Owner" && row.status === "ACTIVE" && activeOwners <= 1;

  async function onInvite(event: React.FormEvent) {
    event.preventDefault();
    setInviteError(null);
    if (!inviteEmail.includes("@")) {
      setInviteError("Masukkan email yang valid.");
      return;
    }
    if (!inviteRoleId) {
      setInviteError("Pilih peran untuk staf baru.");
      return;
    }
    setBusy(true);
    const result = await apiFetch<{ user_status: string }>("/memberships", {
      method: "POST",
      body: JSON.stringify({ email: inviteEmail.trim().toLowerCase(), role_id: inviteRoleId }),
    });
    setBusy(false);
    if (!result.ok) {
      setInviteError(problemMessage(result.error));
      return;
    }
    setInviteEmail("");
    setMessage(
      result.data.user_status === "ACTIVE"
        ? "Anggota berhasil ditambahkan (langsung aktif)."
        : "Undangan terkirim. Anggota aktif setelah emailnya diverifikasi.",
    );
    load();
  }

  async function onChangeRole(row: MembershipRow, roleId: string) {
    if (!roleId || roleId === row.role_id) return;
    setMessage(null); setError(null); setRoleBusy(true);
    const result = await apiFetch(`/memberships/${row.id}`, {
      method: "PATCH",
      body: JSON.stringify({ role_id: roleId }),
    });
    setRoleBusy(false);
    if (!result.ok) {
      setError(problemMessage(result.error));
      return;
    }
    setEditingMember(null);
    focusRecord(row.id);
    setMessage(`Peran ${row.user.email} diubah.`);
    load();
  }

  async function onDeleteRole(role: RoleRow) {
    if (!window.confirm(`Hapus peran ${role.name}? Peran yang masih dipakai anggota tidak dapat dihapus.`)) return;
    setRoleBusy(true); setError(null); setMessage(null);
    const result = await apiFetch(`/roles/${role.id}`, { method: "DELETE" });
    setRoleBusy(false);
    if (!result.ok) { setError(problemMessage(result.error)); return; }
    if (editingRole?.id === role.id) setEditingRole(null);
    setMessage(`Peran ${role.name} dihapus.`);
    load();
  }

  const [securityMember, setSecurityMember] = useState<MembershipRow | null>(null);

  async function onRevoke(row: MembershipRow) {
    const self = row.user.email.toLowerCase() === currentEmail;
    const confirmed = window.confirm(
      self ? "Cabut akses Anda sendiri dari workspace ini? Anda akan kehilangan akses setelahnya." : `Cabut akses ${row.user.email} dari workspace ini?`,
    );
    if (!confirmed) return;
    setError(null);
    const result = await apiFetch(`/memberships/${row.id}`, { method: "DELETE" });
    if (!result.ok) {
      setError(problemMessage(result.error));
      return;
    }
    setMessage(`Akses ${row.user.email} dicabut.`);
    load();
  }

  if (noAccess) {
    return (
      <div className="workspace-page">
        <RevealText as="h1" variant="title" className="text-2xl font-bold">Pengguna & Role</RevealText>
        <div className="mt-6">
          <EmptyState
            title="Halaman ini khusus Owner/Admin"
            description="Peran Anda tidak memiliki akses mengelola pengguna. Minta Owner jika perlu."
          />
        </div>
      </div>
    );
  }

  return (
    <div className="workspace-page">
      <RevealText as="h1" variant="title" className="text-2xl font-bold">Pengguna & Role</RevealText>
      <p className="mt-1 text-sm text-muted">
        Kelola staf travel dan peran mereka (Owner dapat mengubah role dan
        mencabut akses; audit tercatat).
      </p>

      <FloatingNotice message={message} onDismiss={() => setMessage(null)} />
      <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />

      <div className="workspace-columns mt-6">
      <section className="card p-6 lg:col-span-2">
        <h2 className="font-semibold">Anggota workspace</h2>
        {rows === null ? (
          <div className="mt-4">
            <LoadingState label="Memuat anggota…" />
          </div>
        ) : rows.length === 0 ? (
          <div className="mt-4">
            <EmptyState title="Belum ada anggota" />
          </div>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted">
                  <th className="py-2 pr-4">Anggota</th>
                  <th className="hidden py-2 pr-4 sm:table-cell">Peran</th>
                  <th className="hidden py-2 pr-4 sm:table-cell">Status</th>
                  <th className="w-px whitespace-nowrap py-2 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} data-record={row.id} className="border-b border-border/60">
                    <td className="py-3 pr-4">
                      <p className="font-medium">
                        {row.user.full_name || row.user.email}
                        {row.user.email.toLowerCase() === currentEmail ? <span className="ml-2 text-xs font-normal text-muted">(Anda)</span> : null}
                      </p>
                      {row.user.full_name ? <p className="mt-0.5 break-all text-xs text-muted">{row.user.email}</p> : null}
                      {editingMember !== row.id ? <p className="mt-1.5 flex flex-wrap items-center gap-2 text-xs sm:hidden">
                        <span>{row.role ?? "-"}</span>
                        <StatusBadge tone={row.status === "ACTIVE" ? "success" : row.status === "REVOKED" ? "danger" : "warning"}>{MEMBER_STATUS[row.status] ?? row.status}</StatusBadge>
                      </p> : null}
                    </td>
                    <td className={`${editingMember === row.id ? "table-cell" : "hidden"} py-3 pr-4 sm:table-cell`}>
                      {editingMember === row.id ? (
                        <div><FormSelect
                          htmlFor={`role-${row.id}`}
                          className="w-full min-w-24 pb-1 text-sm"
                          value={roleDraft}
                          disabled={roleBusy}
                          onChange={(event) => setRoleDraft(event.target.value)}
                          aria-label={`Ubah peran ${row.user.email}`}
                        >
                          {roles.map((role) => (
                            <option key={role.id} value={role.id}>
                              {role.name}
                            </option>
                          ))}
                        </FormSelect></div>
                      ) : (
                        row.role ?? "-"
                      )}
                    </td>
                    <td className="hidden py-3 pr-4 sm:table-cell">
                      <StatusBadge tone={row.status === "ACTIVE" ? "success" : row.status === "REVOKED" ? "danger" : "warning"}>
                        {MEMBER_STATUS[row.status] ?? row.status}
                      </StatusBadge>
                    </td>
                    <td className="w-px whitespace-nowrap py-3 pl-4 text-right">
                      <div className="flex flex-col items-end gap-2 sm:flex-row sm:items-center sm:justify-end">
                        {editingMember === row.id ? <>
                          <Btn size="xs" disabled={roleBusy || !roleDraft || roleDraft === row.role_id} onClick={() => onChangeRole(row, roleDraft)}>Simpan</Btn>
                          <Btn size="xs" variant="tint" disabled={roleBusy} onClick={() => setEditingMember(null)}>Batal</Btn>
                        </> : !canManage || row.status === "REVOKED" ? (
                          <span className="text-muted">—</span>
                        ) : isLastOwner(row) ? (
                          <span className="block max-w-20 whitespace-normal text-xs text-muted sm:max-w-none sm:whitespace-nowrap" title="Tambahkan Owner lain sebelum mengubah peran atau mencabut akses akun ini.">Owner terakhir</span>
                        ) : <>
                          <Btn size="xs" variant="tint" onClick={() => setSecurityMember(row)}>Keamanan</Btn>
                          {roles.length > 0 ? <Btn size="xs" variant="tint" disabled={roleBusy} onClick={() => {setEditingMember(row.id); setRoleDraft(row.role_id ?? ""); setError(null);}}>Ubah peran</Btn> : null}
                          <Btn size="xs" variant="danger" disabled={roleBusy} onClick={() => onRevoke(row)}>Cabut akses</Btn>
                        </>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {securityMember ? <div className="lg:col-span-2"><MemberSecurity member={securityMember} self={securityMember.user.email.toLowerCase() === currentEmail}
        onClose={() => setSecurityMember(null)} onChanged={(text) => {setMessage(text); setSecurityMember(null); load();}} /></div> : null}

      {hasSidePanels ? <div className="grid grid-cols-1 items-start gap-6 lg:col-span-2 lg:grid-cols-2">
      {canInvite ? (
        <section className="card p-6">
          <h2 className="font-semibold">Undang staf baru</h2>
          <p className="mt-1 text-xs text-muted">
            Pengguna baru menerima undangan email; ia aktif setelah verifikasi
            email (anti-enumeration — pesan sukses sama untuk email baru/lama).
          </p>
          <form onSubmit={onInvite} className="mt-6">
            <FormField
              label="Email"
              htmlFor="invite-email"
              type="email"
              error={inviteError}
              value={inviteEmail}
              onChange={(event) => setInviteEmail(event.target.value)}
              placeholder="nama@travel.id"
              required
            />
            <FormSelect
              label="Peran"
              htmlFor="invite-role"
              value={inviteRoleId}
              onChange={(event) => setInviteRoleId(event.target.value)}
              required
            >
              <option value="">Pilih peran…</option>
              {roles.map((role) => (
                <option key={role.id} value={role.id}>
                  {role.name}
                </option>
              ))}
            </FormSelect>
            <div className="form-submit">
              <Btn type="submit" disabled={busy}>
                {busy ? "Mengirim…" : "Kirim undangan"}
              </Btn>
            </div>
          </form>
        </section>
      ) : null}

      {canReadRoles && roles.length > 0 ? (
        <section className="card p-6">
          <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">Peran</h2>
            {canWriteRoles && !editingRole && !creatingRole ? <Btn size="xs" variant="tint" disabled={roleBusy} onClick={() => {setCreatingRole(true); setRoleName(""); setRolePermissions(""); setRoleScope("OWN"); setError(null);}}>Tambah peran</Btn> : null}</div>
          {editingRole || creatingRole ? <form className="mt-6" onSubmit={async (event) => {
            event.preventDefault(); setRoleBusy(true); setError(null);
            const body = JSON.stringify({name:roleName.trim(), branch_scope:roleScope, permissions:rolePermissions.split(/[\n,]/).map((item) => item.trim()).filter(Boolean)});
            const result = editingRole ? await apiFetch(`/roles/${editingRole.id}`, {method:"PATCH", body}) : await apiFetch("/roles", {method:"POST", body});
            setRoleBusy(false);
            if (!result.ok) {setError(problemMessage(result.error)); return;}
            focusRecord(editingRole?.id);
            setMessage(editingRole ? "Definisi peran tersimpan." : `Peran ${roleName.trim()} ditambahkan.`); setEditingRole(null); setCreatingRole(false); load();
          }}><fieldset className="min-w-0" disabled={roleBusy}><FormField label="Nama peran" htmlFor="role-name" value={roleName} onChange={(event) => setRoleName(event.target.value)} required maxLength={64} /><FormTextarea label="Izin peran" htmlFor="role-permissions" value={rolePermissions} onChange={(event) => setRolePermissions(event.target.value)} hint="Satu izin per baris. Perubahan berlaku untuk semua anggota yang memakai peran ini." /><FormSelect label="Cakupan cabang" htmlFor="role-scope" value={roleScope} onChange={(event) => setRoleScope(event.target.value as "ALL" | "OWN")} hint="Cabang sendiri: hanya booking, invoice, lead, pengeluaran dan komisi cabang yang ditugaskan (atur di menu Cabang), ditambah data tanpa cabang."><option value="OWN">Cabang sendiri</option><option value="ALL">Semua cabang</option></FormSelect><div className="flex flex-wrap gap-2"><Btn type="submit">{editingRole ? "Simpan perubahan" : "Tambah peran"}</Btn><Btn type="button" variant="tint" onClick={() => {setEditingRole(null); setCreatingRole(false);}}>{editingRole ? "Batal ubah" : "Batal"}</Btn></div></fieldset></form> : null}
          <ul className="mt-3 space-y-3">
            {roles.map((role) => (
              <li key={role.id} data-record={role.id}>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold">{role.name}</span>
                  {canWriteRoles && !role.is_system && role.name !== "Owner" ? <Btn variant="link" size="xs" disabled={roleBusy} onClick={() => {setCreatingRole(false); setEditingRole(role); setRoleName(role.name); setRolePermissions(role.permissions.join("\n")); setRoleScope(role.branch_scope ?? "ALL"); setError(null);}}>Ubah definisi peran</Btn> : null}
                  {canWriteRoles && !role.is_system && role.name !== "Owner" && rows !== null && !rows.some((row) => row.role_id === role.id) ? <Btn variant="link" size="xs" disabled={roleBusy || editingRole?.id === role.id} onClick={() => void onDeleteRole(role)}>Hapus</Btn> : null}
                  {role.is_system ? (
                    <StatusBadge>SISTEM</StatusBadge>
                  ) : null}
                  <span className="text-xs text-muted">{role.branch_scope === "OWN" ? "· cabang sendiri" : "· semua cabang"}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {(role.permissions.length > 0 ? role.permissions : ["(tanpa permission)"]).map((perm) => (
                    <code
                      key={perm}
                      className="break-all border border-border bg-background px-1.5 py-0.5 text-[0.7rem] text-muted"
                    >
                      {perm}
                    </code>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      </div> : null}
      </div>

      <p className="mt-4 text-xs text-muted">
        Selama masa uji coba, workspace dapat memiliki maksimal 3 pengguna
        internal.
      </p>
    </div>
  );
}
