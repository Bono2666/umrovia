"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Btn,
  EmptyState,
  ErrorState,
  FormField,
  FormSelect,
  FormTextarea,
  LoadingState,
  StatusBadge,
} from "@/components/workspace/ui";
import { formatDate, formatIdr } from "@/lib/format";
import {
  apiFetch,
  problemMessage,
  type Booking,
  type Departure,
  type Pilgrim,
  type RoomType,
} from "@/lib/api";
import { ROOM_LABELS } from "@/lib/rooms";
import { changedFields, focusForm, formErrors as apiFormErrors } from "@/lib/forms";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";

/**
 * Booking end-to-end (S09, UI-07; MOD-07; Spec §5.2/§6.2/§8.3): daftar booking
 * dengan peserta & snapshot harga, form tambah (pilih keberangkatan OPEN +
 * pemilih jamaah multi), dan tombol transisi mengikuti kontrak MOD-07
 * (DRAFT → RESERVED → CONFIRMED → DOCUMENT_PROCESS → READY_TO_DEPART →
 * DEPARTED → COMPLETED; CANCELED dengan alasan wajib; EXPIRED terkontrol).
 * Reservasi kursi (DRAFT → RESERVED) atomik di server — kursi terakhir bisa
 * diperebutkan (UAT-02).
 */
const STATUS_LABEL: Record<string, string> = {
  DRAFT: "Draf",
  RESERVED: "Direservasi",
  CONFIRMED: "Terkonfirmasi",
  DOCUMENT_PROCESS: "Proses dokumen",
  READY_TO_DEPART: "Siap berangkat",
  DEPARTED: "Sudah berangkat",
  COMPLETED: "Selesai",
  CANCELED: "Dibatalkan",
  EXPIRED: "Kedaluwarsa",
};

const STATUS_TONE: Record<string, "neutral" | "success" | "warning" | "danger"> = {
  DRAFT: "neutral",
  RESERVED: "warning",
  CONFIRMED: "success",
  DOCUMENT_PROCESS: "warning",
  READY_TO_DEPART: "success",
  DEPARTED: "success",
  COMPLETED: "neutral",
  CANCELED: "danger",
  EXPIRED: "danger",
};

const PARTICIPANT_LABEL: Record<string, string> = {
  DRAFT: "Draf",
  REGISTERED: "Terdaftar",
  AWAITING_DP: "Menunggu DP",
  DP_VERIFIED_PENDING_CHARGE: "DP terverifikasi",
  CONFIRMED: "Terkonfirmasi",
  READY: "Siap",
  DEPARTED: "Berangkat",
  COMPLETED: "Selesai",
  CANCELED: "Batal",
  REVIEW_REQUIRED: "Perlu review",
};

/** Transisi sah MOD-07 — tombol per status header. */
const NEXT_ACTIONS: Record<string, { target: string; label: string }[]> = {
  DRAFT: [{ target: "RESERVED", label: "Reservasi kursi" }],
  RESERVED: [{ target: "CONFIRMED", label: "Konfirmasi" }],
  CONFIRMED: [{ target: "DOCUMENT_PROCESS", label: "Proses dokumen" }],
  DOCUMENT_PROCESS: [{ target: "READY_TO_DEPART", label: "Siap berangkat" }],
  READY_TO_DEPART: [{ target: "DEPARTED", label: "Berangkat" }],
  DEPARTED: [{ target: "COMPLETED", label: "Tandai selesai" }],
};

const CANCELABLE = ["DRAFT", "RESERVED", "CONFIRMED", "DOCUMENT_PROCESS", "READY_TO_DEPART"];
const EXPIRABLE = ["DRAFT", "RESERVED"];

