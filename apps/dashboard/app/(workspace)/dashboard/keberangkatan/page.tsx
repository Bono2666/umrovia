"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Btn,
  EmptyState,
  ErrorState,
  FormField,
  FormSelect,
  LoadingState,
  StatusBadge,
} from "@/components/workspace/ui";
import { formatDate } from "@/lib/format";
import {
  apiFetch,
  problemMessage,
  type Departure,
  type DepartureStaff,
  type TravelPackage,
} from "@/lib/api";

/**
 * Keberangkatan & kuota (S08, UI-05; MOD-06; Spec §5.2/§6.5/§8.3): daftar
 * dengan gauge kursi (kapasitas − terpakai − terblokir), form tambah dengan
 * pemilih paket, dan tombol transisi status mengikuti kontrak state machine
 * §6.5 (DRAFT → OPEN → READY → DEPARTED → COMPLETED; CANCELED dengan alasan
 * wajib). Kursi dipesan atomik oleh booking (S09) — halaman ini hanya
 * menampilkan dan mengatur kuota/blokir.
 */
const STATUS_LABEL: Record<string, string> = {
  DRAFT: "Draf",
  OPEN: "Pendaftaran dibuka",
  READY: "Siap berangkat",
  DEPARTED: "Sudah berangkat",
  COMPLETED: "Selesai",
  CANCELED: "Dibatalkan",
};

const STATUS_TONE: Record<string, "neutral" | "success" | "warning" | "danger"> = {
  DRAFT: "neutral",
  OPEN: "success",
  READY: "warning",
  DEPARTED: "success",
  COMPLETED: "neutral",
  CANCELED: "danger",
};

/** Transisi sah §6.5 — tombol per status; CANCELED hanya dari DRAFT/OPEN/READY. */
const NEXT_ACTIONS: Record<string, { target: string; label: string }[]> = {
  DRAFT: [{ target: "OPEN", label: "Buka pendaftaran" }],
  OPEN: [{ target: "READY", label: "Siapkan" }],
  READY: [{ target: "DEPARTED", label: "Berangkat" }],
  DEPARTED: [{ target: "COMPLETED", label: "Tandai selesai" }],
};

