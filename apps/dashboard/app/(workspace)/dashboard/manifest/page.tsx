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
import { formatDate } from "@/lib/format";
import {
  API_BASE,
  apiFetch,
  hasPermission,
  problemMessage,
  type Departure,
  type ManifestEnvelope,
  type ManifestRequirement,
  type UserPayload,
} from "@/lib/api";

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
  before_ready: "Sebelum siap berangkat (READY)",
  before_departure: "Sebelum keberangkatan (DEPARTED)",
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
  not_eligible: "Belum eligible",
  pending_charge: "Charge tertunda",
  charged: "Tercharge",
  waived: "Diwaive",
  reversed: "Reversed",
};

const DOC_STATUS_LABEL: Record<string, string> = {
  UPLOADED: "terunggah",
  UNDER_REVIEW: "ditinjau",
  APPROVED: "disetujui",
  REJECTED: "ditolak",
};

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
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [includePii, setIncludePii] = useState(false);

  // form checklist (UI-11)
  const [reqKind, setReqKind] = useState("passport");
  const [reqDeadline, setReqDeadline] = useState("before_ready");
  const [reqMandatory, setReqMandatory] = useState(true);
  const [reqBusy, setReqBusy] = useState(false);

  const load = useCallback((depId: string, q: string, documentFilter: string) => {
    if (!depId) return; // pilih “— pilih keberangkatan —”: biarkan state (dibersihkan di handler)
    const params = new URLSearchParams({ checklist_gaps: "1" });
    if (q.trim()) params.set("q", q.trim());
    if (documentFilter) params.set("document", documentFilter);
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
        setDepartureId((prev) => prev || result.data.results[0]?.id || "");
      } else if (result.error.status === 403) {
        setNoAccess(true);
      }
    });
  }, []);

  useEffect(() => {
    load(departureId, query, docFilter);
  }, [departureId, query, docFilter, load]);

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
    load(departureId, query, docFilter);
  }

  function downloadCsv() {
    if (!departureId) return;
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (docFilter) params.set("document", docFilter);
    if (includePii) params.set("pii", "1");
    // unduh via anchor sintetis: server merespons Content-Disposition attachment
    const anchor = document.createElement("a");
    anchor.href = `${API_BASE}/api/v1/departures/${departureId}/manifest/export?${params.toString()}`;
    anchor.rel = "noopener";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
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
    load(departureId, query, docFilter);
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
    load(departureId, query, docFilter);
  }

  if (noAccess) {
    return (
      <div className="workspace-page">
        <h1 className="text-2xl font-bold">Manifest & checklist</h1>
        <div className="mt-6">
          <EmptyState
            title="Halaman ini khusus Operasional/Admin"
            description="Peran Anda tidak memiliki permission manifest.read."
          />
        </div>
      </div>
    );
  }

  const canExport = permissions !== null && hasPermission(permissions, "manifest.export");
  const canExportPii =
    permissions !== null && hasPermission(permissions, "manifest.export_pii");
  const canPublish = permissions !== null && hasPermission(permissions, "manifest.publish");
  const canManage =
    permissions !== null && hasPermission(permissions, "documents.requirements.manage");
  const gaps = envelope?.checklist_gaps ?? [];

  return (
    <div className="workspace-page">
      <h1 className="text-2xl font-bold">Manifest & checklist</h1>
      <p className="mt-1 text-sm text-muted">
        Daftar jamaah per keberangkatan (UI-12) dan checklist dokumen wajib per paket (UI-11,
        MOD-08). Roster hanya memuat peserta booking aktif (UAT-14) dengan identitas ter-mask;
        nilai NIK/paspor penuh hanya lewat ekspor PII yang berizin dan diaudit (OPS-03).
        Snapshot publikasi bersifat append-only — revisi selalu menjadi versi baru (§7.6).
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
        <div className="manifest-filters grid gap-x-3 gap-y-8 md:grid-cols-3">
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
        </div>
        {departures.length === 0 && permissions !== null ? (
          <p className="form-control__hint">
            Belum ada keberangkatan — buat dulu di menu Keberangkatan (UI-05).
          </p>
        ) : null}
      </section>

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
            Transisi keberangkatan ke <strong>READY</strong> akan ditolak server kecuali memakai
            <em> approved exception</em> dengan alasan (dicatat di audit, OPS-02) — ubah lewat menu
            Keberangkatan melalui “Siapkan dengan pengecualian”, atau lengkapi dokumen jamaah.
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
                      label="Sertakan PII"
                      checked={includePii}
                      onChange={setIncludePii}
                    />
                  ) : null}
                  <Btn variant="solid" size="xs" onClick={downloadCsv}>
                    Unduh CSV
                  </Btn>
                </>
              ) : null}
            </div>
          </div>
          {canExport && canExportPii ? (
            <p className="mt-1 text-xs text-muted">
              Kolom PII (NIK/paspor penuh, kebutuhan khusus) memerlukan permission
              manifest.export_pii dan selalu tercatat di audit.
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
                    NIK {row.identity_masked || "—"} · Paspor {row.passport_masked || "—"}
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
              ; syarat global dapat ditimpa per paket. <code>before_ready</code> menggerakkan
              gerbang READY keberangkatan & booking siap berangkat; <code>before_departure</code>{" "}
              menggerakkan gerbang DEPARTED.
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
                Belum ada syarat dokumen — gerbang checklist lulus otomatis (belum ada yang bisa
                kurang).
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
                    label="Wajib (menggerakkan gerbang kesiapan)"
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
                    <p className="mt-0.5 truncate text-xs text-muted">
                      checksum {version.checksum.slice(0, 16)}…
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-muted">
                Belum ada versi terbit — publikasikan snapshot untuk membekukan roster (§7.6).
              </p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
