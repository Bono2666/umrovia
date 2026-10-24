"use client";

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
import { formatDate } from "@/lib/format";
import {
  apiFetch,
  problemMessage,
  type Booking,
  type Departure,
  type Pilgrim,
} from "@/lib/api";

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

function formatIdr(value: number): string {
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 0,
  }).format(value);
}

export default function BookingPage() {
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
  const [picked, setPicked] = useState<Pilgrim[]>([]);
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
    apiFetch<{ results: Pilgrim[] }>(`/pilgrims?q=${encodeURIComponent(q)}`).then((result) => {
      if (result.ok) setPilgrimResults(result.data.results);
    });
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
    const result = await apiFetch<Booking>("/bookings", {
      method: "POST",
      body: JSON.stringify({
        departure: departureId,
        participants: picked.map((p) => p.id),
        notes: notes.trim(),
      }),
    });
    setBusy(false);
    if (!result.ok) {
      setFormErrors({ form: problemMessage(result.error) });
      return;
    }
    setDepartureId("");
    setNotes("");
    setPicked([]);
    setPilgrimQuery("");
    setMessage(
      `Booking ${result.data.code} dibuat (draf) untuk ${result.data.participant_count} peserta — ` +
        "klik “Reservasi kursi” untuk menahan kursi secara atomik.",
    );
    load(query);
  }

  if (noAccess) {
    return (
      <div className="workspace-page">
        <h1 className="text-2xl font-bold">Booking</h1>
        <div className="mt-6">
          <EmptyState
            title="Halaman ini khusus staf penjualan"
            description="Peran Anda tidak memiliki permission bookings.read."
          />
        </div>
      </div>
    );
  }

  const visible =
    rows && statusFilter ? rows.filter((row) => row.status === statusFilter) : rows;
  const searchable = pilgrimResults.filter((p) => !picked.some((s) => s.id === p.id)).slice(0, 8);

  return (
    <div className="workspace-page">
      <h1 className="text-2xl font-bold">Booking</h1>
      <p className="mt-1 text-sm text-muted">
        Pendaftaran jamaah pada keberangkatan (MOD-07, UI-07). Booking lahir sebagai draf;
        “Reservasi kursi” menahan kursi secara atomik (UAT-02), pembatalan melepasnya kembali.
        Harga di-snapshot saat dibuat — perubahan harga paket tidak mengubah booking (UAT-04).
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
                <li key={booking.id} className="py-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="min-w-44">
                      <p className="font-semibold">{booking.code}</p>
                      <p className="text-xs text-muted">
                        {booking.package_name} · {booking.departure_code} ·{" "}
                        {formatDate(booking.departure_start_at)}
                      </p>
                    </div>
                    <StatusBadge tone={STATUS_TONE[booking.status] ?? "neutral"}>
                      {STATUS_LABEL[booking.status] ?? booking.status}
                    </StatusBadge>
                    <span className="ml-auto text-xs text-muted">
                      {booking.participant_count} peserta · {formatIdr(booking.total_amount)} ·{" "}
                      {booking.available_seats} kursi tersisa
                    </span>
                  </div>
                  <ul className="mt-2 flex flex-wrap gap-1.5">
                    {booking.participants.map((p) => (
                      <li
                        key={p.id}
                        className="inline-flex items-center gap-1 border border-border/60 px-1.5 py-0.5 text-[0.7rem]"
                      >
                        {p.pilgrim_name}
                        <span className="text-muted">
                          · {PARTICIPANT_LABEL[p.participant_status] ?? p.participant_status}
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
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {(NEXT_ACTIONS[booking.status] ?? []).map((action) => (
                      <Btn
                        key={action.target}
                        variant="tint"
                        size="xs"
                        disabled={busyId === booking.id}
                        onClick={() => transition(booking, action.target)}
                      >
                        {action.label}
                      </Btn>
                    ))}
                    {CANCELABLE.includes(booking.status) ? (
                      <Btn
                        variant="danger"
                        size="xs"
                        disabled={busyId === booking.id}
                        onClick={() => cancel(booking)}
                      >
                        Batalkan
                      </Btn>
                    ) : null}
                    {EXPIRABLE.includes(booking.status) ? (
                      <Btn
                        variant="tint"
                        size="xs"
                        disabled={busyId === booking.id}
                        onClick={() => expire(booking)}
                      >
                        Kedaluwarsa
                      </Btn>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card p-6">
          <h2 className="font-semibold">Tambah booking</h2>
          <form onSubmit={onCreate} className="mt-6">
            <FormSelect
              label="Keberangkatan"
              htmlFor="booking-departure"
              hint="Hanya keberangkatan dengan pendaftaran dibuka (OPEN)."
              error={formErrors.departure}
              value={departureId}
              onChange={(event) => setDepartureId(event.target.value)}
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
                {busy ? "Menyimpan…" : "Buat booking"}
              </Btn>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
