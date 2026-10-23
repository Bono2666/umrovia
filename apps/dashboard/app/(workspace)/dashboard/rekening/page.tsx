"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Btn,
  EmptyState,
  ErrorState,
  FormField,
  LoadingState,
  StatusBadge,
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
                <Btn variant="tint" className="ml-auto" onClick={() => onToggle(account)}>
                  {account.active ? "Nonaktifkan" : "Aktifkan"}
                </Btn>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card mt-4 p-6">
        <h2 className="font-semibold">Tambah rekening</h2>
        {/* Field = form-control 1:1 form kontak; ritme antar-field datang
            dari .form-group (55px) → tanpa grid/gap. */}
        <form onSubmit={onAdd} className="mt-8">
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
            hint="Hanya 4 digit terakhir yang disimpan (write-only)."
            error={formErrors.account_number}
            value={accountNumber}
            onChange={(event) => setAccountNumber(event.target.value)}
            inputMode="numeric"
            placeholder="1234567890"
            required
          />
          {formErrors.form ? (
            <p className="error-message" role="alert">
              {formErrors.form}
            </p>
          ) : null}
          <div className="form-submit">
            <Btn type="submit" disabled={busy}>
              {busy ? "Menyimpan…" : "Tambah rekening"}
            </Btn>
          </div>
        </form>
      </section>
    </div>
  );
}
