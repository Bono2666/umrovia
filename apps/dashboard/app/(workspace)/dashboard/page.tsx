"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/workspace/ui";
import { apiFetch, type BankAccount, type MembershipRow, type RoleRow, type TrialStatus } from "@/lib/api";
import { formatDate, formatRemaining } from "@/lib/format";

const CHECKLIST = [
  { step: "1", label: "Lengkapi profil travel", note: "Branding & invoice → halaman Profil Travel", href: "/dashboard/profil" },
  { step: "2", label: "Daftarkan rekening bank resmi", note: "Untuk instruksi DP — halaman Kas & Bank", href: "/dashboard/rekening" },
  { step: "3", label: "Undang staf & atur role", note: "Owner/Admin/Sales/Finance → Pengguna & Role", href: "/dashboard/pengguna" },
  { step: "4", label: "Buat paket & jadwal keberangkatan", note: "Menyusul di Sprint S08", href: null },
  { step: "5", label: "Simulasikan booking, DP & invoice", note: "Booking S09 · Pembayaran S11", href: null },
];

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
 * travel (staf, role, rekening) + quick-start. Modul operasional (paket,
 * booking, manifest) menyusul S07–S11 — checklist menunjuk halaman config
 * yang sudah tersedia.
 */
export default function DashboardPage() {
  const trial = useOptional<TrialStatus>("/trial/status");
  const memberships = useOptional<{ results: MembershipRow[] }>("/memberships");
  const roles = useOptional<{ results: RoleRow[] }>("/roles");
  const bank = useOptional<{ results: BankAccount[] }>("/bank-accounts");

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

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-bold">Ringkasan</h1>
      <p className="mt-1 text-sm text-muted">
        Status workspace, konfigurasi travel, dan langkah mencoba alur lengkap
        (data demo tidak pernah menjadi tagihan).
      </p>

      {trial.data ? (
        <section className="card mt-6 p-6">
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
        <section className="mt-4 grid gap-3 sm:grid-cols-3">
          {tiles.map((tile) => (
            <div key={tile.label} className="card p-4">
              <p className="text-xs text-muted">{tile.label}</p>
              <p className="mt-1 text-xl font-bold">{tile.value}</p>
              {tile.note ? <p className="mt-0.5 text-xs text-muted">{tile.note}</p> : null}
            </div>
          ))}
        </section>
      ) : null}

      <section className="card mt-6 p-6">
        <h2 className="font-semibold">Quick-start checklist</h2>
        <ol className="mt-4 space-y-3">
          {CHECKLIST.map((item) => (
            <li key={item.step} className="flex items-start gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-white">
                {item.step}
              </span>
              <div>
                {item.href ? (
                  <Link href={item.href} className="text-sm font-medium text-primary underline-offset-2 hover:underline">
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
  );
}
