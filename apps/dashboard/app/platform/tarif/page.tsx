"use client";

import { useCallback, useEffect, useState } from "react";
import { usePlatform } from "@/components/platform/PlatformShell";
import { Btn, FormField, FormTextarea, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage } from "@/lib/api";
import { formatIdr } from "@/lib/format";
import { FloatingNotice } from "@/components/workspace/FloatingNotice";

type Price = {id: string; code: string; unit_price_idr: number; effective_from: string; current: boolean; scheduled: boolean};

export default function PlatformPricingPage() {
  const {can} = usePlatform();
  const [rows, setRows] = useState<Price[] | null>(null);
  const [form, setForm] = useState({code: "", price: "", effective: "", reason: ""});
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => apiFetch<{results: Price[]}>("/platform/pricing").then((r) => (r.ok ? setRows(r.data.results) : setError(problemMessage(r.error)))), []);
  useEffect(() => {void load();}, [load]);

  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null); setMessage(null);
    const r = await apiFetch<{results: Price[]}>("/platform/pricing", {method: "POST", body: JSON.stringify({
      code: form.code.trim().toUpperCase(), unit_price_idr: Number(form.price), effective_from: new Date(form.effective).toISOString(), reason: form.reason,
    })});
    setBusy(false);
    if (!r.ok) {setError(problemMessage(r.error)); return;}
    setRows(r.data.results); setForm({code: "", price: "", effective: "", reason: ""});
    setMessage("Versi tarif dijadwalkan. Biaya yang sudah terpotong tidak berubah.");
  }

  return <div>
    <h1 className="text-2xl font-bold">Tarif SaaS</h1>
    <p className="mt-1 text-sm text-muted">Tarif per booking-jamaah dengan DP terverifikasi. Setiap biaya menyimpan versi tarif saat dibuat; versi baru hanya berlaku ke depan.</p>
    <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />
    <FloatingNotice message={message} onDismiss={() => setMessage(null)} />
    <div className="workspace-columns mt-6">
      <section className="card min-w-0 p-6"><h2 className="font-semibold">Versi tarif</h2>
        {rows === null ? <LoadingState /> : <ul className="mt-3 divide-y divide-border">{rows.map((row) => <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
          <span><span className="font-medium">{row.code}</span><span className="block text-xs text-muted">Berlaku {new Date(row.effective_from).toLocaleString("id-ID", {dateStyle: "long", timeStyle: "short"})}</span></span>
          <span className="flex items-center gap-2"><span className="font-semibold">{formatIdr(row.unit_price_idr)}</span>{row.current ? <StatusBadge tone="success">Berlaku</StatusBadge> : row.scheduled ? <StatusBadge tone="warning">Terjadwal</StatusBadge> : <StatusBadge>Lama</StatusBadge>}</span>
        </li>)}</ul>}
      </section>
      {can("platform.pricing_manage") ? <section className="card min-w-0 p-6"><h2 className="font-semibold">Jadwalkan versi baru</h2>
        <form className="mt-5" onSubmit={submit}>
          <FormField label="Kode versi (mis. STD-2027)" htmlFor="price-code" maxLength={32} value={form.code} onChange={(event) => setForm({...form, code: event.target.value})} required />
          <FormField label="Tarif per jamaah (Rp)" htmlFor="price-amount" inputMode="numeric" value={form.price} onChange={(event) => setForm({...form, price: event.target.value.replace(/\D/g, "")})} required hint={form.price ? formatIdr(Number(form.price)) : undefined} />
          <FormField label="Berlaku mulai" htmlFor="price-effective" type="datetime-local" value={form.effective} onChange={(event) => setForm({...form, effective: event.target.value})} required hint="Paling cepat 1 jam dari sekarang." />
          <FormTextarea label="Alasan & dasar persetujuan" htmlFor="price-reason" rows={3} maxLength={240} value={form.reason} onChange={(event) => setForm({...form, reason: event.target.value})} required />
          <Btn type="submit" loading={busy} disabled={!form.code || !form.price || !form.effective || form.reason.trim().length < 10}>Jadwalkan tarif</Btn>
        </form>
      </section> : null}
    </div>
  </div>;
}
