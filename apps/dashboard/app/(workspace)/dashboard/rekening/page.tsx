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
import { formatMasked } from "@/lib/format";
import { changedFields, focusForm, formErrors as apiFormErrors } from "@/lib/forms";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";
import { CashPanel } from "@/components/workspace/CashPanel";
import { FloatingNotice, focusRecord } from "@/components/workspace/FloatingNotice";

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
    focusRecord(result.data.bank_account.id);
    setMessage(
      `Rekening tersimpan (tersimpan sebagai nomor masked ${result.data.bank_account.account_masked}).`,
    );
    load();
  }

  function resetForm() {
    setEditing(null); setBankName(""); setAccountName(""); setAccountNumber(""); setActive(true); setFormErrors({});
  }

  async function removeAccount(account: BankAccount) {
    if (!window.confirm(`Hapus rekening ${account.bank_name} ${account.account_masked}? Rekening yang pernah dipakai cukup dinonaktifkan. Data yang belum pernah dipakai dihapus permanen.`)) return;
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch(`/bank-accounts/${account.id}`, { method: "DELETE" });
    setBusy(false);
    if (!result.ok) { setError(problemMessage(result.error)); return; }
    setMessage(`Rekening ${account.bank_name} ${account.account_masked} dihapus.`);
    load();
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
        <RevealText as="h1" variant="title" className="text-2xl font-bold">Kas &amp; Bank</RevealText>
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
      <RevealText as="h1" variant="title" className="text-2xl font-bold">Kas &amp; Bank</RevealText>
      <p className="mt-1 text-sm text-muted">
        Rekening resmi travel yang dicantumkan pada invoice untuk pembayaran
        jamaah. Demi keamanan, hanya 4 digit terakhir nomor rekening yang
        disimpan dan ditampilkan.
      </p>

      <FloatingNotice message={message} onDismiss={() => setMessage(null)} />
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
              <li key={account.id} data-record={account.id} className="py-4 text-sm">
                <p className="flex flex-wrap items-center gap-2 font-semibold">
                  {account.bank_name}
                  <StatusBadge tone={account.active ? "success" : "neutral"}>
                    {account.active ? "Aktif" : "Nonaktif"}
                  </StatusBadge>
                </p>
                <p className="text-xs text-muted">{account.account_name} · {formatMasked(account.account_masked)}</p>
                {can("bank_accounts.write") ? <div className="mt-3 flex flex-wrap gap-1.5">
                  <Btn variant="tint" size="xs" disabled={busy} onClick={() => editAccount(account)}>Ubah rekening</Btn>
                  <Btn variant="tint" size="xs" disabled={busy} onClick={() => onToggle(account)}>
                    {account.active ? "Nonaktifkan" : "Aktifkan"}
                  </Btn>
                  {account.deletable ? <Btn variant="danger" size="xs" disabled={busy || editing?.id === account.id} onClick={() => void removeAccount(account)}>Hapus</Btn> : null}
                </div> : null}
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
      {rows ? <CashPanel accounts={rows} /> : null}
    </div>
  );
}