const CONFIRMED_LIKE = ["CONFIRMED", "READY", "DEPARTED", "COMPLETED"];
const activeParticipants = (booking: Booking) => booking.participants.filter((p) => p.participant_status !== "CANCELED");
const confirmedCount = (booking: Booking) => activeParticipants(booking).filter((p) => CONFIRMED_LIKE.includes(p.participant_status)).length;
/** Server mewajibkan DP (dan biaya layanan produksi) tiap peserta sebelum konfirmasi. */
const readyToConfirm = (booking: Booking) => activeParticipants(booking).length > 0 && confirmedCount(booking) === activeParticipants(booking).length;

function confirmHint(booking: Booking) {
  const waitingFee = activeParticipants(booking).filter((p) => p.participant_status === "DP_VERIFIED_PENDING_CHARGE").length;
  const waitingDp = activeParticipants(booking).length - confirmedCount(booking) - waitingFee;
  if (waitingDp > 0) return `Konfirmasi setelah DP semua peserta terverifikasi (${confirmedCount(booking) + waitingFee}/${activeParticipants(booking).length} sudah DP).`;
  return <>DP lengkap; {waitingFee} peserta menunggu saldo <Link className="text-primary underline" href="/dashboard/wallet">SaaS Wallet</Link>.</>;
}

