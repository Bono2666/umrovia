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
import {
  apiFetch,
  problemMessage,
  type Pilgrim,
  type PilgrimDocument,
} from "@/lib/api";

/**
 * Master Jamaah (S07, Spec §8.3/UI-06): daftar + pencarian, tambah, dan
 * checklist dokumen. NIK/paspor dikirim write-only — API hanya mengembalikan
 * varian masked (§10.1). Duplikat identitas ditandai otomatis oleh server
 * (MOD-04: ditandai, bukan digabung). Tanpa permission `pilgrims.read` →
 * tampil status tanpa akses (server menolak semua operasi).
 */
export default function JamaahPage() {
  const [rows, setRows] = useState<Pilgrim[] | null>(null);
  const [selected, setSelected] = useState<Pilgrim | null>(null);
  const [documents, setDocuments] = useState<PilgrimDocument[]>([]);
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

  async function openDetail(pilgrim: Pilgrim) {
    setSelected(pilgrim);
    const result = await apiFetch<{ results: PilgrimDocument[] }>(
      `/pilgrims/${pilgrim.id}/documents`,
    );
    if (result.ok) setDocuments(result.data.results);
  }

  async function onAdd(event: React.FormEvent) {
    event.preventDefault();
    const errors: Record<string, string | null> = {
      name: name.trim() ? null : "Nama sesuai dokumen wajib diisi.",
      birth_date: birthDate ? null : "Tanggal lahir wajib diisi.",
      identity_number:
        !identityNumber.trim() || identityNumber.replace(/\D/g, "").length === 16
          ? null
          : "NIK harus 16 digit.",
    };
    setFormErrors(errors);
    if (Object.values(errors).some(Boolean)) return;

    setBusy(true);
    setMessage(null);
    const result = await apiFetch<Pilgrim>("/pilgrims", {
      method: "POST",
      body: JSON.stringify({
        name: name.trim(),
        gender,
        birth_date: birthDate,
        birth_place: birthPlace.trim(),
        phone: phone.trim(),
        email: email.trim(),
        identity_number: identityNumber.replace(/\D/g, ""),
        passport_number: passportNumber.trim(),
      }),
    });
    setBusy(false);
    if (!result.ok) {
      setFormErrors({ form: problemMessage(result.error) });
      return;
    }
    setName("");
    setGender("");
    setBirthDate("");
    setBirthPlace("");
    setPhone("");
    setEmail("");
    setIdentityNumber("");
    setPassportNumber("");
    const created = result.data;
    setMessage(
      created.possible_duplicate_of
        ? `Jamaah ${created.code} tersimpan — identitas serupa terdeteksi dan ditandai sebagai potensi duplikat.`
        : `Jamaah ${created.code} tersimpan (NIK/paspor disimpan terenkripsi, tampil masked).`,
    );
    load(query);
  }

  if (noAccess) {
    return (
      <div className="workspace-page">
        <h1 className="text-2xl font-bold">Jamaah</h1>
        <div className="mt-6">
          <EmptyState
            title="Halaman ini khusus staf dengan akses jamaah"
            description="Peran Anda tidak memiliki permission pilgrims.read."
          />
        </div>
      </div>
    );
  }

  return (
    <div className="workspace-page">
      <h1 className="text-2xl font-bold">Jamaah</h1>
      <p className="mt-1 text-sm text-muted">
        Master data jamaah (MOD-04). NIK &amp; nomor paspor disimpan terenkripsi
        dan hanya ditampilkan sebagai 4 karakter terakhir (masked, §10.1);
        identitas sama ditandai sebagai potensi duplikat — tidak digabung
        otomatis.
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
              <li key={pilgrim.id} className="flex flex-wrap items-center gap-3 py-3 text-sm">
                <div className="min-w-40">
                  <p className="font-semibold">{pilgrim.name}</p>
                  <p className="text-xs text-muted">
                    {pilgrim.code}
                    {pilgrim.identity_masked ? ` · NIK ${pilgrim.identity_masked}` : ""}
                    {pilgrim.phone ? ` · ${pilgrim.phone}` : ""}
                  </p>
                </div>
                {pilgrim.possible_duplicate_of ? (
                  <StatusBadge tone="warning">DUPLIKAT?</StatusBadge>
                ) : null}
                <StatusBadge tone={pilgrim.status === "ACTIVE" ? "success" : "neutral"}>
                  {pilgrim.status === "ACTIVE" ? "AKTIF" : "DIARSIPKAN"}
                </StatusBadge>
                <Btn variant="tint" className="ml-auto" onClick={() => openDetail(pilgrim)}>
                  Detail
                </Btn>
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
                <dd>{selected.identity_masked || "—"}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted">Paspor</dt>
                <dd>{selected.passport_masked || "—"}</dd>
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
                Belum ada dokumen terdaftar untuk jamaah ini.
              </p>
            ) : (
              <ul className="mt-2 divide-y divide-border/60">
                {documents.map((doc) => (
                  <li key={doc.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
                    <span className="min-w-24 font-medium uppercase">{doc.kind}</span>
                    <span className="text-xs text-muted">v{doc.version}</span>
                    <StatusBadge
                      tone={
                        doc.status === "APPROVED"
                          ? "success"
                          : doc.status === "REJECTED"
                            ? "danger"
                            : "neutral"
                      }
                    >
                      {doc.status}
                    </StatusBadge>
                    {doc.reason ? (
                      <span className="text-xs text-muted">{doc.reason}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : null}
      </section>

      <section className="card p-6">
        <h2 className="font-semibold">Tambah jamaah</h2>
        {/* Workspace controls use compact typography and field spacing. */}
        <form onSubmit={onAdd} className="mt-6">
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
            required
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
            hint="16 digit — disimpan terenkripsi (write-only, tampil masked)."
            error={formErrors.identity_number}
            value={identityNumber}
            onChange={(event) => setIdentityNumber(event.target.value)}
            inputMode="numeric"
            placeholder="3175092102900001"
          />
          <FormField
            label="Nomor paspor"
            htmlFor="pilgrim-passport"
            hint="Disimpan terenkripsi (write-only, tampil masked)."
            value={passportNumber}
            onChange={(event) => setPassportNumber(event.target.value)}
            placeholder="C1234567"
          />
          {formErrors.form ? (
            <p className="error-message" role="alert">
              {formErrors.form}
            </p>
          ) : null}
          <div className="form-submit">
            <Btn type="submit" disabled={busy}>
              {busy ? "Menyimpan…" : "Tambah jamaah"}
            </Btn>
          </div>
        </form>
      </section>
      </div>
    </div>
  );
}
