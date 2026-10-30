"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Btn,
  EmptyState,
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
  type Agent,
  type Booking,
  type Departure,
  type Paginated,
  type Pilgrim,
  type RoomType,
  type TravelPackage,
} from "@/lib/api";
import { ROOM_LABELS } from "@/lib/rooms";
import { changedFields, focusForm, formErrors as apiFormErrors } from "@/lib/forms";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";
import { FloatingNotice, focusError, focusRecord } from "@/components/workspace/FloatingNotice";

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

type Adjustment = {discount: string; extra: string; note: string};
const NO_ADJUSTMENT: Adjustment = {discount: "", extra: "", note: ""};
const rupiah = (value: string) => Number(value.replace(/\D/g, "")) || 0;
const snapshotNumber = (snapshot: Record<string, unknown>, key: string) => Number(snapshot[key] ?? 0) || 0;
/** Harga bersih peserta = paket − diskon + biaya tambahan (sama dengan server). */
const netPrice = (snapshot: Record<string, unknown>) => snapshotNumber(snapshot, "unit_price_idr") - snapshotNumber(snapshot, "discount_idr") + snapshotNumber(snapshot, "extra_idr") + snapshotNumber(snapshot, "addons_idr");
const CATEGORY_LABEL: Record<string, string> = {CHILD_NO_BED: "Anak tanpa kasur", INFANT: "Bayi"};
const adjustmentFrom = (snapshot: Record<string, unknown>): Adjustment => ({
  discount: snapshot.discount_idr ? String(snapshot.discount_idr) : "", extra: snapshot.extra_idr ? String(snapshot.extra_idr) : "", note: String(snapshot.adjustment_note ?? ""),
});
const adjustmentPayload = (value: Adjustment) => ({discount_idr: rupiah(value.discount), extra_idr: rupiah(value.extra), note: value.note.trim()});

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
  const [page, setPage] = useState(1);
  const [pageInfo, setPageInfo] = useState<{count: number; next: string | null; previous: string | null}>({count: 0, next: null, previous: null});
  const [departures, setDepartures] = useState<Departure[]>([]);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [noAccess, setNoAccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  // Kode booking yang bentrok (jamaah sudah punya booking aktif): digulir setelah daftar memuatnya.
  const pendingFocus = useRef<string | null>(null);

  // form tambah booking (UI-07)
  const [departureId, setDepartureId] = useState("");
  const [notes, setNotes] = useState("");
  const [pilgrimQuery, setPilgrimQuery] = useState("");
  const [pilgrimResults, setPilgrimResults] = useState<Pilgrim[]>([]);
  const [picked, setPicked] = useState<Pick<Pilgrim, "id" | "name" | "code">[]>([]);
  const [roomTypes, setRoomTypes] = useState<Record<string, RoomType>>({});
  const [formErrors, setFormErrors] = useState<Record<string, string | null>>({});
  const [busy, setBusy] = useState(false);
  const [payerName, setPayerName] = useState("");
  const [agentId, setAgentId] = useState("");
  const [branchId, setBranchId] = useState<string | null>(null);  // null = cabang default staf
  const [branches, setBranches] = useState<{id: string; code: string; name: string}[]>([]);
  const [branchScope, setBranchScope] = useState<"ALL" | "OWN">("ALL");
  const [adjustments, setAdjustments] = useState<Record<string, Adjustment>>({});
  const [categories, setCategories] = useState<Record<string, string>>({});
  const [addonChoices, setAddonChoices] = useState<Record<string, string[]>>({});
  const [packageInfo, setPackageInfo] = useState<TravelPackage | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentEdit, setAgentEdit] = useState<{bookingId: string; agent: string; reason: string} | null>(null);
  const canAgents = can("agents.read");
  const canDiscount = can("bookings.discount");

  // Paginasi server (S19): 50 booking per halaman; filter status & cari di server.
  const load = useCallback((q: string, status = statusFilter, pageNo = page) => {
    const params = new URLSearchParams({page: String(pageNo)});
    if (q.trim()) params.set("q", q.trim());
    if (status) params.set("status", status);
    apiFetch<Paginated<Booking>>(`/bookings?${params}`).then((result) => {
      if (result.ok) {setRows(result.data.results); setPageInfo({count: result.data.count, next: result.data.next, previous: result.data.previous});}
      else if (result.error.status === 403) setNoAccess(true);
      else setError(problemMessage(result.error));
    });
  }, [statusFilter, page]);

  useEffect(() => {
    load(query);
  }, [load, query]);

  useEffect(() => {
    const row = rows?.find((booking) => booking.code === pendingFocus.current);
    if (!row) return;
    pendingFocus.current = null;
    focusRecord(row.id, "danger");
  }, [rows]);

  /** Tampilkan booking yang bentrok: gulir ke barisnya, atau cari dulu bila tidak ada di daftar (filter/halaman lain). */
  function showConflict(code: string) {
    const row = rows?.find((booking) => booking.code === code);
    if (row) { focusRecord(row.id, "danger"); return; }
    pendingFocus.current = code;
    setStatusFilter(""); setPage(1); setQuery(code);
  }

  useEffect(() => {
    // Keberangkatan OPEN saja yang menerima pendaftaran (MOD-06) — bila gagal
    // (mis. tanpa departures.read) form menampilkan petunjuk, server otoritas.
    apiFetch<{ results: Departure[] }>("/departures?status=OPEN").then((result) => {
      if (!result.ok) return;
      setDepartures(result.data.results);
      // Dari CRM Leads: ?departure= (keberangkatan diminati) dan ?pilgrim= (jamaah hasil konversi).
      const params = new URLSearchParams(window.location.search);
      const status = params.get("status");  // drill-down dari Ringkasan
      if (status && status in STATUS_LABEL) setStatusFilter(status);
      const q = params.get("q");  // tautan dari daftar tunggu / ringkasan
      if (q) setQuery(q);
      const wanted = params.get("departure");
      if (wanted && result.data.results.some((dep) => dep.id === wanted)) setDepartureId(wanted);
    });
    const pilgrimId = new URLSearchParams(window.location.search).get("pilgrim");
    if (pilgrimId) apiFetch<Pilgrim>(`/pilgrims/${pilgrimId}`).then((result) => {
      if (result.ok) setPicked((prev) => (prev.some((p) => p.id === result.data.id) ? prev : [...prev, {id: result.data.id, name: result.data.name, code: result.data.code}]));
    });
  }, []);

  const canBranches = can("branches.read");
  useEffect(() => {
    if (!canBranches) return;
    void apiFetch<{scope: "ALL" | "OWN"; branches: {id: string; code: string; name: string}[]}>("/branches/mine").then((result) => {if (result.ok) {setBranches(result.data.branches); setBranchScope(result.data.scope);}});
  }, [canBranches]);

  const selectedPackageId = departures.find((dep) => dep.id === departureId)?.package_id ?? "";
  useEffect(() => {
    if (!selectedPackageId) return;
    let cancelled = false;
    void apiFetch<TravelPackage>(`/packages/${selectedPackageId}`).then((result) => {if (!cancelled && result.ok) setPackageInfo(result.data);});
    return () => {cancelled = true;};
  }, [selectedPackageId]);

  useEffect(() => {
    if (!canAgents) return;
    void apiFetch<{results: Agent[]}>("/agents?active=1&page=1&page_size=100").then((result) => {if (result.ok) setAgents(result.data.results);});
  }, [canAgents]);

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
    focusRecord(booking.id);
    setMessage(`${booking.code}: status → ${STATUS_LABEL[target] ?? target}.`);
    load(query);
  }

  async function saveAgent(booking: Booking) {
    if (!agentEdit) return;
    setBusyId(booking.id); setError(null); setMessage(null);
    const result = await apiFetch(`/bookings/${booking.id}/agent`, {method: "POST", body: JSON.stringify({agent: agentEdit.agent || null, reason: agentEdit.reason.trim()})});
    setBusyId(null);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setAgentEdit(null);
    focusRecord(booking.id);
    setMessage(`${booking.code}: agen diperbarui; komisi agen sebelumnya dibatalkan dan dihitung ulang untuk agen baru.`);
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
    const adjusted = picked.filter((p) => adjustments[p.id] && (rupiah(adjustments[p.id].discount) || rupiah(adjustments[p.id].extra) || editing?.participants.some((row) => row.pilgrim_id === p.id && (row.pricing_snapshot.discount_idr || row.pricing_snapshot.extra_idr))));
    const values = {
        departure: departureId,
        participants: picked.map((p) => p.id),
        room_types: Object.fromEntries(picked.filter((p) => roomTypes[p.id]).map((p) => [p.id, roomTypes[p.id]])),
        notes: notes.trim(),
        payer_name: payerName.trim(),
        agent: agentId || null,
        price_categories: Object.fromEntries(picked.filter((p) => categories[p.id] && categories[p.id] !== "ADULT").map((p) => [p.id, categories[p.id]])),
        addons: Object.fromEntries(picked.filter((p) => addonChoices[p.id]?.length).map((p) => [p.id, addonChoices[p.id]])),
        ...(branchId !== null ? {branch: branchId || null} : {}),
        adjustments: Object.fromEntries(adjusted.map((p) => [p.id, adjustmentPayload(adjustments[p.id])])),
      };
    const original = editing ? {departure:editing.departure_id, notes:editing.notes, payer_name:editing.payer_name, agent:editing.agent?.id ?? null, branch:editing.branch?.id ?? null,
      participants:editing.participants.map((p) => p.pilgrim_id),
      room_types:Object.fromEntries(editing.participants.filter((p) => p.pricing_snapshot.room_type).map((p) => [p.pilgrim_id, p.pricing_snapshot.room_type])),
      price_categories:Object.fromEntries(editing.participants.filter((p) => p.pricing_snapshot.price_category && p.pricing_snapshot.price_category !== "ADULT").map((p) => [p.pilgrim_id, p.pricing_snapshot.price_category])),
      addons:Object.fromEntries(editing.participants.filter((p) => Array.isArray(p.pricing_snapshot.addons) && (p.pricing_snapshot.addons as unknown[]).length).map((p) => [p.pilgrim_id, (p.pricing_snapshot.addons as {code: string}[]).map((a) => a.code)])),
      adjustments:Object.fromEntries(editing.participants.filter((p) => p.pricing_snapshot.discount_idr || p.pricing_snapshot.extra_idr).map((p) => [p.pilgrim_id, adjustmentPayload(adjustmentFrom(p.pricing_snapshot))]))} : {};
    const result = await apiFetch<Booking>(editing ? `/bookings/${editing.id}` : "/bookings", {
      method: editing ? "PATCH" : "POST",
      body: JSON.stringify(editing ? changedFields(values, original) : values),
    });
    setBusy(false);
    if (!result.ok) {
      setFormErrors(apiFormErrors(result.error));
      const conflict = result.error.field_errors?.conflicting_bookings?.[0];
      if (conflict) showConflict(conflict); else focusError();
      return;
    }
    focusRecord(result.data.id);
    setMessage(editing ? `Booking ${result.data.code} diperbarui.` : `Booking ${result.data.code} dibuat (draf) untuk ${result.data.participant_count} peserta. Reservasi kursi setelah data sesuai.`);
    resetForm(); load(query);
  }

  function resetForm() {
    setEditing(null); setDepartureId(""); setNotes(""); setPicked([]); setRoomTypes({}); setPayerName(""); setAgentId(""); setAdjustments({}); setBranchId(null); setCategories({}); setAddonChoices({});
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
    resetForm(); setEditing(booking); setDepartureId(booking.departure_id); setNotes(booking.notes); setPayerName(booking.payer_name); setAgentId(booking.agent?.id ?? ""); setBranchId(booking.branch?.id ?? "");
    setCategories(Object.fromEntries(booking.participants.map((p) => [p.pilgrim_id, String(p.pricing_snapshot.price_category ?? "ADULT")])));
    setAddonChoices(Object.fromEntries(booking.participants.map((p) => [p.pilgrim_id, ((p.pricing_snapshot.addons as {code: string}[] | undefined) ?? []).map((a) => a.code)])));
    setAdjustments(Object.fromEntries(booking.participants.filter((p) => p.pricing_snapshot.discount_idr || p.pricing_snapshot.extra_idr).map((p) => [p.pilgrim_id, adjustmentFrom(p.pricing_snapshot)])));
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

  const visible = rows;
  const searchable = pilgrimResults.filter((p) => !picked.some((s) => s.id === p.id)).slice(0, 8);
  const selectedDeparture = departures.find((dep) => dep.id === departureId);
  const roomChoices = selectedDeparture?.room_prices ?? [];
  const pkg = packageInfo && packageInfo.id === selectedDeparture?.package_id ? packageInfo : null;
  const categoryPrice = (id: string) => categories[id] === "CHILD_NO_BED" ? pkg?.child_no_bed_price_idr ?? 0 : categories[id] === "INFANT" ? pkg?.infant_price_idr ?? 0 : null;
  const addonTotal = (id: string) => (addonChoices[id] ?? []).reduce((sum, code) => sum + (pkg?.addons?.find((a) => a.code === code)?.price_idr ?? 0), 0);
  const estimatedTotal = picked.reduce((total, person) => total + (categoryPrice(person.id) ?? existingPrice(person.id, roomTypes[person.id] ?? "") ?? roomChoices.find((room) => room.room_type === roomTypes[person.id])?.price_idr ?? selectedDeparture?.package_price_idr ?? 0)
    - rupiah(adjustments[person.id]?.discount ?? "") + rupiah(adjustments[person.id]?.extra ?? "") + addonTotal(person.id), 0);
  const hasVariants = Boolean(pkg && (pkg.child_no_bed_price_idr != null || pkg.infant_price_idr != null));
  const setAdjustment = (id: string, patch: Partial<Adjustment>) => setAdjustments((prev) => ({...prev, [id]: {...(prev[id] ?? NO_ADJUSTMENT), ...patch}}));

  return (
    <div className="workspace-page">
      <RevealText as="h1" variant="title" className="text-2xl font-bold">Booking</RevealText>
      <p className="mt-1 text-sm text-muted">
        Pendaftaran jamaah ke keberangkatan. Booking dimulai sebagai draf; klik
        “Reservasi kursi” untuk menahan kursi, dan pembatalan melepasnya kembali.
        Harga dikunci saat booking dibuat, sehingga perubahan harga paket tidak
        memengaruhinya. Invoice terbit otomatis saat kursi direservasi.
      </p>

      <FloatingNotice message={message} onDismiss={() => setMessage(null)} />
      <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />

      <div className="workspace-columns mt-6">
        <section className="card p-6">
          <h2 className="font-semibold">Daftar booking</h2>
          <FormField
            label="Cari"
            htmlFor="booking-search"
            hint="Kode booking atau nama/jamaah."
            className="mt-4"
            value={query}
            onChange={(event) => {setPage(1); setQuery(event.target.value);}}
            placeholder="BK-… / Budi"
          />
          <FormSelect
            label="Status"
            htmlFor="booking-status"
            className="mt-2"
            value={statusFilter}
            onChange={(event) => {setPage(1); setStatusFilter(event.target.value);}}
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
                <li key={booking.id} data-record={booking.id} className="py-4 text-sm">
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
                    <div className="min-w-0 sm:flex-1">
                      <p className="flex flex-wrap items-center gap-2 font-semibold">
                        {booking.code}
                        <StatusBadge tone={STATUS_TONE[booking.status] ?? "neutral"}>
                          {STATUS_LABEL[booking.status] ?? booking.status}
                        </StatusBadge>
                      </p>
                      <p className="text-xs text-muted">
                        {booking.package_name} · {booking.departure_code} · {formatDate(booking.departure_start_at)}
                      </p>
                      {booking.agent || booking.payer_name || booking.branch ? <p className="text-xs text-muted">
                        {[booking.branch ? `Cabang ${booking.branch.code}` : "", booking.agent ? `Agen ${booking.agent.name}` : "", booking.payer_name ? `Pembayar ${booking.payer_name}` : ""].filter(Boolean).join(" · ")}
                      </p> : null}
                    </div>
                    <p className="text-xs text-muted sm:shrink-0 sm:text-right">
                      <strong className="text-sm text-foreground">{formatIdr(booking.total_amount)}</strong>
                      <br />
                      {booking.participant_count} peserta · {booking.available_seats} kursi tersisa
                    </p>
                  </div>
                  <ul className="mt-2 flex flex-wrap gap-1.5">
                    {booking.participants.map((p) => (
                      <li
                        key={p.id} data-record={p.id}
                        className="inline-flex items-center gap-1 border border-border/60 px-1.5 py-0.5 text-[0.7rem]"
                      >
                        {p.pilgrim_name}
                        <span className="text-muted">
                          · {CATEGORY_LABEL[String(p.pricing_snapshot.price_category)] ?? ROOM_LABELS[p.pricing_snapshot.room_type as RoomType] ?? "Standar"} · {formatIdr(netPrice(p.pricing_snapshot))}
                          {p.pricing_snapshot.discount_idr ? ` (diskon ${formatIdr(snapshotNumber(p.pricing_snapshot, "discount_idr"))})` : ""}
                          {p.pricing_snapshot.extra_idr ? ` (+${formatIdr(snapshotNumber(p.pricing_snapshot, "extra_idr"))})` : ""} · {PARTICIPANT_LABEL[p.participant_status] ?? p.participant_status}
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
                    {canAgents && booking.status !== "DRAFT" && CANCELABLE.includes(booking.status) && agentEdit?.bookingId !== booking.id ? (
                      <Btn variant="tint" size="xs" onClick={() => setAgentEdit({bookingId: booking.id, agent: booking.agent?.id ?? "", reason: ""})}>{booking.agent ? "Ganti agen" : "Tetapkan agen"}</Btn>
                    ) : null}
                    {booking.deletable ? <Btn variant="danger" size="xs" disabled={busy || editing?.id === booking.id} onClick={() => void removeBooking(booking)}>Hapus draf</Btn> : null}
                    {CANCELABLE.includes(booking.status) && booking.status !== "DRAFT" ? (
                      <Btn variant="danger" size="xs" disabled={busyId === booking.id} onClick={() => cancel(booking)}>
                        Batalkan
                      </Btn>
                    ) : null}
                  </div> : null}
                  {agentEdit?.bookingId === booking.id ? <div className="mt-3 border border-border/60 p-3">
                    <FormSelect label="Agen" htmlFor={`agent-${booking.id}`} value={agentEdit.agent} onChange={(event) => setAgentEdit({...agentEdit, agent: event.target.value})}>
                      <option value="">Tanpa agen (penjualan langsung)</option>
                      {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name} ({agent.code})</option>)}
                    </FormSelect>
                    <FormField label="Alasan perubahan" htmlFor={`agent-reason-${booking.id}`} maxLength={240} value={agentEdit.reason} onChange={(event) => setAgentEdit({...agentEdit, reason: event.target.value})} hint="Tercatat di histori agen booking." />
                    <div className="flex flex-wrap gap-2">
                      <Btn size="xs" disabled={busyId === booking.id || !agentEdit.reason.trim()} onClick={() => void saveAgent(booking)}>Simpan agen</Btn>
                      <Btn size="xs" variant="tint" onClick={() => setAgentEdit(null)}>Batal</Btn>
                    </div>
                  </div> : null}
                </li>
              ))}
            </ul>
          )}
          {pageInfo.previous || pageInfo.next ? (
            <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
              <Btn size="xs" variant="solid" disabled={!pageInfo.previous} onClick={() => setPage((value) => value - 1)}>Sebelumnya</Btn>
              <span>Halaman {page} · {pageInfo.count} booking</span>
              <Btn size="xs" variant="solid" disabled={!pageInfo.next} onClick={() => setPage((value) => value + 1)}>Berikutnya</Btn>
            </div>
          ) : null}
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
                  <li key={p.id} data-record={p.id}>
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
                    key={p.id} data-record={p.id}
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
                {hasVariants ? picked.map((person) => <FormSelect key={`cat-${person.id}`} label={`Kategori harga ${person.name}`} htmlFor={`category-${person.id}`} value={categories[person.id] ?? "ADULT"} onChange={(event) => setCategories((prev) => ({...prev, [person.id]: event.target.value}))}>
                  <option value="ADULT">Dewasa / anak dengan kasur (harga kamar)</option>
                  {pkg?.child_no_bed_price_idr != null ? <option value="CHILD_NO_BED">Anak tanpa kasur · {formatIdr(pkg.child_no_bed_price_idr)}</option> : null}
                  {pkg?.infant_price_idr != null ? <option value="INFANT">Bayi · {formatIdr(pkg.infant_price_idr)}</option> : null}
                </FormSelect>) : null}
                {roomChoices.length > 0 || Object.keys(roomTypes).length > 0 ? picked.filter((person) => (categories[person.id] ?? "ADULT") === "ADULT").map((person) => (
                  <FormSelect key={person.id} label={`Kamar ${person.name}`} htmlFor={`room-${person.id}`} value={roomTypes[person.id] ?? ""} required={existingPrice(person.id, "") === undefined} onChange={(event) => setRoomTypes((prev) => ({...prev, [person.id]: event.target.value as RoomType}))}>
                    <option value="">{existingPrice(person.id, "") !== undefined ? "Pertahankan harga standar booking" : "— pilih kamar —"}</option>
                    {roomTypes[person.id] && !roomChoices.some((room) => room.room_type === roomTypes[person.id]) ? <option value={roomTypes[person.id]}>{ROOM_LABELS[roomTypes[person.id]]} · harga booking {formatIdr(existingPrice(person.id, roomTypes[person.id]) ?? 0)}</option> : null}
                    {roomChoices.map((room) => <option key={room.room_type} value={room.room_type}>{ROOM_LABELS[room.room_type]} · {formatIdr(existingPrice(person.id, room.room_type) ?? room.price_idr)} / jamaah</option>)}
                  </FormSelect>
                )) : null}
                {pkg?.addons?.length ? <fieldset className="mb-4">
                  <legend className="text-sm font-medium">Layanan tambahan</legend>
                  {picked.map((person) => <div key={`addon-${person.id}`} className="mt-2 text-sm">
                    <p className="text-xs text-muted">{person.name}</p>
                    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">{pkg.addons!.map((addon) => <label key={addon.code} className="flex items-center gap-1.5">
                      <input type="checkbox" checked={(addonChoices[person.id] ?? []).includes(addon.code)} onChange={(event) => setAddonChoices((prev) => {
                        const current = prev[person.id] ?? [];
                        return {...prev, [person.id]: event.target.checked ? [...current, addon.code] : current.filter((code) => code !== addon.code)};
                      })} />
                      {addon.name} <span className="text-xs text-muted">{formatIdr(addon.price_idr)}</span>
                    </label>)}</div>
                  </div>)}
                </fieldset> : null}
                <details className="mb-4" open={Object.keys(adjustments).length > 0}>
                  <summary className="cursor-pointer text-sm font-medium">Diskon &amp; biaya tambahan</summary>
                  <p className="mt-2 text-xs text-muted">{canDiscount ? "Isi per jamaah bila ada potongan harga atau layanan tambahan; alasan wajib dan tercetak di invoice." : "Biaya tambahan dapat diisi; diskon memerlukan izin Owner/Admin."}</p>
                  {picked.map((person) => <div key={person.id} className="mt-4 border-t border-border/60 pt-4">
                    <p className="text-sm font-medium">{person.name}</p>
                    {canDiscount ? <FormField label="Diskon (Rp)" htmlFor={`discount-${person.id}`} inputMode="numeric" value={adjustments[person.id]?.discount ?? ""} onChange={(event) => setAdjustment(person.id, {discount: event.target.value})}
                      hint={rupiah(adjustments[person.id]?.discount ?? "") ? formatIdr(rupiah(adjustments[person.id]?.discount ?? "")) : undefined} /> : null}
                    <FormField label="Biaya tambahan (Rp)" htmlFor={`extra-${person.id}`} inputMode="numeric" value={adjustments[person.id]?.extra ?? ""} onChange={(event) => setAdjustment(person.id, {extra: event.target.value})}
                      hint={rupiah(adjustments[person.id]?.extra ?? "") ? formatIdr(rupiah(adjustments[person.id]?.extra ?? "")) : "Mis. upgrade hotel, kursi khusus."} />
                    <FormField label="Alasan" htmlFor={`adjustment-note-${person.id}`} maxLength={200} value={adjustments[person.id]?.note ?? ""} onChange={(event) => setAdjustment(person.id, {note: event.target.value})} />
                  </div>)}
                </details>
                <p className="text-sm font-semibold">Perkiraan total: {formatIdr(estimatedTotal)}</p>
              </div>
            ) : null}

            <FormField label="Nama pembayar (opsional)" htmlFor="booking-payer" maxLength={160} value={payerName} onChange={(event) => setPayerName(event.target.value)}
              hint="Tercetak sebagai pelanggan di invoice. Kosongkan untuk memakai nama peserta pertama." />
            {branches.length > 0 ? <FormSelect label="Cabang" htmlFor="booking-branch" value={branchId ?? "__default"} onChange={(event) => setBranchId(event.target.value === "__default" ? null : event.target.value)} hint="Cabang yang mencatat penjualan; dipakai pada laporan per cabang.">
              {!editing ? <option value="__default">Cabang default saya</option> : null}
              {branchScope === "ALL" ? <option value="">Tanpa cabang</option> : null}
              {branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.code} · {branch.name}</option>)}
            </FormSelect> : null}
            {canAgents ? <FormSelect label="Agen (opsional)" htmlFor="booking-agent" value={agentId} onChange={(event) => setAgentId(event.target.value)} hint="Agen yang mendapat kredit penjualan dan komisi.">
              <option value="">Tanpa agen (penjualan langsung)</option>
              {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name} ({agent.code})</option>)}
            </FormSelect> : null}
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
