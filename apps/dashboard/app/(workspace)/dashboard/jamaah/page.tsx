"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Btn,
  EmptyState,
  ErrorState,
  FormField,
  FormCheckbox,
  FormSelect,
  FormTextarea,
  LoadingState,
  StatusBadge,
} from "@/components/workspace/ui";
import {
  apiFetch,
  apiUpload,
  downloadFromApi,
  problemMessage,
  type Pilgrim,
  type PilgrimDocument,
  type PilgrimPortalStatus,
} from "@/lib/api";
import { formatDate, formatMasked } from "@/lib/format";
import { changedFields, focusForm, formErrors as apiFormErrors } from "@/lib/forms";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";

const DOC_KIND: Record<string, string> = { ktp: "KTP", passport: "Paspor", photo: "Foto", kk: "Kartu Keluarga", other: "Dokumen lain" };
const DOC_STATUS: Record<string, string> = { UPLOADED: "Menunggu review", UNDER_REVIEW: "Ditinjau", APPROVED: "Disetujui", REJECTED: "Ditolak" };

const EMPTY_PROFILE = {
  nationality: "ID", marital_status: "", address: "",
  emergency_contact_name: "", emergency_contact_phone: "",
  guardian_name: "", guardian_relation: "", special_needs: "",
  passport_name: "", passport_issued_at: "", passport_expires_at: "", passport_place_of_issue: "",
};

const PROFILE_FIELDS = [
  ["nationality", "Kewarganegaraan (kode negara)"],
  ["marital_status", "Status perkawinan"],
  ["emergency_contact_name", "Nama kontak darurat"],
  ["emergency_contact_phone", "Telepon kontak darurat"],
  ["guardian_name", "Nama wali / mahram"],
  ["guardian_relation", "Hubungan wali / mahram"],
  ["passport_name", "Nama sesuai paspor"],
  ["passport_issued_at", "Tanggal terbit paspor"],
  ["passport_expires_at", "Tanggal kedaluwarsa paspor"],
  ["passport_place_of_issue", "Tempat terbit paspor"],
] as const;

/**
 * Master Jamaah (S07, Spec §8.3/UI-06): daftar + pencarian, tambah, dan
 * checklist dokumen. NIK/paspor dikirim write-only — API hanya mengembalikan
 * varian masked (§10.1). Duplikat identitas ditandai otomatis oleh server
 * (MOD-04: ditandai, bukan digabung). Tanpa permission `pilgrims.read` →
 * tampil status tanpa akses (server menolak semua operasi).
 */
