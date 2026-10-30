"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { LogoutButton } from "@/components/LogoutButton";
import { UmroviaLogo } from "@/components/UmroviaLogo";
import { Btn, EmptyState, ErrorState, FormField, FormSelect, FormTextarea, LoadingState, StatusBadge } from "@/components/workspace/ui";
import {
  API_BASE, apiFetch, apiUpload, downloadFromApi, problemMessage,
  type ChangeRequest, type PortalAccessView, type PortalBooking, type PortalDocumentItem, type PortalNotification, type PortalProfile, type UserPayload,
} from "@/lib/api";
import { formatDate, formatIdr, formatMasked } from "@/lib/format";
import { ROOM_LABELS } from "@/lib/rooms";
import type { RoomType } from "@/lib/api";
import { FloatingNotice } from "@/components/workspace/FloatingNotice";

const STEPS = ["Terdaftar", "Menunggu DP", "DP diterima", "Terkonfirmasi", "Siap berangkat", "Berangkat", "Selesai"];
const DOC_STATUS: Record<string, { label: string; tone: "neutral" | "success" | "warning" | "danger" }> = {
  UPLOADED: { label: "Menunggu review", tone: "warning" },
  UNDER_REVIEW: { label: "Sedang ditinjau", tone: "warning" },
  APPROVED: { label: "Disetujui", tone: "success" },
  REJECTED: { label: "Ditolak", tone: "danger" },
};
const DOC_KINDS: Record<string, string> = { ktp: "KTP", passport: "Paspor", photo: "Foto", kk: "Kartu Keluarga", other: "Dokumen lain" };
const ACCEPT = ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png";

/**
 * Portal jamaah (S14, UI-13): data milik sendiri saja — jadwal, progres,
 * pembayaran, dokumen (unggah/riwayat/unduh bertanda tangan) dan kontak.
 */
export default function PortalPage() {
  const router = useRouter();
  const [me, setMe] = useState<UserPayload | null>(null);
  const [accesses, setAccesses] = useState<PortalAccessView[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiFetch<{ results: PortalAccessView[] }>("/portal/me").then((result) => {
      if (result.ok) setAccesses(result.data.results);
      else setError(problemMessage(result.error));
    });
  }, []);

  useEffect(() => {
    apiFetch<UserPayload>("/me").then((result) => {
      if (!result.ok) {
        router.replace("/login?next=/portal");
        return;
      }
      setMe(result.data);
      load();
    });
  }, [router, load]);

  return (
    <div className="workspace-shell min-h-screen">
      <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3 sm:px-6">
        <span className="flex items-center gap-3"><UmroviaLogo /><span className="border-l border-border pl-3 text-sm font-semibold text-ink">Portal Jamaah</span></span>
        <span className="flex items-center gap-3 text-sm text-muted">
          <span className="hidden truncate sm:inline">{me?.email}</span>
          <LogoutButton onLoggedOut={() => router.push("/login?next=/portal")} />
        </span>
      </header>
      <main className="mx-auto w-full max-w-5xl space-y-8 p-4 sm:p-6">
        {error ? <ErrorState message={error} onRetry={load} /> : null}
        {accesses === null ? (
          error ? null : <LoadingState label="Memuat portal…" />
        ) : accesses.length === 0 ? (
          <div className="card p-8">
            <EmptyState title="Belum ada akses portal" description="Akun ini belum terhubung ke data jamaah. Buka tautan undangan dari travel Anda, atau minta undangan baru." />
            {me?.memberships.some((m) => m.status === "ACTIVE") ? <p className="mt-4 text-center text-sm"><Link className="text-primary underline" href="/dashboard">Buka dashboard travel</Link></p> : null}
          </div>
        ) : (
          <>
            <InboxPanel />
            {accesses.map((access) => <AccessSection key={access.access_id} access={access} onChanged={load} />)}
          </>
        )}
      </main>
    </div>
  );
}

