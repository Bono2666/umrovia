"use client";

import { useCallback, useEffect, useState } from "react";
import {
  EmptyState,
  ErrorState,
  FormField,
  LoadingState,
  StatusBadge,
  BTN_DANGER,
} from "@/components/workspace/ui";
import {
  apiFetch,
  hasPermission,
  problemMessage,
  type MembershipRow,
  type RoleRow,
  type UserPayload,
} from "@/lib/api";

/**
 * Pengguna & Role (S06, §4.1): daftar membership + undang staf
 * (POST /memberships), ganti role (PATCH), cabut akses (DELETE), dan daftar
 * role + permission (GET /roles). Aksi ditutup berdasarkan permission
 * klien (`memberships.write/.manage`) — server tetap menegaskan ulang.
 */
export default function PenggunaPage() {
  const [perms, setPerms] = useState<string[] | null>(null);
  const [rows, setRows] = useState<MembershipRow[] | null>(null);
  const [roles, setRoles] = useState<RoleRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [noAccess, setNoAccess] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRoleId, setInviteRoleId] = useState("");
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    // Permission workspace aktif (mirror resolusi di WorkspaceShell).
    apiFetch<UserPayload>("/me").then((result) => {
      if (!result.ok) {
        setNoAccess(true);
        return;
      }
      const { memberships, active_tenant_slug } = result.data;
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
    setMessage(null);
    const result = await apiFetch(`/memberships/${row.id}`, {
      method: "PATCH",
      body: JSON.stringify({ role_id: roleId }),
    });
    if (!result.ok) {
      setError(problemMessage(result.error));
      return;
    }
    setMessage(`Peran ${row.user.email} diubah.`);
    load();
  }

  async function onRevoke(row: MembershipRow) {
    const confirmed = window.confirm(
      `Cabut akses ${row.user.email} dari workspace ini?`,
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
      <div className="mx-auto max-w-3xl">
        <h1 className="text-2xl font-bold">Pengguna & Role</h1>
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
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-bold">Pengguna & Role</h1>
      <p className="mt-1 text-sm text-muted">
        Kelola staf travel dan peran mereka (Owner dapat mengubah role dan
        mencabut akses; audit tercatat).
      </p>

      {message ? (
        <p className="mt-4 border border-success/30 bg-success/10 p-3 text-sm text-success" role="status">
          {message}
        </p>
      ) : null}
      {error ? (
        <div className="mt-4">
          <ErrorState message={error} />
        </div>
      ) : null}

      <section className="card mt-6 p-6">
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
                  <th className="py-2 pr-4">Email</th>
                  <th className="py-2 pr-4">Nama</th>
                  <th className="py-2 pr-4">Peran</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-b border-border/60">
                    <td className="py-2 pr-4">{row.user.email}</td>
                    <td className="py-2 pr-4">{row.user.full_name || "-"}</td>
                    <td className="py-2 pr-4">
                      {canManage && roles.length > 0 ? (
                        <select
                          className="input w-auto py-1 text-sm"
                          value={row.role_id ?? ""}
                          onChange={(event) => onChangeRole(row, event.target.value)}
                          aria-label={`Ubah peran ${row.user.email}`}
                        >
                          {roles.map((role) => (
                            <option key={role.id} value={role.id}>
                              {role.name}
                            </option>
                          ))}
                        </select>
                      ) : (
                        row.role ?? "-"
                      )}
                    </td>
                    <td className="py-2 pr-4">
                      <StatusBadge tone={row.status === "ACTIVE" ? "success" : "warning"}>
                        {row.status}
                      </StatusBadge>
                    </td>
                    <td className="py-2">
                      {canManage && row.status !== "REVOKED" ? (
                        <button type="button" className={BTN_DANGER} onClick={() => onRevoke(row)}>
                          Cabut akses
                        </button>
                      ) : (
                        <span className="text-xs text-muted">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {canInvite ? (
        <section className="card mt-4 p-6">
          <h2 className="font-semibold">Undang staf baru</h2>
          <p className="mt-1 text-xs text-muted">
            Pengguna baru menerima undangan email; ia aktif setelah verifikasi
            email (anti-enumeration — pesan sukses sama untuk email baru/lama).
          </p>
          <form onSubmit={onInvite} className="mt-4 grid gap-4 sm:grid-cols-2">
            <FormField label="Email" htmlFor="invite-email" error={inviteError}>
              <input
                id="invite-email"
                type="email"
                className="input"
                value={inviteEmail}
                onChange={(event) => setInviteEmail(event.target.value)}
                placeholder="nama@travel.id"
                required
              />
            </FormField>
            <FormField label="Peran" htmlFor="invite-role">
              <select
                id="invite-role"
                className="input"
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
              </select>
            </FormField>
            <div className="sm:col-span-2">
              <button type="submit" className="btn-primary" disabled={busy}>
                {busy ? "Mengirim…" : "Kirim undangan"}
              </button>
            </div>
          </form>
        </section>
      ) : null}

      {canReadRoles && roles.length > 0 ? (
        <section className="card mt-4 p-6">
          <h2 className="font-semibold">Peran</h2>
          <ul className="mt-3 space-y-3">
            {roles.map((role) => (
              <li key={role.id}>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold">{role.name}</span>
                  {role.is_system ? (
                    <StatusBadge>SISTEM</StatusBadge>
                  ) : null}
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {(role.permissions.length > 0 ? role.permissions : ["(tanpa permission)"]).map((perm) => (
                    <code
                      key={perm}
                      className="border border-border bg-background px-1.5 py-0.5 text-[0.7rem] text-muted"
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

      <p className="mt-4 text-xs text-muted">
        Batas uji coba: maksimal 3 pengguna internal (TR04) — penambahan di atas
        kuota ditolak server dengan kode TRIAL_USER_LIMIT.
      </p>
    </div>
  );
}