export default function KeberangkatanPage() {
  const [rows, setRows] = useState<Departure[] | null>(null);
  const [packages, setPackages] = useState<TravelPackage[]>([]);
  const [staff, setStaff] = useState<DepartureStaff[]>([]);
  const [leadStaff, setLeadStaff] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [noAccess, setNoAccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [packageId, setPackageId] = useState("");
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [cityOfOrigin, setCityOfOrigin] = useState("");
  const [route, setRoute] = useState("");
  const [meetingPoint, setMeetingPoint] = useState("");
  const [seatCapacity, setSeatCapacity] = useState("");
  const [seatsBlocked, setSeatsBlocked] = useState("");
  const [deadline, setDeadline] = useState("");
  const [formErrors, setFormErrors] = useState<Record<string, string | null>>({});
  const [busy, setBusy] = useState(false);

  const load = useCallback((q: string) => {
    const suffix = q.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
    apiFetch<{ results: Departure[] }>(`/departures${suffix}`).then((result) => {
      if (result.ok) setRows(result.data.results);
      else if (result.error.status === 403) setNoAccess(true);
      else setError(problemMessage(result.error));
    });
  }, []);

  useEffect(() => {
    load(query);
  }, [load, query]);

  useEffect(() => {
    // Pemilih paket untuk form — bila gagal (mis. tanpa packages.read) biarkan
    // kosong: form menampilkan petunjuk, server tetap otoritas.
    apiFetch<{ results: TravelPackage[] }>("/packages").then((result) => {
      if (result.ok) setPackages(result.data.results);
    });
    apiFetch<{ results: DepartureStaff[] }>("/departures/staff").then((result) => {
      if (result.ok) setStaff(result.data.results);
    });
  }, []);

  async function transition(dep: Departure, target: string, reason?: string, checklistException = false) {
    setBusyId(dep.id);
    setError(null);
    const result = await apiFetch<Departure>(`/departures/${dep.id}/transition`, {
      method: "POST",
      body: JSON.stringify({ target, reason, checklist_exception: checklistException }),
    });
    setBusyId(null);
    if (!result.ok) {
      setError(problemMessage(result.error));
      return;
    }
    setMessage(`${dep.code}: status → ${STATUS_LABEL[target] ?? target}.`);
    load(query);
  }

  function prepareWithException(dep: Departure) {
    const reason = window.prompt(`Alasan pengecualian dokumen wajib untuk ${dep.code} (tercatat dalam riwayat):`);
    if (reason === null) return;
    if (!reason.trim()) {
      setError("Alasan pengecualian dokumen wajib diisi.");
      return;
    }
    transition(dep, "READY", reason.trim(), true);
  }

  function cancel(dep: Departure) {
    const reason = window.prompt(`Alasan pembatalan ${dep.code} (wajib diisi):`);
    if (reason === null) return;
    if (!reason.trim()) {
      setError("Alasan pembatalan wajib diisi.");
      return;
    }
    transition(dep, "CANCELED", reason.trim());
  }

  async function editBlocked(dep: Departure) {
    const input = window.prompt(
      `Kuota blokir ${dep.code} — tersedia ${dep.available_seats} dari ${dep.seat_capacity} (terpakai ${dep.seats_taken}).\nKuota blokir baru:`,
      String(dep.seats_blocked),
    );
    if (input === null) return;
    const value = Number(input);
    if (!Number.isInteger(value) || value < 0) {
      setError("Kuota blokir harus bilangan bulat ≥ 0.");
      return;
    }
    setBusyId(dep.id);
    setError(null);
    const result = await apiFetch<Departure>(`/departures/${dep.id}`, {
      method: "PATCH",
      body: JSON.stringify({ seats_blocked: value }),
    });
    setBusyId(null);
    if (!result.ok) {
      setError(problemMessage(result.error));
      return;
    }
    setMessage(`${dep.code}: kuota blokir → ${value}.`);
    load(query);
  }

  async function onAdd(event: React.FormEvent) {
    event.preventDefault();
    const capacity = Number(seatCapacity);
    const blocked = Number(seatsBlocked || 0);
    const errors: Record<string, string | null> = {
      package: packageId ? null : "Pilih paket.",
      start_at: startAt ? null : "Tanggal keberangkatan wajib diisi.",
      end_at:
        endAt && startAt && new Date(endAt) <= new Date(startAt)
          ? "Kepulangan harus setelah keberangkatan (§10.1)."
          : null,
      city_of_origin: cityOfOrigin.trim() ? null : "Kota asal wajib diisi.",
      seat_capacity:
        Number.isInteger(capacity) && capacity >= 0 && capacity <= 1000
          ? null
          : "Kapasitas 0–1000 kursi.",
      seats_blocked:
        Number.isInteger(blocked) && blocked >= 0 ? null : "Kuota blokir ≥ 0.",
    };
    setFormErrors(errors);
    if (Object.values(errors).some(Boolean)) return;

    setBusy(true);
    setMessage(null);
    setError(null);
    const result = await apiFetch<Departure>("/departures", {
      method: "POST",
      body: JSON.stringify({
        package: packageId,
        start_at: startAt,
        end_at: endAt || null,
        city_of_origin: cityOfOrigin.trim(),
        route: route.trim(),
        meeting_point: meetingPoint.trim(),
        seat_capacity: capacity,
        seats_blocked: blocked,
        registration_deadline: deadline || null,
        lead_staff: leadStaff || null,
      }),
    });
    setBusy(false);
    if (!result.ok) {
      setFormErrors({ form: problemMessage(result.error) });
      return;
    }
    setPackageId("");
    setStartAt("");
    setEndAt("");
    setCityOfOrigin("");
    setRoute("");
    setMeetingPoint("");
    setSeatCapacity("");
    setSeatsBlocked("");
    setDeadline("");
    setLeadStaff("");
    setMessage(
      `Keberangkatan ${result.data.code} dibuat — ${result.data.available_seats} kursi tersedia.`,
    );
    load(query);
  }

  if (noAccess) {
    return (
      <div className="workspace-page">
        <h1 className="text-2xl font-bold">Keberangkatan</h1>
        <div className="mt-6">
          <EmptyState
            title="Halaman ini khusus staf operasional"
            description="Peran Anda tidak memiliki permission departures.read."
          />
        </div>
      </div>
    );
  }

  const visible =
    rows && statusFilter
      ? rows.filter((dep) => dep.status === statusFilter)
      : rows;

  return (
    <div className="workspace-page">
      <h1 className="text-2xl font-bold">Keberangkatan</h1>
      <p className="mt-1 text-sm text-muted">
        Jadwal keberangkatan &amp; kuota kursi (MOD-06). Ketersediaan dihitung
        atomik — kapasitas − terpakai − terblokir (BR-002); status mengikuti
        alur Draf → Pendaftaran dibuka → Siap berangkat → Berangkat → Selesai,
        atau Dibatalkan dengan alasan.
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
          <h2 className="font-semibold">Daftar keberangkatan</h2>
          <FormField
            label="Cari"
            htmlFor="keberangkatan-search"
            hint="Kode, kota asal, atau nama paket."
            className="mt-4"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="DPR-… / Jakarta / Ramadhan"
          />
          <FormSelect
            label="Status"
            htmlFor="keberangkatan-status"
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
              <LoadingState label="Memuat keberangkatan…" />
            </div>
          ) : visible.length === 0 ? (
            <div className="mt-4">
              <EmptyState
                title="Belum ada keberangkatan"
                description="Buat jadwal pertama melalui formulir di samping."
              />
            </div>
          ) : (
            <ul className="mt-4 divide-y divide-border/60">
              {visible.map((dep) => (
                <li key={dep.id} className="py-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="min-w-44">
                      <p className="font-semibold">{dep.package_name}</p>
                      <p className="text-xs text-muted">
                        {dep.code} · {formatDate(dep.start_at)}
                        {dep.city_of_origin ? ` · ${dep.city_of_origin}` : ""}
                        {dep.lead_staff_name ? ` · PIC ${dep.lead_staff_name}` : ""}
                      </p>
                    </div>
                    <StatusBadge tone={STATUS_TONE[dep.status] ?? "neutral"}>
                      {STATUS_LABEL[dep.status] ?? dep.status}
                    </StatusBadge>
                    <span
                      className={`ml-auto text-xs ${
                        dep.available_seats === 0 ? "font-semibold text-danger" : "text-muted"
                      }`}
                    >
                      {dep.available_seats} kursi tersisa · {dep.seats_taken} terpakai ·{" "}
                      {dep.seats_blocked} diblokir / {dep.seat_capacity}
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {(NEXT_ACTIONS[dep.status] ?? []).map((action) => (
                      <Btn
                        key={action.target}
                        variant="tint"
                        size="xs"
                        disabled={busyId === dep.id}
                        onClick={() => transition(dep, action.target)}
                      >
                        {action.label}
                      </Btn>
                    ))}
                    {dep.status === "OPEN" ? (
                      <Btn
                        variant="tint"
                        size="xs"
                        disabled={busyId === dep.id}
                        onClick={() => prepareWithException(dep)}
                      >
                        Siapkan dengan pengecualian
                      </Btn>
                    ) : null}
                    {["DRAFT", "OPEN", "READY"].includes(dep.status) ? (
                      <Btn
                        variant="danger"
                        size="xs"
                        disabled={busyId === dep.id}
                        onClick={() => cancel(dep)}
                      >
                        Batalkan
                      </Btn>
                    ) : null}
                    {["DRAFT", "OPEN", "READY"].includes(dep.status) ? (
                      <Btn
                        variant="tint"
                        size="xs"
                        disabled={busyId === dep.id}
                        onClick={() => editBlocked(dep)}
                      >
                        Ubah blokir
                      </Btn>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card p-6">
          <h2 className="font-semibold">Tambah keberangkatan</h2>
          {/* Workspace controls use compact typography and field spacing. */}
          <form onSubmit={onAdd} className="mt-6">
            <FormSelect
              label="Paket"
              htmlFor="departure-package"
              error={formErrors.package}
              value={packageId}
              onChange={(event) => setPackageId(event.target.value)}
            >
              <option value="">— pilih paket —</option>
              {packages.map((pkg) => (
                <option key={pkg.id} value={pkg.id}>
                  {pkg.code} — {pkg.name}
                </option>
              ))}
            </FormSelect>
            {packages.length === 0 ? (
              <p className="form-control__hint">
                Belum ada paket terlihat — buka menu Paket dan buat katalog dulu.
              </p>
            ) : null}
            <FormSelect
              label="PIC keberangkatan"
              htmlFor="departure-lead-staff"
              value={leadStaff}
              onChange={(event) => setLeadStaff(event.target.value)}
            >
              <option value="">— belum ditentukan —</option>
              {staff.map((member) => <option key={member.id} value={member.id}>{member.name}</option>)}
            </FormSelect>
            <FormField
              label="Keberangkatan"
              htmlFor="departure-start"
              type="datetime-local"
              error={formErrors.start_at}
              value={startAt}
              onChange={(event) => setStartAt(event.target.value)}
              required
            />
            <FormField
              label="Kepulangan"
              htmlFor="departure-end"
              type="datetime-local"
              error={formErrors.end_at}
              value={endAt}
              onChange={(event) => setEndAt(event.target.value)}
            />
            <FormField
              label="Kota asal"
              htmlFor="departure-city"
              error={formErrors.city_of_origin}
              value={cityOfOrigin}
              onChange={(event) => setCityOfOrigin(event.target.value)}
              placeholder="Jakarta"
              required
            />
            <FormField
              label="Maskapai / rute"
              htmlFor="departure-route"
              value={route}
              onChange={(event) => setRoute(event.target.value)}
              placeholder="GA 715 · CGK–JED"
            />
            <FormField
              label="Meeting point"
              htmlFor="departure-meeting"
              value={meetingPoint}
              onChange={(event) => setMeetingPoint(event.target.value)}
              placeholder="Terminal 3 Soekarno-Hatta"
            />
            <FormField
              label="Kapasitas kursi"
              htmlFor="departure-capacity"
              error={formErrors.seat_capacity}
              value={seatCapacity}
              onChange={(event) => setSeatCapacity(event.target.value)}
              inputMode="numeric"
              placeholder="40"
            />
            <FormField
              label="Kuota blokir"
              htmlFor="departure-blocked"
              hint="Kursi ditahan untuk sponsor/agensi — tidak dijual ke publik."
              error={formErrors.seats_blocked}
              value={seatsBlocked}
              onChange={(event) => setSeatsBlocked(event.target.value)}
              inputMode="numeric"
              placeholder="0"
            />
            <FormField
              label="Batas pendaftaran"
              htmlFor="departure-deadline"
              type="date"
              value={deadline}
              onChange={(event) => setDeadline(event.target.value)}
            />
            {formErrors.form ? (
              <p className="error-message" role="alert">
                {formErrors.form}
              </p>
            ) : null}
            <div className="form-submit">
              <Btn type="submit" disabled={busy}>
                {busy ? "Menyimpan…" : "Tambah keberangkatan"}
              </Btn>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