/** Inbox NTF-02: pemberitahuan travel (booking, invoice, pembayaran, dokumen, jadwal). */
function InboxPanel() {
  const [inbox, setInbox] = useState<{ results: PortalNotification[]; unread: number } | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(() => {
    apiFetch<{ results: PortalNotification[]; unread: number }>("/portal/notifications").then((result) => {
      if (result.ok) setInbox(result.data);
    });
  }, []);
  useEffect(() => { load(); }, [load]);

  function markRead(item: PortalNotification) {
    if (item.read_at) return;
    const readAt = new Date().toISOString();
    setInbox((value) => value && { unread: Math.max(value.unread - 1, 0), results: value.results.map((row) => row.id === item.id ? { ...row, read_at: readAt } : row) });
    void apiFetch(`/portal/accesses/${item.access_id}/notifications/${item.id}/read`, { method: "POST" });
  }

  async function readAll() {
    const result = await apiFetch("/portal/notifications/read-all", { method: "POST" });
    if (result.ok) load();
  }

  if (inbox === null || inbox.results.length === 0) return null;
  const items = showAll ? inbox.results : inbox.results.slice(0, 4);
  return (
    <section className="card p-6" aria-labelledby="portal-inbox-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="portal-inbox-title" className="flex items-center gap-2 font-semibold">
          Pemberitahuan
          {inbox.unread ? <StatusBadge tone="warning">{inbox.unread} baru</StatusBadge> : null}
        </h2>
        {inbox.unread ? <Btn size="xs" variant="link" onClick={() => void readAll()}>Tandai semua dibaca</Btn> : null}
      </div>
      <ul className="mt-3 divide-y divide-border">
        {items.map((item) => {
          const expanded = open === item.id;
          return (
            <li key={item.id} className="py-3">
              <button type="button" aria-expanded={expanded} className="flex w-full items-start justify-between gap-3 text-left"
                onClick={() => { setOpen(expanded ? null : item.id); markRead(item); }}>
                <span className="min-w-0">
                  <span className={`block text-sm ${item.read_at ? "" : "font-semibold"}`}>
                    {item.read_at ? null : <span className="mr-2 inline-block h-2 w-2 rounded-full bg-primary align-middle" aria-label="Belum dibaca" />}
                    {item.subject}
                  </span>
                  <span className="mt-0.5 block text-xs text-muted">{new Date(item.created_at).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" })}</span>
                </span>
                <span className="shrink-0 text-xs text-primary">{expanded ? "Tutup" : "Baca"}</span>
              </button>
              {expanded ? <pre className="mt-3 whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-foreground">{item.body}</pre> : null}
            </li>
          );
        })}
      </ul>
      {inbox.results.length > 4 ? <Btn className="mt-2" size="xs" variant="link" onClick={() => setShowAll((value) => !value)}>{showAll ? "Tampilkan lebih sedikit" : `Tampilkan semua (${inbox.results.length})`}</Btn> : null}
    </section>
  );
}

function AccessSection({ access, onChanged }: { access: PortalAccessView; onChanged: () => void }) {
  return (
    <section className="space-y-6">
      <div>
        <p className="text-sm text-muted">{access.travel.name}{access.environment === "demo" ? " · data demo" : ""}</p>
        <h1 className="text-2xl font-bold">Assalamu&apos;alaikum, {access.profile.name}</h1>
        <p className="mt-1 text-sm text-muted">Pantau perjalanan, pembayaran dan dokumen Anda. Pertanyaan seputar perjalanan dapat ditujukan ke {access.travel.name}{access.travel.phone ? ` (${access.travel.phone})` : ""}.</p>
      </div>
      {access.bookings.length === 0 ? (
        <div className="card p-6"><EmptyState title="Belum ada perjalanan" description="Booking Anda akan tampil di sini setelah travel mendaftarkannya." /></div>
      ) : access.bookings.map((booking) => <BookingCard key={booking.booking_id} accessId={access.access_id} booking={booking} />)}
      {access.announcements.length ? <section className="card p-6" aria-labelledby={`ann-${access.access_id}`}>
        <h2 id={`ann-${access.access_id}`} className="font-semibold">Pengumuman dari {access.travel.name}</h2>
        <ul className="mt-3 divide-y divide-border">{access.announcements.map((item) => <li key={item.id} className="py-3">
          <p className="font-medium">{item.title}</p>
          <p className="mt-1 whitespace-pre-line text-sm text-muted">{item.body}</p>
          <p className="mt-1 text-xs text-muted">{item.published_at ? formatDate(item.published_at) : ""}{item.departure ? ` · rombongan ${item.departure.code}` : ""}</p>
        </li>)}</ul>
      </section> : null}
      <div className="workspace-columns">
        <DocumentsPanel accessId={access.access_id} />
        <ProfileCard accessId={access.access_id} profile={access.profile} onSaved={onChanged} />
      </div>
      <IdentityCorrection accessId={access.access_id} requests={access.change_requests} onSent={onChanged} />
    </section>
  );
}

function BookingCard({ accessId, booking }: { accessId: string; booking: PortalBooking }) {
  const canceled = booking.status === "CANCELED" || booking.participant_status === "CANCELED";
  const { departure, payment } = booking;
  const room = ROOM_LABELS[booking.room_type as RoomType];
  return (
    <article className="card p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex flex-wrap items-center gap-2 text-lg font-semibold">
            {departure.package_name}
            {canceled ? <StatusBadge tone="danger">Dibatalkan</StatusBadge> : null}
          </h2>
          <p className="text-sm text-muted">
            {formatDate(departure.start_at)}{departure.end_at ? ` – ${formatDate(departure.end_at)}` : ""} · {departure.city_of_origin}{room ? ` · Kamar ${room}` : ""}
          </p>
          {departure.meeting_point || departure.route ? <p className="mt-1 text-sm text-muted">{[departure.route, departure.meeting_point && `Titik kumpul: ${departure.meeting_point}`].filter(Boolean).join(" · ")}</p> : null}
        </div>
        <span className="text-xs text-muted">Booking {booking.code}</span>
      </div>

      {!canceled && booking.progress !== null ? (
        <ol className="mt-5 grid grid-cols-2 gap-2 text-xs sm:grid-cols-7" aria-label="Progres perjalanan">
          {STEPS.map((label, index) => {
            const done = index < booking.progress!;
            const current = index === booking.progress;
            return (
              <li key={label} aria-current={current ? "step" : undefined} className={`border-t-2 pt-2 ${done ? "border-primary text-foreground" : current ? "border-primary font-semibold text-primary" : "border-border text-muted"}`}>
                {done ? "✓ " : ""}{label}
              </li>
            );
          })}
        </ol>
      ) : null}

      <dl className="mt-6 grid gap-4 text-sm sm:grid-cols-3">
        <div><dt className="text-muted">Tagihan Anda</dt><dd className="mt-1 text-lg font-semibold">{formatIdr(payment.amount_idr)}</dd></div>
        <div><dt className="text-muted">Sudah dibayar</dt><dd className="mt-1 text-lg font-semibold text-success">{formatIdr(payment.paid_idr)}</dd></div>
        <div><dt className="text-muted">Sisa</dt><dd className="mt-1 text-lg font-semibold">{formatIdr(payment.balance_idr)}</dd>{payment.due_at && payment.balance_idr > 0 ? <p className="text-xs text-muted">Jatuh tempo {formatDate(payment.due_at)}</p> : null}</div>
      </dl>
      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
        {payment.invoice_id ? (
          <a className="text-primary underline" href={`${API_BASE}/api/v1/portal/accesses/${accessId}/invoices/${payment.invoice_id}/pdf`}>Unduh invoice {payment.invoice_number}</a>
        ) : payment.group_invoice ? (
          <span className="text-muted">Invoice {payment.invoice_number} berlaku untuk rombongan; minta salinan ke travel.</span>
        ) : (
          <span className="text-muted">Invoice belum diterbitkan.</span>
        )}
      </div>
      {booking.receipts.length ? (
        <ul className="mt-4 divide-y divide-border/60 border-t border-border/60 text-sm">
          {booking.receipts.map((receipt) => (
            <li key={`${receipt.id}-${receipt.received_at}`} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span>{receipt.kind === "DP" ? "DP" : receipt.kind === "INSTALLMENT" ? "Cicilan" : "Pelunasan"} · {formatDate(receipt.received_at)}</span>
              <span className="flex items-center gap-3">
                <strong>{formatIdr(receipt.amount_idr)}</strong>
                {receipt.downloadable && receipt.id ? <a className="text-primary underline" href={`${API_BASE}/api/v1/portal/accesses/${accessId}/receipts/${receipt.id}/pdf`}>Kuitansi</a> : null}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

function DocumentsPanel({ accessId }: { accessId: string }) {
  const [items, setItems] = useState<PortalDocumentItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busyKind, setBusyKind] = useState<string | null>(null);
  const [extraKind, setExtraKind] = useState("passport");
  const input = useRef<HTMLInputElement>(null);
  const target = useRef<string>("");

  const load = useCallback(() => {
    apiFetch<{ results: PortalDocumentItem[] }>(`/portal/accesses/${accessId}/documents`).then((result) => {
      if (result.ok) setItems(result.data.results);
      else setError(problemMessage(result.error));
    });
  }, [accessId]);
  useEffect(() => { load(); }, [load]);

  function choose(kind: string) {
    target.current = kind;
    input.current?.click();
  }

  async function onFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const kind = target.current;
    setBusyKind(kind); setError(null); setMessage(null);
    const form = new FormData();
    form.append("kind", kind);
    form.append("file", file);
    const result = await apiUpload(`/portal/accesses/${accessId}/documents`, form);
    setBusyKind(null);
    if (!result.ok) { setError(problemMessage(result.error)); return; }
    setMessage(`${DOC_KINDS[kind] ?? kind} terunggah dan menunggu review travel.`);
    load();
  }

  async function open(documentId: string) {
    setError(null);
    const result = await apiFetch<{ path: string }>(`/portal/accesses/${accessId}/documents/${documentId}/download-url`, { method: "POST" });
    if (result.ok) downloadFromApi(result.data.path);
    else setError(problemMessage(result.error));
  }

  const listed = new Set(items?.map((item) => item.kind));
  const extraOptions = Object.entries(DOC_KINDS).filter(([kind]) => !listed.has(kind));
  // Jenis yang sudah ada di checklist disembunyikan; pakai opsi pertama yang tersisa.
  const extra = listed.has(extraKind) ? extraOptions[0]?.[0] ?? "" : extraKind;
  return (
    <section className="card min-w-0 p-6">
      <h2 className="font-semibold">Dokumen perjalanan</h2>
      <p className="mt-1 text-sm text-muted">Unggah PDF, JPG atau PNG (maks. 10 MB). Travel akan meninjau setiap dokumen.</p>
      <input ref={input} type="file" accept={ACCEPT} className="hidden" onChange={onFile} aria-label="Pilih berkas dokumen" />
      <FloatingNotice message={message} onDismiss={() => setMessage(null)} />
      <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />
      {items === null ? <div className="mt-4"><LoadingState /></div> : (
        <ul className="mt-4 divide-y divide-border/60">
          {items.length === 0 ? <li className="py-3 text-sm text-muted">Travel belum menetapkan dokumen wajib. Anda tetap dapat mengunggah dokumen di bawah.</li> : null}
          {items.map((item) => {
            const status = item.latest ? DOC_STATUS[item.latest.status] : null;
            return (
              <li key={item.kind} className="py-4 text-sm">
                <p className="flex flex-wrap items-center gap-2 font-medium">
                  {item.label}
                  {item.mandatory ? <span className="text-xs font-normal text-muted">wajib{item.deadline ? ` · ${item.deadline.toLowerCase()}` : ""}</span> : null}
                  {status ? <StatusBadge tone={status.tone}>{status.label}</StatusBadge> : <StatusBadge tone="neutral">Belum diunggah</StatusBadge>}
                </p>
                {item.latest?.status === "REJECTED" && item.latest.reason ? <p className="mt-1 text-danger">Alasan: {item.latest.reason}. Silakan unggah ulang.</p> : null}
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {item.can_upload ? <Btn size="xs" variant={item.latest ? "tint" : "solid"} loading={busyKind === item.kind} disabled={busyKind !== null} onClick={() => choose(item.kind)}>{item.latest ? "Unggah ulang" : "Unggah"}</Btn> : null}
                  {item.latest?.has_file ? <Btn size="xs" variant="link" onClick={() => void open(item.latest!.id)}>Lihat berkas</Btn> : null}
                </div>
                {item.history.length > 1 ? (
                  <details className="mt-2 text-xs text-muted">
                    <summary className="cursor-pointer">Riwayat {item.history.length} versi</summary>
                    <ul className="mt-1 space-y-1">
                      {item.history.map((version) => <li key={version.id}>v{version.version} · {formatDate(version.uploaded_at)} · {DOC_STATUS[version.status]?.label ?? version.status}{version.reason ? ` — ${version.reason}` : ""}</li>)}
                    </ul>
                  </details>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      <div className="mt-4 flex flex-wrap items-end gap-3 border-t border-border/60 pt-6">
        <FormSelect label="Unggah dokumen lain" htmlFor={`extra-kind-${accessId}`} value={extra} onChange={(event) => setExtraKind(event.target.value)}>
          {extraOptions.map(([kind, label]) => <option key={kind} value={kind}>{label}</option>)}
        </FormSelect>
        <Btn size="xs" variant="tint" disabled={busyKind !== null || !extra} onClick={() => choose(extra)}>Pilih berkas</Btn>
      </div>
    </section>
  );
}

function ProfileCard({ accessId, profile, onSaved }: { accessId: string; profile: PortalProfile; onSaved: () => void }) {
  const initial = { phone: profile.phone, email: profile.email, address: profile.address, emergency_contact_name: profile.emergency_contact_name, emergency_contact_phone: profile.emergency_contact_phone };
  const [form, setForm] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const changed = (Object.keys(initial) as (keyof typeof initial)[]).filter((key) => form[key] !== initial[key]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true); setMessage(null); setError(null);
    const body = Object.fromEntries(changed.map((key) => [key, form[key]]));
    const result = await apiFetch<PortalProfile>(`/portal/accesses/${accessId}/profile`, { method: "PATCH", body: JSON.stringify(body) });
    setBusy(false);
    if (!result.ok) { setError(problemMessage(result.error)); return; }
    setMessage("Kontak tersimpan.");
    onSaved();
  }

  return (
    <section className="card min-w-0 p-6">
      <h2 className="font-semibold">Data diri & kontak</h2>
      <dl className="mt-3 grid gap-2 text-sm">
        <div className="flex justify-between gap-3"><dt className="text-muted">Nama</dt><dd className="text-right font-medium">{profile.name}</dd></div>
        <div className="flex justify-between gap-3"><dt className="text-muted">NIK</dt><dd>{profile.identity_masked ? formatMasked(profile.identity_masked) : "—"}</dd></div>
        <div className="flex justify-between gap-3"><dt className="text-muted">Paspor</dt><dd>{profile.passport_masked ? formatMasked(profile.passport_masked) : "—"}</dd></div>
      </dl>
      <p className="mt-2 text-xs text-muted">Data identitas salah? Ajukan koreksi di bagian “Koreksi data identitas” — travel akan memverifikasinya.</p>
      <form className="mt-6" onSubmit={save}>
        <FormField label="HP / WhatsApp" htmlFor={`p-phone-${accessId}`} inputMode="tel" value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} />
        <FormField label="Email" htmlFor={`p-email-${accessId}`} type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
        <FormTextarea label="Alamat" htmlFor={`p-address-${accessId}`} value={form.address} maxLength={500} onChange={(event) => setForm({ ...form, address: event.target.value })} />
        <FormField label="Kontak darurat" htmlFor={`p-ec-${accessId}`} value={form.emergency_contact_name} maxLength={160} onChange={(event) => setForm({ ...form, emergency_contact_name: event.target.value })} />
        <FormField label="HP kontak darurat" htmlFor={`p-ecp-${accessId}`} inputMode="tel" value={form.emergency_contact_phone} onChange={(event) => setForm({ ...form, emergency_contact_phone: event.target.value })} />
        <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />
        <FloatingNotice message={message} onDismiss={() => setMessage(null)} />
        <Btn type="submit" loading={busy} disabled={!changed.length}>Simpan kontak</Btn>
      </form>
    </section>
  );
}

const IDENTITY_FIELDS: [string, string, string][] = [
  ["name", "Nama sesuai dokumen", "text"], ["birth_place", "Tempat lahir", "text"], ["birth_date", "Tanggal lahir", "date"],
  ["identity_number", "NIK (16 digit)", "text"], ["passport_number", "Nomor paspor", "text"], ["passport_name", "Nama di paspor", "text"],
  ["passport_issued_at", "Tanggal terbit paspor", "date"], ["passport_expires_at", "Paspor berlaku hingga", "date"],
];

/** POR-06: jamaah mengajukan koreksi identitas; diterapkan setelah diverifikasi travel. */
function IdentityCorrection({ accessId, requests, onSent }: { accessId: string; requests: ChangeRequest[]; onSent: () => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = requests.find((r) => r.status === "PENDING");
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const changes = Object.fromEntries(Object.entries(values).filter(([, v]) => v.trim()));
    setBusy(true); setError(null);
    const result = await apiFetch<ChangeRequest>(`/portal/accesses/${accessId}/change-requests`, { method: "POST", body: JSON.stringify({ changes, reason }) });
    setBusy(false);
    if (!result.ok) { setError(problemMessage(result.error)); return; }
    setValues({}); setReason(""); onSent();
  }
  return (
    <section className="card p-6">
      <h2 className="font-semibold">Koreksi data identitas</h2>
      <p className="mt-1 text-sm text-muted">Isi hanya data yang perlu diperbaiki. Perubahan berlaku setelah diverifikasi travel dengan dokumen asli.</p>
      {requests.length ? <ul className="mt-3 space-y-2 text-sm">{requests.map((r) => <li key={r.id} className="border border-border/60 p-3">
        <p className="flex flex-wrap items-center gap-2"><StatusBadge tone={r.status === "APPROVED" ? "success" : r.status === "REJECTED" ? "danger" : "warning"}>{r.status_label}</StatusBadge><span className="text-xs text-muted">{formatDate(r.created_at)}</span></p>
        <p className="mt-1">{r.changes.map((c) => `${c.label}: ${c.value}`).join(" · ")}</p>
        {r.decision_note ? <p className="mt-1 text-xs text-muted">Catatan travel: {r.decision_note}</p> : null}
      </li>)}</ul> : null}
      {pending ? <p className="mt-4 text-sm text-muted">Permintaan Anda sedang diverifikasi. Anda dapat mengajukan koreksi lain setelah diputuskan.</p> : <form className="mt-5" onSubmit={submit}>
        <div className="grid gap-x-4 sm:grid-cols-2">{IDENTITY_FIELDS.map(([key, label, type]) => <FormField key={key} label={label} htmlFor={`idc-${key}-${accessId}`} type={type} value={values[key] ?? ""} onChange={(event) => setValues({ ...values, [key]: event.target.value })} />)}</div>
        <FormTextarea label="Alasan koreksi" htmlFor={`idc-reason-${accessId}`} value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} />
        <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />
        <Btn type="submit" loading={busy} disabled={!reason.trim() || !Object.values(values).some((v) => v.trim())}>Ajukan koreksi</Btn>
      </form>}
    </section>
  );
}
