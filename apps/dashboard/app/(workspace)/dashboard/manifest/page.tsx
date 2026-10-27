"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Btn,
  EmptyState,
  ErrorState,
  FormCheckbox,
  FormField,
  FormSelect,
  LoadingState,
  StatusBadge,
} from "@/components/workspace/ui";
import { formatDate, formatIdr, formatMasked } from "@/lib/format";
import {
  downloadFromApi,
  apiFetch,
  hasPermission,
  problemMessage,
  type Departure,
  type ManifestEnvelope,
  type ManifestRequirement,
  type UserPayload,
  type ManifestReadiness,
} from "@/lib/api";
import { RevealText } from "@/components/marketing/RevealText";

/**
 * Manifest keberangkatan & checklist operasional (S10; Spec §5.2/§7.6/§8.3,
 * UI-11/UI-12; PRD MOD-08/MOD-12; OPS-02/OPS-03; UAT-14; exit gate S10
 * "Basic departure manifests export").
 *
 * - roster per keberangkatan: hanya peserta booking AKTIF (UAT-14), field
 *   selalu masked (§10.1); filter q + status dokumen (MOD-12);
 * - publikasi snapshot → versi bernomor urut unik + checksum (§7.6);
 * - ekspor CSV: masked sebagai default; "Sertakan PII" hanya bila memegang
 *   `manifest.export_pii` (Owner per matriks §3) — server tetap otoritas dan
 *   mencatat audit `manifest.exported`/`manifest.export_denied` (OPS-03);
 * - checklist per paket (MOD-08): tambah/hapus syarat dokumen; gerbang READY
 *   tanpa *approved exception* ditolak server dengan alasan (OPS-02);
 * - daftar versi terbit + indikator kekurangan gerbang READY.
 */

const KIND_LABEL: Record<string, string> = {
  ktp: "KTP",
  passport: "Paspor",
  photo: "Foto",
  kk: "Kartu Keluarga",
  other: "Dokumen lain",
};

