"use client";

import { useCallback, useEffect, useState } from "react";
import {
  EmptyState,
  ErrorState,
  FormField,
  LoadingState,
  StatusBadge,
  BTN_SECONDARY,
} from "@/components/workspace/ui";
import { apiFetch, problemMessage, type BankAccount } from "@/lib/api";

/**
 * Kas & Bank (S06, §5.3): daftar rekening bank resmi travel (nomor hanya
 * masked — nomor penuh tak pernah disimpan/dikembalikan), tambah rekening
 * (nomor write-only), dan toggle aktif. Tanpa permission `bank_accounts.*`
 * → tampil status tanpa akses (server menolak semua operasi).
 */
export default function RekeningPage() {
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
        accountNumber.replace(/\D/g, "").length >= 8
          ? null
          : "Nomor rekening minimal 8 digit.",
    };
    setFormErrors(errors);
    if (Object.values(errors).some(Boolean)) return;

    setBusy(true);
    setMessage(null);
    const result = await apiFetch<{ bank_account: BankAccount }>("/bank-accounts", {
      method: "POST",
      body: JSON.stringify({
        bank_name: bankName.trim(),
        account_name: accountName.trim(),
        account_number: accountNumber.replace(/\D/g, ""),
      }),
    });
    setBusy(false);
    if (!result.ok) {
      setFormErrors({ form: problemMessage(result.error) });
      return;
    }
    setBankName("");
    setAccountName("");
    setAccountNumber("");
    setMessage(
      `Rekening tersimpan (tersimpan sebagai nomor masked ${result.data.bank_account.account_masked}).`,
    );
    load();
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
      <div className="mx-auto max-w-3xl">
        <h1 className="text-2xl font-bold">Kas &amp; Bank</h1>
        <div className="mt-6">
          <EmptyState
            title="Halaman ini khusus Owner/Admin/Finance"
            description="Peran Anda tidak memiliki akses rekening bank (bank_accounts.read)."
          />
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-bold">Kas &amp; Bank</h1>
      <p className="mt-1 text-sm text-muted">
        Rekening bank resmi travel untuk instruksi pembayaran DP. Nomor rekening
        disimpan hanya sebagai 4 digit terakhir (masked, §5.3) — tidak pernah
        dikembalikan utuh oleh API.
      </p>

      {message ? (
        <p className="mt-4 rounded border border-success/30 bg-success/10 p-3 text-sm text-success" role="status">
          {message}
        </p>
      ) : null}
      {error ? (
        <div className="mt-4">
          <ErrorState message={error} />
        </div>
      ) : null}

      <section className="card mt-6 p-6">
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
                <code className="rounded bg-background px-2 py-0.5 text-xs">
                  {account.account_masked}
                </code>
                <StatusBadge tone={account.active ? "success" : "neutral"}>
                  {account.active ? "AKTIF" : "NONAKTIF"}
                </StatusBadge>
                <button
                  type="button"
                  className={`${BTN_SECONDARY} ml-auto`}
                  onClick={() => onToggle(account)}
                >
                  {account.active ? "Nonaktifkan" : "Aktifkan"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card mt-4 p-6">
        <h2 className="font-semibold">Tambah rekening</h2>
        <form onSubmit={onAdd} className="mt-4 grid gap-4 sm:grid-cols-2">
          <FormField label="Nama bank" htmlFor="bank-name" error={formErrors.bank_name}>
            <input
              id="bank-name"
              className="input"
              value={bankName}
              onChange={(event) => setBankName(event.target.value)}
              placeholder="BCA"
              required
            />
          </FormField>
          <FormField label="Nama pemilik rekening" htmlFor="account-name" error={formErrors.account_name}>
            <input
              id="account-name"
              className="input"
              value={accountName}
              onChange={(event) => setAccountName(event.target.value)}
              placeholder="PT Travel Nusantara"
              required
            />
          </FormField>
          <FormField
            label="Nomor rekening"
            htmlFor="account-number"
            hint="Hanya 4 digit terakhir yang disimpan (write-only)."
            error={formErrors.account_number}
          >
            <input
              id="account-number"
              className="input"
              value={accountNumber}
              onChange={(event) => setAccountNumber(event.target.value)}
              inputMode="numeric"
              placeholder="1234567890"
              required
            />
          </FormField>
          <div className="flex items-end sm:col-span-2">
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? "Menyimpan…" : "Tambah rekening"}
            </button>
          </div>
          {formErrors.form ? (
            <p className="text-xs text-danger sm:col-span-2" role="alert">
              {formErrors.form}
            </p>
          ) : null}
        </form>
      </section>
    </div>
  );
}
