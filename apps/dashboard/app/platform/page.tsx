"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ErrorState, LoadingState } from "@/components/workspace/ui";
import { apiFetch, problemMessage } from "@/lib/api";
import { formatIdr } from "@/lib/format";

type Overview = {
  as_of: string; tenants_by_state: Record<string, number>; trials_ending_7d: number; open_tickets: number; pending_terminations: number;
  wallet_liability_idr: number; posted_month: number; revenue_month_idr: number; pending_charges: number; topups_awaiting: number; refunds_awaiting: number;
};
const STATES: [string, string][] = [["TRIAL", "Trial"], ["ACTIVE", "Aktif"], ["RESTRICTED", "Charge tertunda"], ["SUSPENDED", "Ditangguhkan"], ["TERMINATED", "Diakhiri"], ["PROVISIONING", "Provisioning"], ["PENDING_EMAIL", "Menunggu email"]];

export default function PlatformOverviewPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {void apiFetch<Overview>("/platform/overview").then((r) => (r.ok ? setData(r.data) : setError(problemMessage(r.error))));}, []);
  if (error) return <ErrorState message={error} />;
  if (!data) return <LoadingState />;
  const cards: [string, string, string, string?][] = [
    ["Pendapatan SaaS bulan ini", formatIdr(data.revenue_month_idr), `${data.posted_month} biaya layanan terpotong, dikurangi refund disetujui`],
    ["Saldo wallet seluruh travel", formatIdr(data.wallet_liability_idr), "Dana prabayar (kewajiban), bukan pendapatan"],
    ["Top-up menunggu settlement", String(data.topups_awaiting), "Verifikasi dana masuk", "/platform/billing"],
    ["Refund menunggu keputusan", String(data.refunds_awaiting), "Persetujuan billing", "/platform/billing"],
    ["Biaya layanan tertunda", String(data.pending_charges), "Menunggu saldo travel"],
    ["Trial berakhir ≤ 7 hari", String(data.trials_ending_7d), "Peluang konversi", "/platform/trial"],
    ["Tiket dukungan aktif", String(data.open_tickets), "Belum selesai", "/platform/dukungan"],
    ["Pengakhiran menunggu", String(data.pending_terminations), "Perlu persetujuan admin kedua", "/platform/tenant?state=SUSPENDED"],
  ];
  return <div>
    <h1 className="text-2xl font-bold">Ringkasan platform</h1>
    <p className="mt-1 text-sm text-muted">Angka agregat lintas travel per {new Date(data.as_of).toLocaleString("id-ID", {dateStyle: "long", timeStyle: "short"})}. Konsol tidak menampilkan data jamaah.</p>
    <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map(([label, value, hint, href]) => {
        const body = <><p className="text-sm text-muted">{label}</p><p className="mt-2 text-2xl font-semibold">{value}</p><p className="mt-1 text-xs text-muted">{hint}</p></>;
        return href ? <Link key={label} href={href} className="card p-5 transition-colors hover:border-primary">{body}</Link> : <section key={label} className="card p-5">{body}</section>;
      })}
    </div>
    <section className="card mt-6 p-6"><h2 className="font-semibold">Travel per status</h2>
      <ul className="mt-4 grid gap-3 sm:grid-cols-3 xl:grid-cols-7">{STATES.map(([state, label]) => <li key={state}>
        <Link href={`/platform/tenant?state=${state}`} className="block border border-border p-3 hover:border-primary"><span className="text-xs text-muted">{label}</span><span className="mt-1 block text-xl font-semibold">{data.tenants_by_state[state] ?? 0}</span></Link>
      </li>)}</ul>
    </section>
  </div>;
}