const DEADLINE_LABEL: Record<string, string> = {
  before_ready: "Sebelum siap berangkat",
  before_departure: "Sebelum berangkat",
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

const CHARGE_LABEL: Record<string, string> = {
  not_eligible: "Belum ada DP",
  pending_charge: "Biaya layanan tertunda",
  charged: "Biaya layanan lunas",
  waived: "Biaya dibebaskan",
  reversed: "Biaya direfund",
};

const DOC_STATUS_LABEL: Record<string, string> = {
  UPLOADED: "terunggah",
  UNDER_REVIEW: "ditinjau",
  APPROVED: "disetujui",
  REJECTED: "ditolak",
};

const PAYMENT_LABEL: Record<string, string> = { paid: "Lunas", partial: "Sebagian", unpaid: "Belum bayar" };

/** Ringkasan kesiapan keberangkatan (S15, OPS-06): seluruh jamaah aktif, bukan hasil filter. */
function ReadinessCard({ readiness }: { readiness: ManifestReadiness }) {
  const total = readiness.participants;
  const metric = (label: string, value: number, tone?: string) => (
    <div className="card p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className={`mt-1 text-xl font-bold ${tone ?? ""}`}>{value}<span className="text-sm font-normal text-muted"> / {total}</span></p>
    </div>
  );
  return (
    <section className="mt-6" aria-label="Kesiapan keberangkatan">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {metric("Dokumen wajib lengkap", readiness.docs_complete, readiness.docs_complete === total && total ? "text-success" : "")}
        {metric("DP diterima", readiness.dp_received)}
        {metric("Lunas", readiness.fully_paid, readiness.fully_paid === total && total ? "text-success" : "")}
        {metric("Terkonfirmasi", readiness.confirmed)}
      </div>
      <p className="mt-2 text-xs text-muted">
        Kursi {readiness.seats_taken} terpakai dari {readiness.seat_capacity} · sisa {readiness.available_seats}
        {readiness.outstanding_idr > 0 ? ` · piutang jamaah ${formatIdr(readiness.outstanding_idr)}` : " · tidak ada piutang"}
        {readiness.pending_charge ? ` · ${readiness.pending_charge} menunggu saldo SaaS Wallet` : ""}
        {readiness.checklist_ready ? " · checklist siap berangkat terpenuhi" : ` · ${readiness.gap_count} kekurangan dokumen wajib`}
      </p>
    </section>
  );
}

function docSummary(row: ManifestEnvelope["rows"][number]): string {
  if (row.docs_complete) return "Lengkap";
  const parts = row.docs_missing.map((kind) => {
    const status = row.docs[kind];
    const label = KIND_LABEL[kind] ?? kind;
    return status ? `${label} (${DOC_STATUS_LABEL[status] ?? status})` : `${label} (belum)`;
  });
  return parts.join(", ");
}

export default function ManifestPage() {
  const [permissions, setPermissions] = useState<string[] | null>(null);
  const [noAccess, setNoAccess] = useState(false);
  const [departures, setDepartures] = useState<Departure[]>([]);
  const [departureId, setDepartureId] = useState("");
  const [envelope, setEnvelope] = useState<ManifestEnvelope | null>(null);
  const [query, setQuery] = useState("");
  const [docFilter, setDocFilter] = useState("");
  const [payFilter, setPayFilter] = useState("");
  const [fullFormPii, setFullFormPii] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [includePii, setIncludePii] = useState(false);

  // form checklist (UI-11)
  const [reqKind, setReqKind] = useState("passport");
  const [reqDeadline, setReqDeadline] = useState("before_ready");
  const [reqMandatory, setReqMandatory] = useState(true);
  const [reqBusy, setReqBusy] = useState(false);

  const load = useCallback((depId: string, q: string, documentFilter: string, paymentFilter = "") => {
    if (!depId) return; // pilih “— pilih keberangkatan —”: biarkan state (dibersihkan di handler)
    const params = new URLSearchParams({ checklist_gaps: "1" });
    if (q.trim()) params.set("q", q.trim());
    if (documentFilter) params.set("document", documentFilter);
    if (paymentFilter) params.set("payment", paymentFilter);
    apiFetch<ManifestEnvelope>(`/departures/${depId}/manifest?${params.toString()}`).then(
      (result) => {
        if (result.ok) {
          setEnvelope(result.data);
          setError(null);
        } else if (result.error.status === 403) {
          setNoAccess(true);
        } else {
          setError(problemMessage(result.error));
        }
      },
    );
  }, []);

  useEffect(() => {
    apiFetch<UserPayload>("/me").then((result) => {
      if (!result.ok) return;
      const me = result.data;
      const active =
        me.memberships.find((m) => m.tenant.slug === (me.active_tenant_slug ?? "")) ??
        me.memberships.find((m) => m.status === "ACTIVE");
      setPermissions(active?.permissions ?? []);
    });
  }, []);

  useEffect(() => {
    apiFetch<{ results: Departure[] }>("/departures").then((result) => {
      if (result.ok) {
        setDepartures(result.data.results);
        // ?departure= dari halaman Keberangkatan memilih keberangkatan tersebut.
        const wanted = new URLSearchParams(window.location.search).get("departure");
        const preferred = result.data.results.find((dep) => dep.id === wanted)?.id;
        setDepartureId((prev) => prev || preferred || result.data.results[0]?.id || "");
      } else if (result.error.status === 403) {
        setNoAccess(true);
      }
    });
  }, []);

  useEffect(() => {
    load(departureId, query, docFilter, payFilter);
  }, [departureId, query, docFilter, payFilter, load]);

  async function publish() {
    if (!departureId) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const result = await apiFetch<{ version: { version_no: number; checksum: string } }>(
      `/departures/${departureId}/manifest/publish`,
      { method: "POST", body: "{}" },
    );
    setBusy(false);
    if (!result.ok) {
      setError(problemMessage(result.error));
      return;
    }
    setMessage(
      `Versi ${result.data.version.version_no} dipublikasikan — checksum ` +
        `${result.data.version.checksum.slice(0, 12)}… (snapshot tersimpan, tidak dapat diedit).`,
    );
    load(departureId, query, docFilter, payFilter);
  }

  function downloadExport(file: "csv" | "xlsx" | "pdf") {
    if (!departureId) return;
    const params = new URLSearchParams({ file });
    if (query.trim()) params.set("q", query.trim());
    if (docFilter) params.set("document", docFilter);
    if (payFilter) params.set("payment", payFilter);
    if (includePii) params.set("pii", "1");
    // Server merespons Content-Disposition attachment; filter sama dengan tampilan.
    downloadFromApi(`/api/v1/departures/${departureId}/manifest/export?${params.toString()}`);
  }

  function printDocument(kind: "registration-forms" | "labels" | "envelopes") {
    if (!departureId) return;
    const params = new URLSearchParams();
    if (kind === "registration-forms" && fullFormPii) params.set("pii", "1");
    downloadFromApi(`/api/v1/departures/${departureId}/print/${kind}${params.size ? `?${params}` : ""}`);
  }

  async function addRequirement(event: React.FormEvent) {
    event.preventDefault();
    if (!envelope) return;
    setReqBusy(true);
    setError(null);
    setMessage(null);
    const result = await apiFetch<ManifestRequirement>("/document-requirements", {
      method: "POST",
      body: JSON.stringify({
        package: envelope.departure.package_id,
        kind: reqKind,
        mandatory: reqMandatory,
        deadline_rule: reqDeadline,
      }),
    });
    setReqBusy(false);
    if (!result.ok) {
      setError(problemMessage(result.error));
      return;
    }
    setMessage(
      `Syarat dokumen ${KIND_LABEL[reqKind] ?? reqKind} ditambahkan untuk paket ` +
        `${envelope.departure.package_code}.`,
    );
    load(departureId, query, docFilter, payFilter);
  }

  async function removeRequirement(req: ManifestRequirement) {
    if (!window.confirm(`Hapus syarat dokumen ${KIND_LABEL[req.kind] ?? req.kind}?`)) return;
    setBusy(true);
    setError(null);
    const result = await apiFetch<void>(`/document-requirements/${req.id}`, { method: "DELETE" });
    setBusy(false);
    if (!result.ok) {
      setError(problemMessage(result.error));
      return;
    }
    setMessage("Syarat dokumen dihapus.");
    load(departureId, query, docFilter, payFilter);
  }

  if (noAccess) {
    return (
      <div className="workspace-page">
        <RevealText as="h1" variant="title" className="text-2xl font-bold">Manifest & checklist</RevealText>
        <div className="mt-6">
          <EmptyState
            title="Halaman ini khusus Operasional/Admin"
            description="Peran Anda belum diberi akses melihat manifest. Hubungi Owner travel."
          />
        </div>
      </div>
    );
  }

  const canExport = permissions !== null && hasPermission(permissions, "manifest.export");
  const canExportPii =
    permissions !== null && hasPermission(permissions, "manifest.export_pii");
  // TBD-08 opsi C: staf cakupan cabang melihat roster cabangnya; manifest resmi diterbitkan pusat.
  const canPublish = permissions !== null && hasPermission(permissions, "manifest.publish") && envelope?.full_scope !== false;
  const canManage =
    permissions !== null && hasPermission(permissions, "documents.requirements.manage");
  const gaps = envelope?.checklist_gaps ?? [];

  return (
    <div className="workspace-page">
      <RevealText as="h1" variant="title" className="text-2xl font-bold">Manifest & checklist</RevealText>
      <p className="mt-1 text-sm text-muted">
        Daftar jamaah per keberangkatan dan checklist dokumen wajib per paket.
        Manifest hanya memuat peserta booking aktif dengan identitas tersamar.
        Ekspor dengan NIK/paspor lengkap hanya untuk peran berwenang dan selalu
        tercatat. Setiap publikasi disimpan sebagai versi baru.
      </p>

      {message ? (
        <p
          className="mt-4 border border-success/30 bg-success/10 p-3 text-sm text-success"
          role="status"
        >
          {message}
        </p>
      ) : null}
      {error ? (
        <div className="mt-4">
          <ErrorState message={error} />
        </div>
      ) : null}

      <section className="card mt-6 p-6">
        <div className="manifest-filters grid gap-x-3 gap-y-8 md:grid-cols-2 xl:grid-cols-4">
          <FormSelect
            label="Keberangkatan"
            htmlFor="manifest-departure"
            value={departureId}
            onChange={(event) => {
              setDepartureId(event.target.value);
              if (!event.target.value) setEnvelope(null); // bersihkan di handler, bukan effect
            }}
          >
            <option value="">— pilih keberangkatan —</option>
            {departures.map((dep) => (
              <option key={dep.id} value={dep.id}>
                {dep.code} — {dep.package_name} · {formatDate(dep.start_at)}
              </option>
            ))}
          </FormSelect>
          <FormField
            label="Cari"
            htmlFor="manifest-search"
            hint="Kode booking, kode/nama jamaah."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="BK-… / Budi"
          />
          <FormSelect
            label="Status dokumen"
            htmlFor="manifest-doc-filter"
            value={docFilter}
            onChange={(event) => setDocFilter(event.target.value)}
          >
            <option value="">Semua</option>
            <option value="complete">Lengkap semua</option>
            <option value="incomplete">Belum lengkap</option>
          </FormSelect>
          <FormSelect
            label="Pembayaran"
            htmlFor="manifest-pay-filter"
            value={payFilter}
            onChange={(event) => setPayFilter(event.target.value)}
          >
            <option value="">Semua</option>
            <option value="paid">Lunas</option>
            <option value="partial">Sebagian</option>
            <option value="unpaid">Belum bayar</option>
          </FormSelect>
        </div>
        {departures.length === 0 && permissions !== null ? (
          <p className="form-control__hint">
            Belum ada keberangkatan — buat dulu di menu Keberangkatan.
          </p>
        ) : null}
      </section>

      {envelope?.readiness ? <ReadinessCard readiness={envelope.readiness} /> : null}

      {gaps.length > 0 ? (
        <div className="mt-4 border border-warning/30 bg-warning/10 p-3 text-sm">
          <p className="font-semibold text-warning">
            Checklist belum lengkap — {gaps.length} kekurangan dokumen wajib
          </p>
          <ul className="mt-1 list-inside list-disc text-muted">
            {gaps.slice(0, 6).map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
            {gaps.length > 6 ? <li>… dan {gaps.length - 6} lainnya</li> : null}
          </ul>
          <p className="mt-1 text-xs">
            Keberangkatan belum dapat ditandai <strong>Siap berangkat</strong> sampai dokumen di atas
            lengkap. Bila perlu, gunakan “Siap dengan pengecualian” di menu Keberangkatan dengan
            alasan yang dicatat di audit.
          </p>
        </div>
      ) : null}

      <div className="workspace-columns mt-6">
        <section className="card p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-semibold">
              Roster manifest
              {envelope ? (
                <span className="ml-2 text-sm font-normal text-muted">
                  {envelope.departure.code} · {envelope.row_count} jamaah
                </span>
              ) : null}
            </h2>
            <div className="flex flex-wrap items-center gap-2">
              {canPublish && departureId ? (
                <Btn variant="tint" size="xs" disabled={busy} onClick={publish}>
                  {busy ? "Memproses…" : "Publikasikan versi"}
                </Btn>
              ) : null}
              {canExport && departureId ? (
                <>
                  {canExportPii ? (
                    <FormCheckbox
                      id="manifest-pii"
                      label="Sertakan data pribadi"
                      checked={includePii}
                      onChange={setIncludePii}
                    />
                  ) : null}
                  <Btn variant="solid" size="xs" onClick={() => downloadExport("pdf")}>PDF</Btn>
                  <Btn variant="tint" size="xs" onClick={() => downloadExport("xlsx")}>Excel</Btn>
                  <Btn variant="tint" size="xs" onClick={() => downloadExport("csv")}>CSV</Btn>
                </>
              ) : null}
            </div>
          </div>
          {canExport && canExportPii ? (
            <p className="mt-1 text-xs text-muted">
              Data pribadi lengkap (NIK/paspor penuh, kebutuhan khusus) hanya untuk
              peran berwenang dan setiap ekspor tercatat di audit.
            </p>
          ) : null}

          {!departureId ? (
            <div className="mt-4">
              <EmptyState
                title="Pilih keberangkatan"
                description="Roster manifest menampilkan peserta booking aktif keberangkatan terpilih."
              />
            </div>
          ) : envelope === null ? (
            <div className="mt-4">
              <LoadingState label="Memuat manifest…" />
            </div>
          ) : envelope.rows.length === 0 ? (
            <div className="mt-4">
              <EmptyState
                title="Belum ada peserta"
                description="Booking aktif (bukan dibatalkan/kedaluwarsa) akan muncul di sini."
              />
            </div>
          ) : (
            <ul className="mt-4 divide-y divide-border/60">
              {envelope.rows.map((row) => (
                <li key={row.participant_id} className="py-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="min-w-44">
                      <p className="font-semibold">{row.name}</p>
                      <p className="text-xs text-muted">
                        {row.pilgrim_code} · {row.booking_code} ·{" "}
                        {row.birth_date ? formatDate(row.birth_date) : "—"}
                      </p>
                    </div>
                    <StatusBadge tone={row.docs_complete ? "success" : "warning"}>
                      {docSummary(row)}
                    </StatusBadge>
                    <span className="ml-auto text-xs text-muted">
                      {PARTICIPANT_LABEL[row.participant_status] ?? row.participant_status} ·{" "}
                      {CHARGE_LABEL[row.saas_charge_state] ?? row.saas_charge_state}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted">
                    NIK {row.identity_masked ? formatMasked(row.identity_masked) : "—"} · Paspor {row.passport_masked ? formatMasked(row.passport_masked) : "—"}
                  </p>
                  <p className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                    <StatusBadge tone={row.payment_status === "paid" ? "success" : row.payment_status === "partial" ? "warning" : "neutral"}>{PAYMENT_LABEL[row.payment_status]}</StatusBadge>
                    <span className="text-muted">
                      Terbayar {formatIdr(row.paid_idr)} dari {formatIdr(row.amount_idr)}
                      {row.balance_idr > 0 ? ` · sisa ${formatIdr(row.balance_idr)}` : ""}
                    </span>
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>

        <div className="flex flex-col gap-6">
          <section className="card p-6">
            <h2 className="font-semibold">Checklist dokumen paket</h2>
            <p className="mt-1 text-xs text-muted">
              Berlaku untuk paket{" "}
              {envelope ? `${envelope.departure.package_code} — ${envelope.departure.package_name}` : "keberangkatan terpilih"}
. Syarat bertanda <strong>wajib</strong> harus lengkap sebelum batas waktunya:
              sebelum booking/keberangkatan ditandai siap berangkat, atau sebelum berangkat.
            </p>
            {envelope && envelope.requirements.length > 0 ? (
              <ul className="mt-3 divide-y divide-border/60">
                {envelope.requirements.map((req) => (
                  <li key={req.id} className="flex items-center gap-2 py-2 text-sm">
                    <span className="font-medium">{KIND_LABEL[req.kind] ?? req.kind}</span>
                    <StatusBadge tone={req.mandatory ? "warning" : "neutral"}>
                      {req.mandatory ? "Wajib" : "Opsional"}
                    </StatusBadge>
                    <span className="text-xs text-muted">
                      {DEADLINE_LABEL[req.deadline_rule] ?? req.deadline_rule}
                      {req.package_id ? " · per paket" : " · global"}
                    </span>
                    {canManage ? (
                      <button
                        type="button"
                        className="ml-auto text-xs text-muted hover:text-danger"
                        disabled={busy}
                        onClick={() => removeRequirement(req)}
                      >
                        Hapus
                      </button>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-muted">
                Belum ada syarat dokumen untuk paket ini, sehingga semua jamaah dianggap lengkap.
              </p>
            )}

            {canManage && envelope ? (
              <form onSubmit={addRequirement} className="mt-4 border-t border-border/60 pt-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Tambah syarat
                </p>
                <FormSelect
                  label="Jenis dokumen"
                  htmlFor="req-kind"
                  className="mt-2"
                  value={reqKind}
                  onChange={(event) => setReqKind(event.target.value)}
                >
                  {Object.entries(KIND_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </FormSelect>
                <FormSelect
                  label="Batas waktu"
                  htmlFor="req-deadline"
                  className="mt-2"
                  value={reqDeadline}
                  onChange={(event) => setReqDeadline(event.target.value)}
                >
                  {Object.entries(DEADLINE_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </FormSelect>
                <div className="mt-2">
                  <FormCheckbox
                    id="req-mandatory"
                    label="Wajib dipenuhi sebelum batas waktu"
                    checked={reqMandatory}
                    onChange={setReqMandatory}
                  />
                </div>
                <div className="form-submit">
                  <Btn type="submit" disabled={reqBusy} loading={reqBusy}>
                    Tambah
                  </Btn>
                </div>
              </form>
            ) : null}
          </section>

          {canExport && departureId ? (
            <section className="card p-6">
              <h2 className="font-semibold">Cetak dokumen</h2>
              <p className="mt-1 text-xs text-muted">Untuk seluruh jamaah aktif keberangkatan ini. Dokumen demo diberi watermark.</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Btn size="xs" variant="tint" onClick={() => printDocument("registration-forms")}>Formulir pendaftaran</Btn>
                <Btn size="xs" variant="tint" onClick={() => printDocument("labels")}>Label koper</Btn>
                <Btn size="xs" variant="tint" onClick={() => printDocument("envelopes")}>Amplop</Btn>
              </div>
              {canExportPii ? (
                <div className="mt-3">
                  <FormCheckbox id="form-pii" label="Tampilkan NIK & paspor lengkap pada formulir" checked={fullFormPii} onChange={setFullFormPii} />
                </div>
              ) : null}
            </section>
          ) : null}

          <section className="card p-6">
            <h2 className="font-semibold">Versi manifest</h2>
            {envelope && envelope.versions.length > 0 ? (
              <ul className="mt-3 divide-y divide-border/60">
                {envelope.versions.map((version) => (
                  <li key={version.id} className="py-2 text-sm">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">v{version.version_no}</span>
                      <span className="text-xs text-muted">
                        {formatDate(version.created_at)} ·{" "}
                        {version.published_by_name ?? "sistem"}
                      </span>
                    </div>
                    <p className="mt-0.5 flex items-center justify-between gap-2 text-xs text-muted">
                      <span className="truncate">checksum {version.checksum.slice(0, 16)}…</span>
                      {canExport ? <Btn size="xs" variant="link" onClick={() => downloadFromApi(`/api/v1/departures/${departureId}/manifest/versions/${version.version_no}/pdf`)}>Unduh PDF</Btn> : null}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-muted">
                Belum ada versi terbit. Publikasikan untuk menyimpan salinan manifest saat ini.
              </p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