export default function BookingPage() {
  const {can, canEditEnvironment, writableEnvironments} = useWorkspacePermissions();
  const [editing, setEditing] = useState<Booking | null>(null);
  const [rows, setRows] = useState<Booking[] | null>(null);
  const [departures, setDepartures] = useState<Departure[]>([]);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [noAccess, setNoAccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  // form tambah booking (UI-07)
  const [departureId, setDepartureId] = useState("");
  const [notes, setNotes] = useState("");
  const [pilgrimQuery, setPilgrimQuery] = useState("");
  const [pilgrimResults, setPilgrimResults] = useState<Pilgrim[]>([]);
  const [picked, setPicked] = useState<Pick<Pilgrim, "id" | "name" | "code">[]>([]);
  const [roomTypes, setRoomTypes] = useState<Record<string, RoomType>>({});
  const [formErrors, setFormErrors] = useState<Record<string, string | null>>({});
  const [busy, setBusy] = useState(false);

  const load = useCallback((q: string) => {
    const suffix = q.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
    apiFetch<{ results: Booking[] }>(`/bookings${suffix}`).then((result) => {
      if (result.ok) setRows(result.data.results);
      else if (result.error.status === 403) setNoAccess(true);
      else setError(problemMessage(result.error));
    });
  }, []);

  useEffect(() => {
    load(query);
  }, [load, query]);

  useEffect(() => {
    // Keberangkatan OPEN saja yang menerima pendaftaran (MOD-06) — bila gagal
    // (mis. tanpa departures.read) form menampilkan petunjuk, server otoritas.
    apiFetch<{ results: Departure[] }>("/departures?status=OPEN").then((result) => {
      if (result.ok) setDepartures(result.data.results);
    });
  }, []);

  useEffect(() => {
    const q = pilgrimQuery.trim();
    if (!q) return;
    let cancelled = false;
    apiFetch<{ results: Pilgrim[] }>(`/pilgrims?q=${encodeURIComponent(q)}`).then((result) => {
      if (!cancelled && result.ok) setPilgrimResults(result.data.results);
    });
    return () => {cancelled = true;};
  }, [pilgrimQuery]);

  async function transition(booking: Booking, target: string, reason?: string) {
    setBusyId(booking.id);
    setError(null);
    const result = await apiFetch<Booking>(`/bookings/${booking.id}/transition`, {
      method: "POST",
      body: JSON.stringify(reason ? { target, reason } : { target }),
    });
    setBusyId(null);
    if (!result.ok) {
      setError(problemMessage(result.error));
      return;
    }
    setMessage(`${booking.code}: status → ${STATUS_LABEL[target] ?? target}.`);
    load(query);
  }

  function cancel(booking: Booking) {
    const reason = window.prompt(`Alasan pembatalan ${booking.code} (wajib diisi):`);
    if (reason === null) return;
    if (!reason.trim()) {
      setError("Alasan pembatalan wajib diisi.");
      return;
    }
    transition(booking, "CANCELED", reason.trim());
  }

  function expire(booking: Booking) {
    if (!window.confirm(`Tandai ${booking.code} kedaluwarsa? Kursi yang ditahan akan dilepas.`)) {
      return;
    }
    transition(booking, "EXPIRED");
  }

  function addPilgrim(pilgrim: Pilgrim) {
    setPicked((prev) => (prev.some((p) => p.id === pilgrim.id) ? prev : [...prev, pilgrim]));
    setPilgrimQuery("");
    setPilgrimResults([]);
    const first = departures.find((dep) => dep.id === departureId)?.room_prices?.[0]?.room_type;
    if (first) setRoomTypes((prev) => ({...prev, [pilgrim.id]: first}));
  }

  async function onCreate(event: React.FormEvent) {
    event.preventDefault();
    const errors: Record<string, string | null> = {
      departure: departureId ? null : "Pilih keberangkatan.",
      participants: picked.length > 0 ? null : "Tambahkan minimal satu jamaah.",
    };
    setFormErrors(errors);
    if (Object.values(errors).some(Boolean)) return;

    setBusy(true);
    setMessage(null);
    setError(null);
    const values = {
        departure: departureId,
        participants: picked.map((p) => p.id),
        room_types: Object.fromEntries(picked.filter((p) => roomTypes[p.id]).map((p) => [p.id, roomTypes[p.id]])),
        notes: notes.trim(),
      };
    const original = editing ? {departure:editing.departure_id, notes:editing.notes,
      participants:editing.participants.map((p) => p.pilgrim_id),
      room_types:Object.fromEntries(editing.participants.filter((p) => p.pricing_snapshot.room_type).map((p) => [p.pilgrim_id, p.pricing_snapshot.room_type]))} : {};
    const result = await apiFetch<Booking>(editing ? `/bookings/${editing.id}` : "/bookings", {
      method: editing ? "PATCH" : "POST",
      body: JSON.stringify(editing ? changedFields(values, original) : values),
    });
    setBusy(false);
    if (!result.ok) {
      setFormErrors(apiFormErrors(result.error));
      return;
    }
    setMessage(editing ? `Booking ${result.data.code} diperbarui.` : `Booking ${result.data.code} dibuat (draf) untuk ${result.data.participant_count} peserta. Reservasi kursi setelah data sesuai.`);
    resetForm(); load(query);
  }

  function resetForm() {
    setEditing(null); setDepartureId(""); setNotes(""); setPicked([]); setRoomTypes({});
    setPilgrimQuery(""); setPilgrimResults([]); setFormErrors({});
  }

  async function removeBooking(booking: Booking) {
    if (!window.confirm(`Hapus booking draf ${booking.code}? Kuota trial yang terpakai tidak dikembalikan. Data yang belum pernah dipakai dihapus permanen.`)) return;
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch(`/bookings/${booking.id}`, { method: "DELETE" });
    setBusy(false);
    if (!result.ok) { setError(problemMessage(result.error)); return; }
    setMessage(`Booking ${booking.code} dihapus.`);
    load(query);
  }

  async function editBooking(row: Booking) {
    setBusy(true); setError(null);
    const result = await apiFetch<Booking>(`/bookings/${row.id}`);
    if (!result.ok) {setBusy(false); setError(problemMessage(result.error)); return;}
    const booking = result.data;
    if (booking.status !== "DRAFT") {setBusy(false); setError("Hanya booking draf yang dapat dikoreksi. Perbarui daftar untuk melihat status terbaru."); load(query); return;}
    resetForm(); setEditing(booking); setDepartureId(booking.departure_id); setNotes(booking.notes);
    setPicked(booking.participants.map((p) => ({id:p.pilgrim_id, name:p.pilgrim_name, code:p.pilgrim_code})));
    setRoomTypes(Object.fromEntries(booking.participants.filter((p) => p.pricing_snapshot.room_type).map((p) => [p.pilgrim_id, p.pricing_snapshot.room_type as RoomType])));
    if (!departures.some((dep) => dep.id === booking.departure_id)) {
      const departure = await apiFetch<Departure>(`/departures/${booking.departure_id}`);
      if (departure.ok) setDepartures((previous) => [...previous.filter((d) => d.id !== departure.data.id), departure.data]);
    }
    setBusy(false); setMessage(null); focusForm("booking-form");
  }

  function existingPrice(pilgrimId: string, room: string) {
    const participant = editing?.participants.find((p) => p.pilgrim_id === pilgrimId);
    return editing?.departure_id === departureId && participant?.pricing_snapshot.room_type === room
      ? Number(participant.pricing_snapshot.unit_price_idr) : undefined;
  }

  if (noAccess) {
    return (
      <div className="workspace-page">
        <RevealText as="h1" variant="title" className="text-2xl font-bold">Booking</RevealText>
        <div className="mt-6">
          <EmptyState
            title="Halaman ini khusus staf penjualan"
            description="Peran Anda belum diberi akses melihat booking. Hubungi Owner travel."
          />
        </div>
      </div>
    );
  }

  const visible =
    rows && statusFilter ? rows.filter((row) => row.status === statusFilter) : rows;
  const searchable = pilgrimResults.filter((p) => !picked.some((s) => s.id === p.id)).slice(0, 8);
  const selectedDeparture = departures.find((dep) => dep.id === departureId);
  const roomChoices = selectedDeparture?.room_prices ?? [];
  const estimatedTotal = picked.reduce((total, person) => total + (existingPrice(person.id, roomTypes[person.id] ?? "") ?? roomChoices.find((room) => room.room_type === roomTypes[person.id])?.price_idr ?? selectedDeparture?.package_price_idr ?? 0), 0);

  return (
    <div className="workspace-page">
      <RevealText as="h1" variant="title" className="text-2xl font-bold">Booking</RevealText>
      <p className="mt-1 text-sm text-muted">
        Pendaftaran jamaah ke keberangkatan. Booking dimulai sebagai draf; klik
        “Reservasi kursi” untuk menahan kursi, dan pembatalan melepasnya kembali.
        Harga dikunci saat booking dibuat, sehingga perubahan harga paket tidak
        memengaruhinya.
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
          <h2 className="font-semibold">Daftar booking</h2>
          <FormField
            label="Cari"
            htmlFor="booking-search"
            hint="Kode booking atau nama/jamaah."
            className="mt-4"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="BK-… / Budi"
          />
          <FormSelect
            label="Status"
            htmlFor="booking-status"
            className="mt-2"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="">Semua status</option>
            {Object.entries(STATUS_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </FormSelect>
          {visible === null ? (
            <div className="mt-4">
              <LoadingState label="Memuat booking…" />
            </div>
          ) : visible.length === 0 ? (
            <div className="mt-4">
              <EmptyState
                title="Belum ada booking"
                description="Buat booking pertama melalui formulir di samping."
              />
            </div>
          ) : (
            <ul className="mt-4 divide-y divide-border/60">
              {visible.map((booking) => (
                <li key={booking.id} className="py-4 text-sm">
                  <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-2 font-semibold">
                        {booking.code}
                        <StatusBadge tone={STATUS_TONE[booking.status] ?? "neutral"}>
                          {STATUS_LABEL[booking.status] ?? booking.status}
                        </StatusBadge>
                      </p>
                      <p className="text-xs text-muted">
                        {booking.package_name} · {booking.departure_code} · {formatDate(booking.departure_start_at)}
                      </p>
                    </div>
                    <p className="text-xs text-muted sm:text-right">
                      <strong className="text-sm text-foreground">{formatIdr(booking.total_amount)}</strong>
                      <br />
                      {booking.participant_count} peserta · {booking.available_seats} kursi tersisa
                    </p>
                  </div>
                  <ul className="mt-2 flex flex-wrap gap-1.5">
                    {booking.participants.map((p) => (
                      <li
                        key={p.id}
                        className="inline-flex items-center gap-1 border border-border/60 px-1.5 py-0.5 text-[0.7rem]"
                      >
                        {p.pilgrim_name}
                        <span className="text-muted">
                          · {ROOM_LABELS[p.pricing_snapshot.room_type as RoomType] ?? "Standar"} · {formatIdr(Number(p.pricing_snapshot.unit_price_idr ?? 0))} · {PARTICIPANT_LABEL[p.participant_status] ?? p.participant_status}
                        </span>
                      </li>
                    ))}
                  </ul>
                  {booking.status === "CANCELED" && booking.cancel_reason ? (
                    <p className="mt-1 text-xs text-danger">
                      Alasan: {booking.cancel_reason}
                      {booking.canceled_by_name ? ` — ${booking.canceled_by_name}` : ""}
                    </p>
                  ) : null}
                  {can("bookings.create") && canEditEnvironment(booking.environment) ? <div className="mt-3 flex flex-wrap items-center gap-1.5">
                    {(NEXT_ACTIONS[booking.status] ?? []).map((action) => action.target === "CONFIRMED" && !readyToConfirm(booking) ? (
                      <span key={action.target} className="text-xs text-muted">{confirmHint(booking)}</span>
                    ) : (
                      <Btn key={action.target} size="xs" disabled={busyId === booking.id} onClick={() => transition(booking, action.target)}>
                        {action.label}
                      </Btn>
                    ))}
                    {booking.status === "DRAFT" ? <Btn variant="tint" size="xs" disabled={busy} onClick={() => editBooking(booking)}>Ubah booking</Btn> : null}
                    {EXPIRABLE.includes(booking.status) && booking.registration_closed ? (
                      <Btn variant="tint" size="xs" disabled={busyId === booking.id} onClick={() => expire(booking)}>
                        Tandai kedaluwarsa
                      </Btn>
                    ) : null}
                    {booking.deletable ? <Btn variant="danger" size="xs" disabled={busy || editing?.id === booking.id} onClick={() => void removeBooking(booking)}>Hapus draf</Btn> : null}
                    {CANCELABLE.includes(booking.status) && booking.status !== "DRAFT" ? (
                      <Btn variant="danger" size="xs" disabled={busyId === booking.id} onClick={() => cancel(booking)}>
                        Batalkan
                      </Btn>
                    ) : null}
                  </div> : null}
                </li>
              ))}
            </ul>
          )}
        </section>

        {can("bookings.create") && writableEnvironments.length > 0 ? <section className="card p-6">
          <h2 className="font-semibold">{editing ? `Ubah booking ${editing.code}` : "Tambah booking"}</h2>
          <p className="mt-2 text-sm text-muted">Peserta, kamar dan keberangkatan dapat dikoreksi selama draf. Harga peserta yang tetap dipertahankan; perubahan kamar atau keberangkatan memakai tarif saat ini.</p>
          <form id="booking-form" onSubmit={onCreate} className="mt-6 scroll-mt-24"><fieldset className="min-w-0" disabled={busy}>
            <FormSelect
              label="Keberangkatan"
              htmlFor="booking-departure"
              hint="Hanya keberangkatan yang pendaftarannya dibuka."
              error={formErrors.departure}
              value={departureId}
              onChange={(event) => {
                setDepartureId(event.target.value);
                const first = departures.find((dep) => dep.id === event.target.value)?.room_prices?.[0]?.room_type;
                setRoomTypes(first ? Object.fromEntries(picked.map((p) => [p.id, first])) : {});
              }}
            >
              <option value="">— pilih keberangkatan —</option>
              {departures.map((dep) => (
                <option key={dep.id} value={dep.id}>
                  {dep.code} — {dep.package_name} · {formatDate(dep.start_at)} ·{" "}
                  {dep.available_seats} kursi
                </option>
              ))}
            </FormSelect>
            {departures.length === 0 ? (
              <p className="form-control__hint">
                Belum ada keberangkatan OPEN — buka menu Keberangkatan dan ubah status ke “Pendaftaran
                dibuka” dulu.
              </p>
            ) : null}

            <FormField
              label="Cari jamaah"
              htmlFor="booking-pilgrim"
              hint="Ketik nama atau kode jamaah, lalu klik untuk menambahkan."
              value={pilgrimQuery}
              onChange={(event) => {
                setPilgrimQuery(event.target.value);
                if (!event.target.value.trim()) setPilgrimResults([]);
              }}
              placeholder="Budi / JM-…"
            />
            {searchable.length > 0 ? (
              <ul className="mb-2 divide-y divide-border/60 border border-border/60">
                {searchable.map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between px-2 py-1.5 text-left text-xs hover:bg-tint/40"
                      onClick={() => addPilgrim(p)}
                    >
                      <span>
                        {p.name} <span className="text-muted">· {p.code}</span>
                      </span>
                      <span className="text-muted">tambah +</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
            {picked.length > 0 ? (
              <ul className="mb-2 flex flex-wrap gap-1.5">
                {picked.map((p) => (
                  <li
                    key={p.id}
                    className="inline-flex items-center gap-1 border border-success/40 bg-success/10 px-1.5 py-0.5 text-[0.7rem]"
                  >
                    {p.name}
                    <button
                      type="button"
                      className="text-muted hover:text-danger"
                      aria-label={`Hapus ${p.name}`}
                      onClick={() => setPicked((prev) => prev.filter((s) => s.id !== p.id))}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
            {formErrors.participants ? (
              <p className="error-message" role="alert">
                {formErrors.participants}
              </p>
            ) : null}

            {picked.length > 0 ? (
              <div className="my-6 border-t border-border pt-6">
                {roomChoices.length > 0 || Object.keys(roomTypes).length > 0 ? picked.map((person) => (
                  <FormSelect key={person.id} label={`Kamar ${person.name}`} htmlFor={`room-${person.id}`} value={roomTypes[person.id] ?? ""} required={existingPrice(person.id, "") === undefined} onChange={(event) => setRoomTypes((prev) => ({...prev, [person.id]: event.target.value as RoomType}))}>
                    <option value="">{existingPrice(person.id, "") !== undefined ? "Pertahankan harga standar booking" : "— pilih kamar —"}</option>
                    {roomTypes[person.id] && !roomChoices.some((room) => room.room_type === roomTypes[person.id]) ? <option value={roomTypes[person.id]}>{ROOM_LABELS[roomTypes[person.id]]} · harga booking {formatIdr(existingPrice(person.id, roomTypes[person.id]) ?? 0)}</option> : null}
                    {roomChoices.map((room) => <option key={room.room_type} value={room.room_type}>{ROOM_LABELS[room.room_type]} · {formatIdr(existingPrice(person.id, room.room_type) ?? room.price_idr)} / jamaah</option>)}
                  </FormSelect>
                )) : null}
                <p className="text-sm font-semibold">Perkiraan total: {formatIdr(estimatedTotal)}</p>
              </div>
            ) : null}

            <FormTextarea
              label="Catatan"
              htmlFor="booking-notes"
              rows={3}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Catatan pendaftaran (opsional)"
            />
            {formErrors.form ? (
              <p className="error-message" role="alert">
                {formErrors.form}
              </p>
            ) : null}
            <div className="form-submit">
              <Btn type="submit" disabled={busy}>
                {busy ? "Menyimpan…" : editing ? "Simpan perubahan" : "Buat booking"}
              </Btn>
              {editing ? <Btn type="button" variant="tint" className="ml-2" onClick={resetForm}>Batal ubah</Btn> : null}
            </div>
          </fieldset></form>
        </section> : null}
      </div>
    </div>
  );
}
