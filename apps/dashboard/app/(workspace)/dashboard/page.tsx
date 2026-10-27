"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/workspace/ui";
import { DashboardKpis } from "@/components/workspace/DashboardKpis";
import { apiFetch, type BankAccount, type MembershipRow, type RoleRow, type SettingsPayload, type TrialStatus, type SaasWallet } from "@/lib/api";
import { formatDate, formatIdr, formatRemaining } from "@/lib/format";
import { RevealText } from "@/components/marketing/RevealText";

type Step = { step: string; label: string; note: string; href: string; done: boolean | null };

/** Ambil data opsional; 403/404 → `forbidden` (tile disembunyikan). */
function useOptional<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [forbidden, setForbidden] = useState(false);
  useEffect(() => {
    apiFetch<T>(path).then((result) => {
      if (result.ok) setData(result.data);
      else if (result.error.status === 403 || result.error.status === 404) setForbidden(true);
    });
  }, [path]);
  return { data, forbidden };
}

/**
 * Ringkasan workspace (S06, UI-02/UI-03): data live trial + status config
 * travel (staf, role, rekening) + quick-start hingga simulasi DP S11.
 */
export default function DashboardPage() {
  const trial = useOptional<TrialStatus>("/trial/status");
  const memberships = useOptional<{ results: MembershipRow[] }>("/memberships");
  const roles = useOptional<{ results: RoleRow[] }>("/roles");
  const bank = useOptional<{ results: BankAccount[] }>("/bank-accounts");
  const wallet = useOptional<SaasWallet>("/wallet");
  const settings = useOptional<SettingsPayload>("/tenant/settings");
  const packages = useOptional<{ results: unknown[] }>("/packages");
  const departures = useOptional<{ results: unknown[] }>("/departures");
  // Cukup 1 baris untuk mengecek langkah onboarding (paginasi S19).
  const bookings = useOptional<{ results: unknown[] }>("/bookings?page=1&page_size=1");
  const invoices = useOptional<{ results: unknown[] }>("/invoices?page=1&page_size=1");
  const demo = wallet.data?.environment === "demo" || (trial.data !== null && !trial.data.converted_at);
  // null = tidak dapat diperiksa dengan peran ini (tanpa tanda centang).
  const has = (value: { results: unknown[] } | null, min = 1) => (value ? value.results.length >= min : null);
  const steps: Step[] = [
    { step: "01", label: "Lengkapi profil travel", note: "Alamat untuk invoice & kuitansi → Profil Travel", href: "/dashboard/profil", done: settings.data ? typeof settings.data.branding_json.address === "string" && settings.data.branding_json.address.trim() !== "" : null },
    { step: "02", label: "Daftarkan rekening bank resmi", note: "Dicantumkan pada invoice → Kas & Bank", href: "/dashboard/rekening", done: bank.data ? bank.data.results.some((row) => row.active) : null },
    { step: "03", label: "Undang staf & atur peran", note: "Admin, Sales, Finance → Pengguna & Role", href: "/dashboard/pengguna", done: has(memberships.data, 2) },
    { step: "04", label: "Buat paket & jadwal keberangkatan", note: "Harga standar atau per tipe kamar", href: "/dashboard/paket", done: packages.data && departures.data ? packages.data.results.length > 0 && departures.data.results.length > 0 : null },
    { step: "05", label: "Buat booking jamaah", note: "Pilih kamar per peserta lalu reservasi kursi", href: "/dashboard/booking", done: has(bookings.data) },
    { step: "06", label: demo ? "Terbitkan invoice & simulasikan DP" : "Terbitkan invoice & catat DP", note: "Invoice → pembayaran → verifikasi → kuitansi", href: "/dashboard/invoice", done: has(invoices.data) },
  ];
  const doneCount = steps.filter((item) => item.done).length;

  const tiles: { label: string; value: string; note?: string }[] = [];
  if (memberships.data) {
    const rows = memberships.data.results;
    tiles.push({
      label: "Pengguna internal",
      value: `${rows.filter((r) => r.status === "ACTIVE").length} aktif`,
      note: `${rows.length} anggota terdaftar`,
    });
  }
  if (roles.data) {
    tiles.push({ label: "Peran", value: `${roles.data.results.length} peran` });
  }
  if (bank.data) {
    tiles.push({
      label: "Rekening bank",
      value: `${bank.data.results.filter((r) => r.active).length} aktif`,
    });
  }
  const hasSummary = Boolean(trial.data) || Boolean(wallet.data) || tiles.length > 0;

  return (
    <div className="workspace-page">
      <RevealText as="h1" variant="title" className="text-2xl font-bold">Ringkasan</RevealText>
      <p className="mt-1 text-sm text-muted">
        Kinerja travel, hal yang perlu ditindaklanjuti dan langkah menyiapkan workspace{demo ? " (data demo tidak pernah menjadi tagihan)" : ""}.
      </p>

      <div className="mt-6"><DashboardKpis /></div>

      <div className="workspace-columns mt-6">
      {hasSummary ? <div className="space-y-4">
      {wallet.data ? <section className="card p-6">
        <h2 className="font-semibold">SaaS Wallet</h2>
        <p className="mt-2 text-2xl font-bold">{formatIdr(wallet.data.balance_idr)}</p>
        <p className="mt-2 text-sm text-muted">{wallet.data.environment === "demo" ? "Mode demo tanpa transaksi wallet nyata." : `Cukup untuk sekitar ${wallet.data.estimated_participant_capacity} jamaah.`}</p>
        {wallet.data.pending_charge_count > 0 ? <p className="mt-2 text-sm text-warning">{wallet.data.pending_charge_count} jamaah menunggu saldo ({formatIdr(wallet.data.pending_charge_idr)}) sebelum terkonfirmasi.</p> : null}
        <Link href="/dashboard/wallet" className="mt-3 inline-block text-sm text-primary underline">{wallet.data.pending_charge_count > 0 ? "Top-up saldo sekarang" : "Lihat saldo, top-up & mutasi"}</Link>
      </section> : null}
      {trial.data && !trial.data.converted_at ? (
        <section className="card p-6">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-semibold">Masa uji coba</h2>
            <StatusBadge tone={trial.data.converted_at ? "success" : "warning"}>
              {trial.data.converted_at ? "TERKONVERSI" : trial.data.trial_status}
            </StatusBadge>
          </div>
          {trial.data.converted_at ? (
            <p className="mt-2 text-sm text-muted">
              Workspace terkonversi ke produksi sejak{" "}
              {formatDate(trial.data.converted_at)}.
            </p>
          ) : (
            <p className="mt-2 text-sm">
              Berakhir <strong>{formatDate(trial.data.ends_at)}</strong>{" "}
              <span className="text-muted">
                ({formatRemaining(trial.data.ends_at)})
              </span>
            </p>
          )}
          <p className="mt-2 text-sm text-muted">
            Booking dummy: {trial.data.dummy_bookings_used}/
            {trial.data.dummy_bookings_limit} · Pengguna internal:{" "}
            {trial.data.internal_users_used}/{trial.data.internal_users_limit}
          </p>
        </section>
      ) : null}

      {tiles.length > 0 ? (
        <section className="grid gap-3 sm:grid-cols-2">
          {tiles.map((tile) => (
            <div key={tile.label} className="card p-4">
              <p className="text-xs text-muted">{tile.label}</p>
              <p className="mt-1 text-xl font-bold">{tile.value}</p>
              {tile.note ? <p className="mt-0.5 text-xs text-muted">{tile.note}</p> : null}
            </div>
          ))}
        </section>
      ) : null}
      </div> : null}

      <section className={`card p-6 ${hasSummary ? "" : "lg:col-span-2"}`}>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-semibold">Panduan memulai</h2>
          <span className="text-xs text-muted">{doneCount} dari {steps.length} langkah selesai</span>
        </div>
        <ol className="mt-4 space-y-3">
          {steps.map((item) => (
            <li key={item.step} className="flex items-start gap-3">
              <span
                aria-label={item.done ? "Selesai" : undefined}
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${item.done ? "bg-success/15 text-success" : "bg-primary text-white"}`}
              >
                {item.done ? "✓" : item.step}
              </span>
              <div>
                {item.href ? (
                  <Link href={item.href} className={`text-sm font-medium ${item.done ? "text-muted line-through decoration-muted/50" : "text-primary hover:text-primary-hover"}`}>
                    {item.label}
                  </Link>
                ) : (
                  <div className="text-sm font-medium">{item.label}</div>
                )}
                <div className="text-xs text-muted">{item.note}</div>
              </div>
            </li>
          ))}
        </ol>
      </section>
      </div>
    </div>
  );
}
