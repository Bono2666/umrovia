"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Btn, EmptyState, FormField, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type Departure, type Pilgrim, type RoomType, type WaitlistEntry } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { ROOM_LABELS } from "@/lib/rooms";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";
import { FloatingNotice, focusRecord } from "@/components/workspace/FloatingNotice";

/**
 * MOD-06 daftar tunggu: hanya untuk keberangkatan yang kursinya habis. Tidak
 * menahan kursi; saat kursi kosong, entri diproses urut antrean menjadi booking draf.
 */
export default function WaitlistPage() {
  const {can, loading, writableEnvironments} = useWorkspacePermissions();
  const canWrite = can("bookings.create") && writableEnvironments.length > 0;
  const [rows, setRows] = useState<WaitlistEntry[] | null>(null);
  const [departures, setDepartures] = useState<Departure[]>([]);
  const [filters, setFilters] = useState({departure: "", status: "WAITING"});
  const [form, setForm] = useState({departure: "", room_type: "", notes: ""});
  const [pilgrimQuery, setPilgrimQuery] = useState("");
  const [pilgrimResults, setPilgrimResults] = useState<Pilgrim[]>([]);
  const [pilgrim, setPilgrim] = useState<Pilgrim | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(() => {
    const query = new URLSearchParams({status: filters.status, ...(filters.departure ? {departure: filters.departure} : {})}).toString();
    return apiFetch<{results: WaitlistEntry[]}>(`/waitlist?${query}`).then((result) => {
      if (result.ok) setRows(result.data.results); else setError(problemMessage(result.error));
    });
  }, [filters]);
  useEffect(() => {if (!loading && can("bookings.read")) void load();}, [loading, can, load]);
  useEffect(() => {
    if (loading) return;
    void apiFetch<{results: Departure[]}>("/departures?status=OPEN").then((result) => {if (result.ok) setDepartures(result.data.results);});
  }, [loading]);
  useEffect(() => {
    const q = pilgrimQuery.trim();
    if (!q) return;
    let cancelled = false;
    void apiFetch<{results: Pilgrim[]}>(`/pilgrims?q=${encodeURIComponent(q)}`).then((result) => {if (!cancelled && result.ok) setPilgrimResults(result.data.results.slice(0, 6));});
    return () => {cancelled = true;};
  }, [pilgrimQuery]);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    if (!pilgrim) return;
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch<WaitlistEntry>("/waitlist", {method: "POST", body: JSON.stringify({...form, pilgrim: pilgrim.id})});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    focusRecord(result.data.id);
    setMessage(`${result.data.pilgrim.name} masuk daftar tunggu ${result.data.departure.code} di urutan ${result.data.position}.`);
    setPilgrim(null); setForm({...form, notes: ""}); void load();
  }

  async function book(entry: WaitlistEntry) {
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch<WaitlistEntry>(`/waitlist/${entry.id}/book`, {method: "POST", body: "{}"});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    focusRecord(entry.id);
    setMessage(`Booking draf ${result.data.booking?.code} dibuat untuk ${entry.pilgrim.name}. Buka Booking untuk mereservasi kursi.`);
    void load();
  }

  async function cancel(entry: WaitlistEntry) {
    const reason = window.prompt(`Keluarkan ${entry.pilgrim.name} dari daftar tunggu ${entry.departure.code}? Tulis alasan.`);
    if (reason === null) return;
    setError(null); setMessage(null);
    const result = await apiFetch<WaitlistEntry>(`/waitlist/${entry.id}/cancel`, {method: "POST", body: JSON.stringify({reason})});
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setMessage(`${entry.pilgrim.name} dikeluarkan dari daftar tunggu.`); void load();
  }

  if (loading) return <LoadingState />;
  if (!can("bookings.read")) return <EmptyState title="Anda tidak memiliki akses booking" />;
  const full = departures.filter((dep) => dep.available_seats === 0);
  const selected = departures.find((dep) => dep.id === form.departure);

  return <div className="workspace-page">
    <RevealText as="h1" variant="title" className="text-2xl font-bold">Daftar tunggu</RevealText>
    <p className="mt-1 max-w-3xl text-sm text-muted">Calon jamaah untuk keberangkatan yang kursinya penuh. Daftar tunggu tidak menahan kursi; saat ada pembatalan, proses dari urutan teratas menjadi booking draf lalu reservasi kursi di halaman Booking.</p>
    <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />
    <FloatingNotice message={message} onDismiss={() => setMessage(null)} />
    <div className="workspace-columns mt-6">
      <section className="card min-w-0 p-6">
        <div className="expense-form grid items-end gap-x-4 gap-y-8 sm:grid-cols-2">
          <FormSelect label="Keberangkatan" htmlFor="waitlist-filter-departure" value={filters.departure} onChange={(event) => setFilters({...filters, departure: event.target.value})}>
            <option value="">Semua keberangkatan</option>{departures.map((dep) => <option key={dep.id} value={dep.id}>{dep.code} · {dep.package_name}</option>)}
          </FormSelect>
          <FormSelect label="Status" htmlFor="waitlist-filter-status" value={filters.status} onChange={(event) => setFilters({...filters, status: event.target.value})}>
            <option value="WAITING">Menunggu kursi</option><option value="BOOKED">Sudah dibuatkan booking</option><option value="CANCELED">Dibatalkan</option><option value="">Semua</option>
          </FormSelect>
        </div>
        {rows === null ? <LoadingState /> : rows.length === 0 ? <div className="mt-4"><EmptyState title="Daftar tunggu kosong" description="Calon jamaah untuk keberangkatan penuh akan tampil di sini." /></div> :
          <ul className="mt-4 divide-y divide-border">{rows.map((entry) => <li key={entry.id} data-record={entry.id} className="py-4 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2">
                  {entry.position ? <span className="font-semibold tabular-nums">#{entry.position}</span> : null}
                  <span className="font-medium">{entry.pilgrim.name}</span><span className="text-xs text-muted">{entry.pilgrim.code}</span>
                  <StatusBadge tone={entry.status === "WAITING" ? "warning" : entry.status === "BOOKED" ? "success" : "neutral"}>{entry.status_label}</StatusBadge>
                </p>
                <p className="mt-1 text-xs text-muted">{entry.departure.code} · {entry.departure.package_name} · {formatDate(entry.departure.start_at)}{entry.room_type ? ` · ${ROOM_LABELS[entry.room_type as RoomType] ?? entry.room_type}` : ""} · masuk {formatDate(entry.created_at)}</p>
                {entry.notes ? <p className="mt-1 text-xs text-muted">{entry.notes}</p> : null}
                {entry.booking ? <p className="mt-1 text-xs"><Link className="text-primary underline" href={`/dashboard/booking?q=${entry.booking.code}`}>Booking {entry.booking.code}</Link></p> : null}
                {entry.cancel_reason ? <p className="mt-1 text-xs text-muted">Alasan: {entry.cancel_reason}</p> : null}
              </div>
              {canWrite && entry.status === "WAITING" ? <div className="flex shrink-0 items-center gap-3">
                {entry.position !== null && entry.departure.available_seats >= entry.position
                  ? <Btn size="xs" disabled={busy} onClick={() => void book(entry)}>Buat booking</Btn>
                  : <span className="text-xs text-muted">{entry.departure.available_seats} kursi kosong</span>}
                <Btn size="xs" variant="link" onClick={() => void cancel(entry)}>Keluarkan</Btn>
              </div> : null}
            </div>
          </li>)}</ul>}
      </section>
      {canWrite ? <section className="card min-w-0 p-6"><h2 className="font-semibold">Tambah ke daftar tunggu</h2>
        {full.length === 0 ? <p className="mt-3 text-sm text-muted">Belum ada keberangkatan yang penuh. Selama kursi masih tersedia, buat booking langsung di halaman Booking.</p> :
          <form className="mt-5" onSubmit={add}>
            <FormSelect label="Keberangkatan penuh" htmlFor="waitlist-departure" value={form.departure} onChange={(event) => setForm({...form, departure: event.target.value, room_type: ""})} required>
              <option value="">— pilih keberangkatan —</option>{full.map((dep) => <option key={dep.id} value={dep.id}>{dep.code} · {dep.package_name} · {formatDate(dep.start_at)}</option>)}
            </FormSelect>
            {pilgrim ? <p className="mb-4 text-sm">Jamaah: <strong>{pilgrim.name}</strong> <Btn size="xs" variant="link" type="button" onClick={() => setPilgrim(null)}>Ganti</Btn></p> : <>
              <FormField label="Cari jamaah" htmlFor="waitlist-pilgrim" value={pilgrimQuery} onChange={(event) => {setPilgrimQuery(event.target.value); if (!event.target.value.trim()) setPilgrimResults([]);}} placeholder="Nama atau kode jamaah" />
              {pilgrimResults.length > 0 ? <ul className="mb-4 divide-y divide-border/60 border border-border/60">{pilgrimResults.map((p) => <li key={p.id} data-record={p.id}>
                <button type="button" className="flex w-full justify-between px-2 py-1.5 text-left text-xs hover:bg-tint/40" onClick={() => {setPilgrim(p); setPilgrimQuery(""); setPilgrimResults([]);}}><span>{p.name} <span className="text-muted">· {p.code}</span></span><span className="text-muted">pilih</span></button>
              </li>)}</ul> : null}
            </>}
            {selected?.room_prices?.length ? <FormSelect label="Kamar diminati" htmlFor="waitlist-room" value={form.room_type} onChange={(event) => setForm({...form, room_type: event.target.value})}>
              <option value="">Belum ditentukan</option>{selected.room_prices.map((room) => <option key={room.room_type} value={room.room_type}>{ROOM_LABELS[room.room_type]}</option>)}
            </FormSelect> : null}
            <FormField label="Catatan" htmlFor="waitlist-notes" maxLength={240} value={form.notes} onChange={(event) => setForm({...form, notes: event.target.value})} />
            <Btn type="submit" loading={busy} disabled={!pilgrim || !form.departure}>Tambahkan</Btn>
          </form>}
      </section> : null}
    </div>
  </div>;
}
