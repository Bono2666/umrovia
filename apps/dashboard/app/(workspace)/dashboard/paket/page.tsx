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
import { formatIdr } from "@/lib/format";
import { apiFetch, problemMessage, type TravelPackage } from "@/lib/api";

/**
 * Master Paket (S08, UI-04; MOD-05; Spec §5.2/§8.3): daftar + CRUD draft/
 * publish. Publish hanya sah dari status Aktif (guard server); harga paket
 * yang sudah punya booking tidak mengubah invoice lama (snapshot booking,
 * S09). Varian harga per tipe kamar menyusul S09.
 */
const KIND_LABEL: Record<string, string> = {
  umroh: "Umroh",
  haji: "Haji",
  ziarah: "Ziarah",
};

const STATUS_TONE: Record<string, "neutral" | "success" | "warning"> = {
  DRAFT: "neutral",
  ACTIVE: "success",
  INACTIVE: "warning",
  ARCHIVED: "neutral",
};

export default function PaketPage() {
  const [rows, setRows] = useState<TravelPackage[] | null>(null);
  const [query, setQuery] = useState("");
  const [noAccess, setNoAccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [kind, setKind] = useState("umroh");
  const [durationDays, setDurationDays] = useState("");
  const [price, setPrice] = useState("");
  const [description, setDescription] = useState("");
  const [inclusions, setInclusions] = useState("");
  const [exclusions, setExclusions] = useState("");
  const [formErrors, setFormErrors] = useState<Record<string, string | null>>({});
  const [busy, setBusy] = useState(false);

  const load = useCallback((q: string) => {
    const suffix = q.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
    apiFetch<{ results: TravelPackage[] }>(`/packages${suffix}`).then((result) => {
      if (result.ok) setRows(result.data.results);
      else if (result.error.status === 403) setNoAccess(true);
      else setError(problemMessage(result.error));
    });
  }, []);

  useEffect(() => {
    load(query);
  }, [load, query]);

  async function patch(pkg: TravelPackage, body: Record<string, unknown>, label: string) {
    setBusyId(pkg.id);
    setError(null);
    const result = await apiFetch<TravelPackage>(`/packages/${pkg.id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    setBusyId(null);
    if (!result.ok) {
      setError(problemMessage(result.error));
      return;
    }
    setMessage(`${pkg.code}: ${label}.`);
    load(query);
  }

  async function onAdd(event: React.FormEvent) {
    event.preventDefault();
    const duration = Number(durationDays);
    const priceValue = Number(price);
    const errors: Record<string, string | null> = {
      name: name.trim() ? null : "Nama paket wajib diisi.",
      duration_days:
        Number.isInteger(duration) && duration >= 0 && duration <= 365
          ? null
          : "Durasi 0–365 hari.",
      price_idr:
        Number.isInteger(priceValue) && priceValue >= 0 && priceValue <= 10_000_000_000
          ? null
          : "Harga Rp0 – Rp10 miliar (integer rupiah).",
    };
    setFormErrors(errors);
    if (Object.values(errors).some(Boolean)) return;

    setBusy(true);
    setMessage(null);
    setError(null);
    const result = await apiFetch<TravelPackage>("/packages", {
      method: "POST",
      body: JSON.stringify({
        name: name.trim(),
        kind,
        duration_days: duration,
        price_idr: priceValue,
        description: description.trim(),
        inclusions: inclusions.split("\n").map((line) => line.trim()).filter(Boolean),
        exclusions: exclusions.split("\n").map((line) => line.trim()).filter(Boolean),
      }),
    });
    setBusy(false);
    if (!result.ok) {
      setFormErrors({ form: problemMessage(result.error) });
      return;
    }
    setName("");
    setKind("umroh");
    setDurationDays("");
    setPrice("");
    setDescription("");
    setInclusions("");
    setExclusions("");
    setMessage(`Paket ${result.data.code} tersimpan sebagai draf.`);
    load(query);
  }

  if (noAccess) {
    return (
      <div className="workspace-page">
        <h1 className="text-2xl font-bold">Paket</h1>
        <div className="mt-6">
          <EmptyState
            title="Halaman ini khusus staf dengan akses katalog"
            description="Peran Anda tidak memiliki permission packages.read."
          />
        </div>
      </div>
    );
  }

  return (
    <div className="workspace-page">
      <h1 className="text-2xl font-bold">Paket</h1>
      <p className="mt-1 text-sm text-muted">
        Katalog paket perjalanan (MOD-05). Harga dasar disimpan sebagai integer
        rupiah (§10.1); publish hanya bisa dari status Aktif, dan penarikan
        publikasi kapan pun. Perubahan harga tidak mengubah invoice yang sudah
        terbit.
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
          <h2 className="font-semibold">Daftar paket</h2>
          <FormField
            label="Cari"
            htmlFor="paket-search"
            hint="Nama atau kode paket."
            className="mt-4"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Ramadhan / PKT-…"
          />
          {rows === null ? (
            <div className="mt-4">
              <LoadingState label="Memuat paket…" />
            </div>
          ) : rows.length === 0 ? (
            <div className="mt-4">
              <EmptyState
                title="Belum ada paket"
                description="Buat paket pertama melalui formulir di samping."
              />
            </div>
          ) : (
            <ul className="mt-4 divide-y divide-border/60">
              {rows.map((pkg) => (
                <li key={pkg.id} className="flex flex-wrap items-center gap-2 py-3 text-sm">
                  <div className="min-w-44">
                    <p className="font-semibold">{pkg.name}</p>
                    <p className="text-xs text-muted">
                      {pkg.code} · {KIND_LABEL[pkg.kind] ?? pkg.kind} ·{" "}
                      {pkg.duration_days} hari · {formatIdr(pkg.price_idr)}
                    </p>
                  </div>
                  <StatusBadge tone={STATUS_TONE[pkg.status] ?? "neutral"}>
                    {pkg.status}
                  </StatusBadge>
                  {pkg.published ? <StatusBadge tone="success">TERBIT</StatusBadge> : null}
                  <span className="ml-auto flex flex-wrap gap-1.5">
                    {pkg.status === "DRAFT" ? (
                      <Btn
                        variant="tint"
                        size="xs"
                        disabled={busyId === pkg.id}
                        onClick={() => patch(pkg, { status: "ACTIVE" }, "diaktifkan")}
                      >
                        Aktifkan
                      </Btn>
                    ) : null}
                    {pkg.status === "ACTIVE" && !pkg.published ? (
                      <Btn
                        variant="tint"
                        size="xs"
                        disabled={busyId === pkg.id}
                        onClick={() => patch(pkg, { published: true }, "dipublikasikan")}
                      >
                        Publikasikan
                      </Btn>
                    ) : null}
                    {pkg.status === "ACTIVE" && pkg.published ? (
                      <Btn
                        variant="tint"
                        size="xs"
                        disabled={busyId === pkg.id}
                        onClick={() => patch(pkg, { published: false }, "publikasi ditarik")}
                      >
                        Tarik publikasi
                      </Btn>
                    ) : null}
                    {pkg.status === "ACTIVE" ? (
                      <Btn
                        variant="tint"
                        size="xs"
                        disabled={busyId === pkg.id}
                        onClick={() => patch(pkg, { status: "INACTIVE" }, "dinonaktifkan")}
                      >
                        Nonaktifkan
                      </Btn>
                    ) : null}
                    {pkg.status === "INACTIVE" ? (
                      <Btn
                        variant="tint"
                        size="xs"
                        disabled={busyId === pkg.id}
                        onClick={() => patch(pkg, { status: "ACTIVE" }, "diaktifkan kembali")}
                      >
                        Aktifkan
                      </Btn>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card p-6">
          <h2 className="font-semibold">Tambah paket</h2>
          {/* Workspace controls use compact typography and field spacing. */}
          <form onSubmit={onAdd} className="mt-6">
            <FormField
              label="Nama paket"
              htmlFor="package-name"
              error={formErrors.name}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Umroh Reguler 12 Hari"
              required
            />
            <FormSelect
              label="Jenis"
              htmlFor="package-kind"
              value={kind}
              onChange={(event) => setKind(event.target.value)}
            >
              <option value="umroh">Umroh</option>
              <option value="haji">Haji</option>
              <option value="ziarah">Ziarah</option>
            </FormSelect>
            <FormField
              label="Durasi (hari)"
              htmlFor="package-duration"
              error={formErrors.duration_days}
              value={durationDays}
              onChange={(event) => setDurationDays(event.target.value)}
              inputMode="numeric"
              placeholder="12"
            />
            <FormField
              label="Harga dasar (Rp)"
              htmlFor="package-price"
              hint="Integer rupiah tanpa desimal — varian harga per kamar menyusul S09."
              error={formErrors.price_idr}
              value={price}
              onChange={(event) => setPrice(event.target.value)}
              inputMode="numeric"
              placeholder="28500000"
            />
            <FormTextarea
              label="Deskripsi"
              htmlFor="package-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Rundown singkat, hotel, maskapai…"
            />
            <FormTextarea
              label="Fasilitas"
              htmlFor="package-inclusions"
              hint="Satu item per baris."
              value={inclusions}
              onChange={(event) => setInclusions(event.target.value)}
              placeholder={"Tiket\nHotel\nVisa"}
            />
            <FormTextarea
              label="Non-fasilitas"
              htmlFor="package-exclusions"
              hint="Satu item per baris."
              value={exclusions}
              onChange={(event) => setExclusions(event.target.value)}
              placeholder={"Upgrade kamar\nUang saku"}
            />
            {formErrors.form ? (
              <p className="error-message" role="alert">
                {formErrors.form}
              </p>
            ) : null}
            <div className="form-submit">
              <Btn type="submit" disabled={busy}>
                {busy ? "Menyimpan…" : "Tambah paket"}
              </Btn>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
