"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/workspace/ui";
import { MonthlyBars } from "@/components/workspace/MonthlyBars";
import { apiFetch } from "@/lib/api";
import { formatDate, formatIdr } from "@/lib/format";

type Summary = {
  as_of: string;
  operations: null | {
    pilgrims: number | null; new_bookings_month: number; new_pax_month: number; sales_estimate_month_idr: number;
    bookings_by_status: {status: string; label: string; count: number}[]; available_seats: number; open_departures: number; waitlist: number;
  };
  finance: null | {
    open_invoices: number; receivable_idr: number; overdue_invoices: number; overdue_idr: number; due_soon_invoices: number; due_soon_idr: number;
    payments_month_idr: number | null; pending_verification: number | null;
  };
  reminders: {kind: string; tone: "warning" | "danger" | "success"; text: string; href: string}[];
  upcoming: null | {id: string; code: string; package_name: string; start_at: string; status: string; capacity: number; taken: number; available: number}[];
  chart: null | {month: string; label: string; bookings: number; sales_idr: number; payments_idr: number | null}[];
};

type Tile = {label: string; value: string; note?: string; href: string};

/** MOD-02: KPI operasional & keuangan, pengingat, keberangkatan terdekat, grafik 12 bulan — setiap angka dapat ditelusuri. */
export function DashboardKpis() {
  const [data, setData] = useState<Summary | null>(null);
  useEffect(() => {
    void apiFetch<Summary>("/dashboard/summary").then((result) => {if (result.ok) setData(result.data);});
  }, []);
  if (!data || (!data.operations && !data.finance)) return null;
  const ops = data.operations, fin = data.finance;
  const tiles: Tile[] = [];
  if (ops) {
    if (ops.pilgrims !== null) tiles.push({label: "Jamaah terdaftar", value: ops.pilgrims.toLocaleString("id-ID"), href: "/dashboard/jamaah"});
    tiles.push({label: "Booking baru bulan ini", value: ops.new_bookings_month.toLocaleString("id-ID"), note: `${ops.new_pax_month} jamaah`, href: "/dashboard/booking"});
    tiles.push({label: "Estimasi penjualan bulan ini", value: formatIdr(ops.sales_estimate_month_idr), note: "Harga bersih booking aktif", href: "/dashboard/laporan"});
    tiles.push({label: "Kursi tersedia", value: ops.available_seats.toLocaleString("id-ID"), note: `${ops.open_departures} keberangkatan dibuka${ops.waitlist ? ` · ${ops.waitlist} daftar tunggu` : ""}`, href: "/dashboard/keberangkatan"});
  }
  if (fin) {
    tiles.push({label: "Tagihan belum lunas", value: formatIdr(fin.receivable_idr), note: `${fin.open_invoices} invoice${fin.overdue_invoices ? ` · ${fin.overdue_invoices} lewat jatuh tempo` : ""}`, href: "/dashboard/invoice"});
    if (fin.payments_month_idr !== null) tiles.push({label: "Pembayaran masuk bulan ini", value: formatIdr(fin.payments_month_idr), note: fin.pending_verification ? `${fin.pending_verification} menunggu verifikasi` : "Terverifikasi", href: "/dashboard/pembayaran"});
  }
  const chart = data.chart ?? [];
  return <div className="space-y-6">
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="Indikator utama">
      {tiles.map((tile) => <Link key={tile.label} href={tile.href} className="card block p-4 transition-colors hover:border-primary">
        <p className="text-xs text-muted">{tile.label}</p>
        <p className="mt-1 text-xl font-semibold tabular-nums">{tile.value}</p>
        {tile.note ? <p className="mt-0.5 text-xs text-muted">{tile.note}</p> : null}
      </Link>)}
    </section>
    <div className="workspace-columns">
      <section className="card min-w-0 p-6">
        <h2 className="font-semibold">Perlu ditindaklanjuti</h2>
        {data.reminders.length === 0 ? <p className="mt-3 text-sm text-muted">Tidak ada pengingat saat ini.</p> :
          <ul className="mt-3 space-y-2 text-sm">{data.reminders.map((item) => <li key={item.text} className="flex items-start gap-2">
            <StatusBadge tone={item.tone}>{item.tone === "danger" ? "Segera" : item.tone === "success" ? "Siap" : "Perhatian"}</StatusBadge>
            <Link href={item.href} className="text-primary hover:underline">{item.text}</Link>
          </li>)}</ul>}
        {ops ? <>
          <h3 className="mt-6 text-sm font-semibold">Booking per status</h3>
          <ul className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">{ops.bookings_by_status.map((row) =>
            <li key={row.status}><Link href={`/dashboard/booking?status=${row.status}`} className="flex justify-between gap-2 hover:text-primary"><span className="text-muted">{row.label}</span><span className="tabular-nums font-medium">{row.count}</span></Link></li>)}</ul>
        </> : null}
      </section>
      {data.upcoming ? <section className="card min-w-0 p-6">
        <h2 className="font-semibold">Keberangkatan terdekat</h2>
        {data.upcoming.length === 0 ? <p className="mt-3 text-sm text-muted">Belum ada jadwal mendatang.</p> :
          <ul className="mt-3 divide-y divide-border text-sm">{data.upcoming.map((dep) => {
            const fill = dep.capacity ? Math.round((dep.taken / dep.capacity) * 100) : 0;
            return <li key={dep.id} className="py-3">
              <div className="flex flex-wrap justify-between gap-2"><span className="font-medium">{dep.code} · {dep.package_name}</span><span className="text-xs text-muted">{formatDate(dep.start_at)}</span></div>
              <div className="mt-2 h-1.5 w-full bg-primary/15" role="meter" aria-valuemin={0} aria-valuemax={dep.capacity} aria-valuenow={dep.taken} aria-label={`Kursi terisi ${dep.code}`}>
                <div className={`h-full ${fill >= 90 ? "bg-warning" : "bg-primary"}`} style={{width: `${fill}%`}} />
              </div>
              <p className="mt-1 text-xs text-muted">{dep.taken}/{dep.capacity} kursi terisi · sisa {dep.available}</p>
            </li>;
          })}</ul>}
      </section> : null}
    </div>
    {chart.length ? <section className="card grid gap-8 p-6 lg:grid-cols-3">
      <MonthlyBars title="Booking per bulan" unit="count" format={(v) => `${v.toLocaleString("id-ID")} booking`} points={chart.map((m) => ({label: m.label, value: m.bookings}))} />
      <MonthlyBars title="Penjualan net per bulan" unit="idr" format={formatIdr} points={chart.map((m) => ({label: m.label, value: m.sales_idr}))} />
      {chart[0].payments_idr !== null ? <MonthlyBars title="Pembayaran masuk per bulan" unit="idr" format={formatIdr} points={chart.map((m) => ({label: m.label, value: m.payments_idr ?? 0}))} /> : null}
    </section> : null}
  </div>;
}
