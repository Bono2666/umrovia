"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Btn,
  EmptyState,
  ErrorState,
  FormField,
  FormCheckbox,
  LoadingState,
  StatusBadge,
} from "@/components/workspace/ui";
import { apiFetch, problemMessage, type BankAccount } from "@/lib/api";
import { changedFields, focusForm, formErrors as apiFormErrors } from "@/lib/forms";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";

/**
 * Kas & Bank (S06, §5.3): daftar rekening bank resmi travel (nomor hanya
 * masked — nomor penuh tak pernah disimpan/dikembalikan), tambah rekening
 * (nomor write-only), dan toggle aktif. Tanpa permission `bank_accounts.*`
 * → tampil status tanpa akses (server menolak semua operasi).
 */
export default function RekeningPage() {
  const {can} = useWorkspacePermissions();
  const [editing, setEditing] = useState<BankAccount | null>(null);
  const [active, setActive] = useState(true);
  const [rows, setRows] = useState<BankAccount[] | null>(null);
  const [noAccess, setNoAccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [bankName, setBankName] = useState("");
  const [accountName, setAccountName] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [formErrors, setFormErrors] = useState<Record<string, string | null>>({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    apiFetch<{ results: BankAccount[] }>("/bank-accounts").then((result) => {
      if (result.ok) setRows(result.data.results);
      else if (result.error.status === 403) setNoAccess(true);
      else setError(problemMessage(result.error));
    });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function onAdd(event: React.FormEvent) {
    event.preventDefault();
    const errors: Record<string, string | null> = {
      bank_name: bankName.trim() ? null : "Nama bank wajib diisi.",
      account_name: accountName.trim() ? null : "Nama pemilik wajib diisi.",
      account_number:
        (editing && !accountNumber.trim()) || /^\d{8,32}$/.test(accountNumber.trim())
          ? null
          : "Nomor rekening harus 8–32 digit.",
    };
    setFormErrors(errors);
    if (Object.values(errors).some(Boolean)) return;

    setBusy(true);
    setMessage(null);
    const values = {bank_name:bankName.trim(), account_name:accountName.trim(), active};
    const payload = {...(editing ? changedFields(values, editing) : {bank_name:values.bank_name, account_name:values.account_name}),
      ...(!editing || accountNumber.trim() ? {account_number:accountNumber.trim()} : {})};
    if (editing && Object.keys(payload).length === 0) {setBusy(false); setMessage("Tidak ada perubahan pada rekening."); return;}
    const result = await apiFetch<{ bank_account: BankAccount }>(editing ? `/bank-accounts/${editing.id}` : "/bank-accounts", {
      method: editing ? "PATCH" : "POST",
      body: JSON.stringify(payload),
    });
    setBusy(false);
    if (!result.ok) {
      setFormErrors(apiFormErrors(result.error));
      return;
    }
    resetForm();
    setMessage(
      `Rekening tersimpan (tersimpan sebagai nomor masked ${result.data.bank_account.account_masked}).`,
    );
    load();
  }

  function resetForm() {
    setEditing(null); setBankName(""); setAccountName(""); setAccountNumber(""); setActive(true); setFormErrors({});
  }

  function editAccount(account: BankAccount) {
    resetForm(); setEditing(account); setBankName(account.bank_name); setAccountName(account.account_name); setActive(account.active);
    setMessage(null); setError(null); focusForm("bank-form");
  }

  async function onToggle(account: BankAccount) {
    setError(null);
    const result = await apiFetch<{ bank_account: BankAccount }>(
      `/bank-accounts/${account.id}`,
      {
        method: "PATCH",
        body: JSON.stringify({ active: !account.active }),
      },
    );
    if (!result.ok) {
      setError(problemMessage(result.error));
      return;
    }
    load();
  }

  if (noAccess) {
    return (
      <div className="workspace-page">
        <h1 className="text-2xl font-bold">Kas &amp; Bank</h1>
        <div className="mt-6">
          <EmptyState
            title="Halaman ini khusus staf dengan akses rekening"
            description="Peran Anda tidak memiliki akses rekening bank (bank_accounts.read)."
          />
        </div>
      </div>
    );
  }

  return (
    <div className="workspace-page">
      <h1 className="text-2xl font-bold">Kas &amp; Bank</h1>
      <p className="mt-1 text-sm text-muted">
        Rekening bank resmi travel untuk instruksi pembayaran DP. Nomor rekening
        disimpan hanya sebagai 4 digit terakhir (masked, §5.3) — tidak pernah
        dikembalikan utuh oleh API.
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

      <div className="workspace-columns mt-6">
      <section className="card p-6">
        <h2 className="font-semibold">Rekening terdaftar</h2>
        {rows === null ? (
          <div className="mt-4">
            <LoadingState label="Memuat rekening…" />
          </div>
        ) : rows.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="Belum ada rekening bank"
              description="Tambahkan rekening resmi agar jamaah menerima instruksi pembayaran yang benar."
            />
          </div>
        ) : (
          <ul className="mt-4 divide-y divide-border/60">
            {rows.map((account) => (
              <li key={account.id} className="flex flex-wrap items-center gap-3 py-3 text-sm">
                <div className="min-w-40">
                  <p className="font-semibold">{account.bank_name}</p>
                  <p className="text-xs text-muted">{account.account_name}</p>
                </div>
                <code className="border border-border bg-background px-2 py-0.5 text-xs">
                  {account.account_masked}
                </code>
                <StatusBadge tone={account.active ? "success" : "neutral"}>
                  {account.active ? "AKTIF" : "NONAKTIF"}
                </StatusBadge>
                {can("bank_accounts.write") ? <><Btn variant="tint" className="ml-auto" disabled={busy} onClick={() => editAccount(account)}>Ubah rekening</Btn>
                <Btn variant="tint" disabled={busy} onClick={() => onToggle(account)}>
                  {account.active ? "Nonaktifkan" : "Aktifkan"}
                </Btn></> : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      {can("bank_accounts.write") ? <section className="card p-6">
        <h2 className="font-semibold">{editing ? `Ubah rekening ${editing.bank_name}` : "Tambah rekening"}</h2>
        {/* Workspace controls use compact typography and field spacing. */}
        <form id="bank-form" onSubmit={onAdd} className="mt-6 scroll-mt-24"><fieldset className="min-w-0" disabled={busy}>
          <FormField
            label="Nama bank"
            htmlFor="bank-name"
            error={formErrors.bank_name}
            value={bankName}
            onChange={(event) => setBankName(event.target.value)}
            placeholder="BCA"
            required
          />
          <FormField
            label="Nama pemilik rekening"
            htmlFor="account-name"
            error={formErrors.account_name}
            value={accountName}
            onChange={(event) => setAccountName(event.target.value)}
            placeholder="PT Travel Nusantara"
            required
          />
          <FormField
            label="Nomor rekening"
            htmlFor="account-number"
            disabled={!!editing && !editing.number_editable}
            hint={editing ? editing.number_editable ? `Tersimpan: ${editing.account_masked}. Kosongkan untuk mempertahankan nomor.` : `Tersimpan: ${editing.account_masked}. Sudah digunakan pada pembayaran; tambahkan rekening baru bila nomor berubah.` : "Hanya 4 digit terakhir yang disimpan."}
            error={formErrors.account_number}
            value={accountNumber}
            onChange={(event) => setAccountNumber(event.target.value)}
            inputMode="numeric"
            placeholder={editing ? "Isi hanya jika nomor perlu dikoreksi" : "1234567890"}
            required={!editing}
          />
          {editing ? <FormCheckbox id="bank-active" label="Rekening aktif" checked={active} onChange={setActive} /> : null}
          {formErrors.form ? (
            <p className="error-message" role="alert">
              {formErrors.form}
            </p>
          ) : null}
          <div className="form-submit">
            <Btn type="submit" disabled={busy}>
              {busy ? "Menyimpan…" : editing ? "Simpan perubahan" : "Tambah rekening"}
            </Btn>
            {editing ? <Btn type="button" variant="tint" className="ml-2" onClick={resetForm}>Batal ubah</Btn> : null}
          </div>
        </fieldset></form>
      </section> : null}
      </div>
    </div>
  );
}