export default function JamaahPage() {
  const {can, canEditEnvironment, writableEnvironments} = useWorkspacePermissions();
  const [editing, setEditing] = useState<Pilgrim | null>(null);
  const [clearIdentity, setClearIdentity] = useState(false);
  const [clearPassport, setClearPassport] = useState(false);
  const [status, setStatus] = useState("ACTIVE");
  const [rows, setRows] = useState<Pilgrim[] | null>(null);
  const [selected, setSelected] = useState<Pilgrim | null>(null);
  const [documents, setDocuments] = useState<PilgrimDocument[]>([]);
  const [portal, setPortal] = useState<PilgrimPortalStatus | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [uploadKind, setUploadKind] = useState("passport");
  const [docBusy, setDocBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [noAccess, setNoAccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [gender, setGender] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [birthPlace, setBirthPlace] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [identityNumber, setIdentityNumber] = useState("");
  const [passportNumber, setPassportNumber] = useState("");
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [formErrors, setFormErrors] = useState<Record<string, string | null>>({});
  const [busy, setBusy] = useState(false);

  const load = useCallback((q: string) => {
    const suffix = q.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
    apiFetch<{ results: Pilgrim[] }>(`/pilgrims${suffix}`).then((result) => {
      if (result.ok) setRows(result.data.results);
      else if (result.error.status === 403) setNoAccess(true);
      else setError(problemMessage(result.error));
    });
  }, []);

  useEffect(() => {
    load(query);
  }, [load, query]);

  function openDetail(pilgrim: Pilgrim) {
    setSelected(pilgrim);
    setDocuments([]);
    setPortal(null);
    setInviteEmail(pilgrim.email || "");
  }

  const selectedId = selected?.id;
  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    Promise.all([
      apiFetch<Pilgrim>(`/pilgrims/${selectedId}`),
      apiFetch<{ results: PilgrimDocument[] }>(`/pilgrims/${selectedId}/documents`),
      apiFetch<PilgrimPortalStatus>(`/pilgrims/${selectedId}/portal`),
    ]).then(([detail, docs, access]) => {
      if (cancelled) return;
      if (detail.ok) setSelected(detail.data);
      else setError(problemMessage(detail.error));
      if (docs.ok) setDocuments(docs.data.results);
      else setError(problemMessage(docs.error));
      if (access.ok) setPortal(access.data);
    });
    return () => { cancelled = true; };
  }, [selectedId]);

  async function reloadDocuments(pilgrimId: string) {
    const [docs, access] = await Promise.all([
      apiFetch<{ results: PilgrimDocument[] }>(`/pilgrims/${pilgrimId}/documents`),
      apiFetch<PilgrimPortalStatus>(`/pilgrims/${pilgrimId}/portal`),
    ]);
    if (docs.ok) setDocuments(docs.data.results);
    if (access.ok) setPortal(access.data);
  }

  async function sendInvite(pilgrim: Pilgrim) {
    setDocBusy(true); setError(null); setMessage(null);
    const result = await apiFetch<PilgrimPortalStatus>(`/pilgrims/${pilgrim.id}/portal`, { method: "POST", body: JSON.stringify({ email: inviteEmail.trim() }) });
    setDocBusy(false);
    if (!result.ok) { setError(problemMessage(result.error)); return; }
    setPortal(result.data);
    setMessage(`Undangan portal dikirim ke ${result.data.pending_invite?.email ?? inviteEmail}.`);
  }

  async function revokePortal(pilgrim: Pilgrim, body: { access_id?: string; invite_id?: string }) {
    if (!window.confirm(body.access_id ? "Cabut akses portal jamaah ini? Jamaah tidak dapat lagi melihat data atau mengunggah dokumen." : "Batalkan undangan yang belum dipakai?")) return;
    setDocBusy(true); setError(null); setMessage(null);
    const result = await apiFetch<PilgrimPortalStatus>(`/pilgrims/${pilgrim.id}/portal/revoke`, { method: "POST", body: JSON.stringify(body) });
    setDocBusy(false);
    if (!result.ok) { setError(problemMessage(result.error)); return; }
    setPortal(result.data);
    setMessage(body.access_id ? "Akses portal dicabut." : "Undangan dibatalkan.");
  }

  async function reviewDocument(pilgrim: Pilgrim, doc: PilgrimDocument, status: "APPROVED" | "REJECTED") {
    let reason = "";
    if (status === "REJECTED") {
      const input = window.prompt(`Alasan menolak ${DOC_KIND[doc.kind] ?? doc.kind} v${doc.version} (akan terlihat oleh jamaah):`);
      if (input === null) return;
      if (!input.trim()) { setError("Alasan penolakan wajib diisi."); return; }
      reason = input.trim();
    }
    setDocBusy(true); setError(null); setMessage(null);
    const result = await apiFetch<PilgrimDocument>(`/pilgrims/${pilgrim.id}/documents/${doc.id}`, { method: "PATCH", body: JSON.stringify(status === "REJECTED" ? { status, reason } : { status }) });
    setDocBusy(false);
    if (!result.ok) { setError(problemMessage(result.error)); return; }
    setMessage(`${DOC_KIND[doc.kind] ?? doc.kind} ${status === "APPROVED" ? "disetujui" : "ditolak"}.`);
    void reloadDocuments(pilgrim.id);
  }

  async function uploadDocument(pilgrim: Pilgrim, file: File) {
    setDocBusy(true); setError(null); setMessage(null);
    const form = new FormData();
    form.append("kind", uploadKind);
    form.append("file", file);
    const result = await apiUpload<PilgrimDocument>(`/pilgrims/${pilgrim.id}/documents/upload`, form);
    setDocBusy(false);
    if (!result.ok) { setError(problemMessage(result.error)); return; }
    setMessage(`${DOC_KIND[uploadKind] ?? uploadKind} terunggah dan menunggu review.`);
    void reloadDocuments(pilgrim.id);
  }

  async function openDocument(pilgrim: Pilgrim, doc: PilgrimDocument) {
    setError(null);
    const result = await apiFetch<{ path: string }>(`/pilgrims/${pilgrim.id}/documents/${doc.id}/download-url`, { method: "POST" });
    if (result.ok) downloadFromApi(result.data.path);
    else setError(problemMessage(result.error));
  }

  async function onAdd(event: React.FormEvent) {
    event.preventDefault();
    const errors: Record<string, string | null> = {
      name: name.trim() ? null : "Nama sesuai dokumen wajib diisi.",
      birth_date: birthDate || editing ? null : "Tanggal lahir wajib diisi.",
      identity_number:
        clearIdentity || !identityNumber.trim() || identityNumber.replace(/\D/g, "").length === 16
          ? null
          : "NIK harus 16 digit.",
    };
    setFormErrors(errors);
    if (Object.values(errors).some(Boolean)) return;

    setBusy(true);
    setMessage(null);
    const values = {
        ...profile,
        passport_issued_at: profile.passport_issued_at || null,
        passport_expires_at: profile.passport_expires_at || null,
        name: name.trim(),
        gender,
        birth_date: birthDate || null,
        birth_place: birthPlace.trim(),
        phone: phone.trim(),
        email: email.trim(),
        status,
      };
    const payload = editing ? changedFields(values, editing) : values;
    const result = await apiFetch<Pilgrim>(editing ? `/pilgrims/${editing.id}` : "/pilgrims", {
      method: editing ? "PATCH" : "POST",
      body: JSON.stringify({...payload,
        ...(!editing || clearIdentity || identityNumber.trim() ? {identity_number: clearIdentity ? "" : identityNumber.replace(/\D/g, "")} : {}),
        ...(!editing || clearPassport || passportNumber.trim() ? {passport_number: clearPassport ? "" : passportNumber.trim()} : {}),
      }),
    });
    setBusy(false);
    if (!result.ok) {
      setFormErrors(apiFormErrors(result.error));
      return;
    }
    if (editing) setSelected(result.data);
    resetForm();
    const created = result.data;
    setMessage(
      created.possible_duplicate_of
        ? `Jamaah ${created.code} tersimpan — identitas serupa terdeteksi dan ditandai sebagai potensi duplikat.`
        : `Jamaah ${created.code} tersimpan.`,
    );
    load(query);
  }

  function resetForm() {
    setEditing(null); setClearIdentity(false); setClearPassport(false); setStatus("ACTIVE"); setFormErrors({});
    setName("");
    setGender("");
    setBirthDate("");
    setBirthPlace("");
    setPhone("");
    setEmail("");
    setIdentityNumber("");
    setPassportNumber("");
    setProfile(EMPTY_PROFILE);
  }

  async function removePilgrim(pilgrim: Pilgrim) {
    if (!window.confirm(`Hapus jamaah ${pilgrim.code} — ${pilgrim.name}? Gunakan Arsip bila data ini benar. Data yang belum pernah dipakai dihapus permanen.`)) return;
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch(`/pilgrims/${pilgrim.id}`, { method: "DELETE" });
    setBusy(false);
    if (!result.ok) { setError(problemMessage(result.error)); return; }
    setMessage(`Jamaah ${pilgrim.code} dihapus.`);
    load(query);
  }

  async function editPilgrim(pilgrim: Pilgrim) {
    setBusy(true); setError(null);
    const result = await apiFetch<Pilgrim>(`/pilgrims/${pilgrim.id}`);
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    const p = result.data;
    resetForm(); setEditing(p); setSelected(p);
    setName(p.name); setGender(p.gender); setBirthDate(p.birth_date ?? ""); setBirthPlace(p.birth_place);
    setPhone(p.phone); setEmail(p.email); setStatus(p.status);
    setProfile(Object.fromEntries(Object.keys(EMPTY_PROFILE).map((key) => [key, p[key as keyof Pilgrim] ?? ""])) as typeof EMPTY_PROFILE);
    setMessage(null); focusForm("pilgrim-form");
  }

  if (noAccess) {
    return (
      <div className="workspace-page">
        <RevealText as="h1" variant="title" className="text-2xl font-bold">Jamaah</RevealText>
        <div className="mt-6">
          <EmptyState
            title="Halaman ini khusus staf dengan akses jamaah"
            description="Peran Anda belum diberi akses melihat data jamaah. Hubungi Owner travel."
          />
        </div>
      </div>
    );
  }

  return (
    <div className="workspace-page">
      <RevealText as="h1" variant="title" className="text-2xl font-bold">Jamaah</RevealText>
      <p className="mt-1 text-sm text-muted">
        Data jamaah travel Anda. NIK dan nomor paspor disimpan terenkripsi dan
        hanya ditampilkan 4 karakter terakhir. Jamaah dengan identitas sama
        ditandai sebagai kemungkinan duplikat agar dapat Anda periksa.
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
        <h2 className="font-semibold">Daftar jamaah</h2>
        <FormField
          label="Cari"
          htmlFor="jamaah-search"
          hint="Nama, kode, telepon, atau NIK (exact)."
          className="mt-4"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Budi / JM-… / 0812…"
        />
        {rows === null ? (
          <div className="mt-4">
            <LoadingState label="Memuat jamaah…" />
          </div>
        ) : rows.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="Belum ada jamaah"
              description="Daftarkan jamaah pertama melalui formulir di samping."
            />
          </div>
        ) : (
          <ul className="mt-4 divide-y divide-border/60">
            {rows.map((pilgrim) => (
              <li key={pilgrim.id} className="py-4 text-sm">
                <p className="flex flex-wrap items-center gap-2 font-semibold">
                  {pilgrim.name}
                  <StatusBadge tone={pilgrim.status === "ACTIVE" ? "success" : "neutral"}>
                    {pilgrim.status === "ACTIVE" ? "Aktif" : "Diarsipkan"}
                  </StatusBadge>
                  {pilgrim.possible_duplicate_of ? (
                    <StatusBadge tone="warning">Kemungkinan duplikat</StatusBadge>
                  ) : null}
                </p>
                <p className="text-xs text-muted">
                  {pilgrim.code}
                  {pilgrim.identity_masked ? ` · NIK ${formatMasked(pilgrim.identity_masked)}` : ""}
                  {pilgrim.phone ? ` · ${pilgrim.phone}` : ""}
                </p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Btn variant="tint" size="xs" onClick={() => openDetail(pilgrim)}>Detail</Btn>
                  {can("pilgrims.write") && canEditEnvironment(pilgrim.environment) ? <Btn variant="tint" size="xs" disabled={busy} onClick={() => editPilgrim(pilgrim)}>Ubah jamaah</Btn> : null}
                  {pilgrim.deletable && can("pilgrims.write") && canEditEnvironment(pilgrim.environment) ? <Btn variant="danger" size="xs" disabled={busy || editing?.id === pilgrim.id} onClick={() => void removePilgrim(pilgrim)}>Hapus</Btn> : null}
                </div>
              </li>
            ))}
          </ul>
        )}

        {selected ? (
          <div className="mt-6 border-t border-border/60 pt-4">
            <h3 className="font-semibold">
              {selected.name}{" "}
              <code className="ml-2 border border-border bg-background px-2 py-0.5 text-xs">
                {selected.code}
              </code>
            </h3>
            <dl className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
              <div className="flex justify-between gap-3">
                <dt className="text-muted">NIK</dt>
                <dd>{selected.identity_masked ? formatMasked(selected.identity_masked) : "—"}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted">Paspor</dt>
                <dd>{selected.passport_masked ? formatMasked(selected.passport_masked) : "—"}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted">Lahir</dt>
                <dd>
                  {selected.birth_place ? `${selected.birth_place}, ` : ""}
                  {selected.birth_date ?? "—"}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted">Telepon</dt>
                <dd>{selected.phone || "—"}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted">Email</dt>
                <dd>{selected.email || "—"}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted">Wali/mahram</dt>
                <dd>
                  {selected.guardian_name
                    ? `${selected.guardian_name} (${selected.guardian_relation || "-"})`
                    : "—"}
                </dd>
              </div>
            </dl>
            {selected.special_needs ? (
              <p className="mt-3 border border-border/60 bg-background p-3 text-sm">
                <span className="text-muted">Catatan kebutuhan khusus: </span>
                {selected.special_needs}
              </p>
            ) : null}

            <h4 className="mt-4 text-sm font-semibold">Dokumen</h4>
            {documents.length === 0 ? (
              <p className="mt-2 text-sm text-muted">
                Belum ada dokumen untuk jamaah ini.
              </p>
            ) : (
              <ul className="mt-2 divide-y divide-border/60">
                {documents.map((doc) => {
                  const latest = !documents.some((other) => other.kind === doc.kind && other.version > doc.version);
                  const reviewable = latest && can("documents.review") && canEditEnvironment(selected.environment) && (doc.status === "UPLOADED" || doc.status === "UNDER_REVIEW");
                  return (
                    <li key={doc.id} className="py-3 text-sm">
                      <p className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{DOC_KIND[doc.kind] ?? doc.kind}</span>
                        <span className="text-xs text-muted">v{doc.version} · {formatDate(doc.uploaded_at)}</span>
                        <StatusBadge tone={doc.status === "APPROVED" ? "success" : doc.status === "REJECTED" ? "danger" : "warning"}>{DOC_STATUS[doc.status] ?? doc.status}</StatusBadge>
                      </p>
                      {doc.reason ? <p className="mt-1 text-xs text-muted">Alasan: {doc.reason}</p> : null}
                      {doc.has_file || reviewable ? (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {doc.has_file ? <Btn size="xs" variant="tint" onClick={() => void openDocument(selected, doc)}>Lihat berkas</Btn> : null}
                          {reviewable ? <Btn size="xs" disabled={docBusy} onClick={() => void reviewDocument(selected, doc, "APPROVED")}>Setujui</Btn> : null}
                          {reviewable ? <Btn size="xs" variant="danger" disabled={docBusy} onClick={() => void reviewDocument(selected, doc, "REJECTED")}>Tolak</Btn> : null}
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}
            {can("pilgrims.write") && canEditEnvironment(selected.environment) ? (
              <div className="mt-3 flex flex-wrap items-end gap-3">
                <FormSelect label="Unggah dokumen" htmlFor="staff-doc-kind" value={uploadKind} onChange={(event) => setUploadKind(event.target.value)}>
                  {Object.entries(DOC_KIND).map(([kind, label]) => <option key={kind} value={kind}>{label}</option>)}
                </FormSelect>
                <label className={`btn btn--primary btn--xs ${docBusy ? "pointer-events-none opacity-60" : "cursor-pointer"}`}>
                  Pilih berkas
                  <input type="file" accept=".pdf,.jpg,.jpeg,.png" className="sr-only" disabled={docBusy} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void uploadDocument(selected, file); }} />
                </label>
              </div>
            ) : null}

            <h4 className="mt-6 text-sm font-semibold">Portal jamaah</h4>
            {portal === null ? (
              <p className="mt-2 text-sm text-muted">Memuat status portal…</p>
            ) : (
              <div className="mt-2 space-y-2 text-sm">
                {portal.accesses.filter((row) => row.status === "ACTIVE").map((row) => (
                  <p key={row.id} className="flex flex-wrap items-center gap-2">
                    <StatusBadge tone="success">Aktif</StatusBadge>
                    <span className="break-all">{row.email}</span>
                    <span className="text-xs text-muted">sejak {formatDate(row.created_at)}</span>
                    {can("pilgrims.write") ? <Btn size="xs" variant="link" disabled={docBusy} onClick={() => void revokePortal(selected, { access_id: row.id })}>Cabut akses</Btn> : null}
                  </p>
                ))}
                {portal.pending_invite ? (
                  <p className="flex flex-wrap items-center gap-2">
                    <StatusBadge tone="warning">Undangan terkirim</StatusBadge>
                    <span className="break-all">{portal.pending_invite.email}</span>
                    <span className="text-xs text-muted">berlaku s.d. {formatDate(portal.pending_invite.expires_at)}</span>
                    {can("pilgrims.write") ? <Btn size="xs" variant="link" disabled={docBusy} onClick={() => void revokePortal(selected, { invite_id: portal.pending_invite!.id })}>Batalkan</Btn> : null}
                  </p>
                ) : null}
                {!portal.accesses.some((row) => row.status === "ACTIVE") && !portal.pending_invite ? <p className="text-muted">Jamaah belum memiliki akses portal.</p> : null}
                {can("pilgrims.write") && canEditEnvironment(selected.environment) ? (
                  <div className="flex flex-wrap items-end gap-3">
                    <FormField label="Email jamaah" htmlFor="portal-invite-email" type="email" value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} hint="Jamaah menerima tautan sekali pakai untuk melihat jadwal, pembayaran dan mengunggah dokumen." />
                    <Btn size="xs" disabled={docBusy || !inviteEmail.trim()} onClick={() => void sendInvite(selected)}>{portal.pending_invite || portal.accesses.length ? "Kirim ulang undangan" : "Undang ke portal"}</Btn>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        ) : null}
      </section>

      {can("pilgrims.write") && writableEnvironments.length > 0 ? <section className="card p-6">
        <h2 className="font-semibold">{editing ? `Ubah jamaah ${editing.code}` : "Tambah jamaah"}</h2>
        {/* Workspace controls use compact typography and field spacing. */}
        <form id="pilgrim-form" onSubmit={onAdd} className="mt-6 scroll-mt-24"><fieldset className="min-w-0" disabled={busy}>
          <FormField
            label="Nama sesuai dokumen"
            htmlFor="pilgrim-name"
            error={formErrors.name}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Budi Santoso"
            required
          />
          <FormSelect
            label="Jenis kelamin"
            htmlFor="pilgrim-gender"
            value={gender}
            onChange={(event) => setGender(event.target.value)}
          >
            <option value="">— pilih —</option>
            <option value="male">Laki-laki</option>
            <option value="female">Perempuan</option>
          </FormSelect>
          <FormField
            label="Tanggal lahir"
            htmlFor="pilgrim-birth-date"
            type="date"
            error={formErrors.birth_date}
            value={birthDate}
            onChange={(event) => setBirthDate(event.target.value)}
            required={!editing}
          />
          <FormField
            label="Tempat lahir"
            htmlFor="pilgrim-birth-place"
            value={birthPlace}
            onChange={(event) => setBirthPlace(event.target.value)}
            placeholder="Jakarta"
          />
          <FormField
            label="HP / WhatsApp"
            htmlFor="pilgrim-phone"
            hint="Format 08xx atau +62 — dinormalisasi otomatis."
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            inputMode="tel"
            placeholder="08123456789"
          />
          <FormField
            label="Email"
            htmlFor="pilgrim-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="budi@example.com"
          />
          <FormField
            label="NIK"
            htmlFor="pilgrim-identity"
            hint={editing ? `Tersimpan: ${editing.identity_masked || "belum ada"}. Kosongkan untuk mempertahankan nomor.` : "16 digit — disimpan terenkripsi."}
            error={formErrors.identity_number}
            value={identityNumber}
            onChange={(event) => setIdentityNumber(event.target.value)}
            inputMode="numeric"
            disabled={clearIdentity}
            placeholder="3175092102900001"
          />
          {editing?.identity_masked ? <FormCheckbox id="clear-pilgrim-identity" label="Hapus NIK tersimpan" checked={clearIdentity} onChange={setClearIdentity} /> : null}
          <FormField
            label="Nomor paspor"
            htmlFor="pilgrim-passport"
            hint={editing ? `Tersimpan: ${editing.passport_masked || "belum ada"}. Kosongkan untuk mempertahankan nomor.` : "Disimpan terenkripsi."}
            value={passportNumber}
            disabled={clearPassport}
            onChange={(event) => setPassportNumber(event.target.value)}
            placeholder="C1234567"
          />
          {editing?.passport_masked ? <FormCheckbox id="clear-pilgrim-passport" label="Hapus nomor paspor tersimpan" checked={clearPassport} onChange={setClearPassport} /> : null}
          {editing ? <FormSelect label="Status jamaah" htmlFor="pilgrim-status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="ACTIVE">Aktif</option><option value="ARCHIVED">Diarsipkan</option></FormSelect> : null}
          <details className="my-6 border-t border-border pt-4">
            <summary className="cursor-pointer text-sm font-semibold">
              Data tambahan, kontak darurat &amp; paspor
            </summary>
            <div className="mt-6">
              {PROFILE_FIELDS.map(([key, label]) => (
                <FormField
                  key={key}
                  label={label}
                  htmlFor={`pilgrim-${key}`}
                  type={key.endsWith("_at") ? "date" : "text"}
                  error={formErrors[key]}
                  value={profile[key]}
                  onChange={(event) => setProfile((prev) => ({ ...prev, [key]: event.target.value }))}
                />
              ))}
              <FormTextarea
                label="Alamat"
                htmlFor="pilgrim-address"
                value={profile.address}
                onChange={(event) => setProfile((prev) => ({ ...prev, address: event.target.value }))}
              />
              <FormTextarea
                label="Catatan kebutuhan khusus"
                htmlFor="pilgrim-special-needs"
                hint="Ditampilkan pada detail jamaah untuk staf yang memiliki akses."
                value={profile.special_needs}
                onChange={(event) => setProfile((prev) => ({ ...prev, special_needs: event.target.value }))}
              />
            </div>
          </details>
          {formErrors.form ? (
            <p className="error-message" role="alert">
              {formErrors.form}
            </p>
          ) : null}
          <div className="form-submit">
            <Btn type="submit" disabled={busy}>
              {busy ? "Menyimpan…" : editing ? "Simpan perubahan" : "Tambah jamaah"}
            </Btn>
            {editing ? <Btn type="button" variant="tint" className="ml-2" onClick={resetForm}>Batal ubah</Btn> : null}
          </div>
        </fieldset></form>
      </section> : null}
      </div>
    </div>
  );
}
