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
import { apiFetch, problemMessage, type TravelPackage, type RoomType } from "@/lib/api";
import { EMPTY_ROOM_PRICES, ROOM_LABELS } from "@/lib/rooms";
import { changedFields, focusForm, formErrors as apiFormErrors } from "@/lib/forms";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";
import { FloatingNotice, focusRecord } from "@/components/workspace/FloatingNotice";

/**
 * Master Paket (S08, UI-04; MOD-05; Spec §5.2/§8.3): daftar + CRUD draft/
 * publish. Publish hanya sah dari status Aktif (guard server); harga paket
 * yang sudah punya booking tidak mengubah invoice lama (snapshot booking,
 * S09). S11: harga kamar dipilih dan di-snapshot per peserta booking.
 */
const KIND_LABEL: Record<string, string> = {
  umroh: "Umroh",
  haji: "Haji",
  ziarah: "Ziarah",
};

const STATUS_LABEL: Record<string, string> = {
  DRAFT: "Draf",
  ACTIVE: "Aktif",
  INACTIVE: "Nonaktif",
  ARCHIVED: "Diarsipkan",
};

const STATUS_TONE: Record<string, "neutral" | "success" | "warning"> = {
  DRAFT: "neutral",
  ACTIVE: "success",
  INACTIVE: "warning",
  ARCHIVED: "neutral",
};

const digits = (value: string) => Number(value.replace(/\D/g, "")) || 0;
/** Baris "a | b | c" → [a, b, c] (baris kosong diabaikan). */
const parseRows = (text: string) => text.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
  const parts = line.split("|").map((part) => part.trim());
  return [parts[0] ?? "", parts[1] ?? "", parts[2] ?? "0"];
});

export default function PaketPage() {
  const {can, canEditEnvironment, writableEnvironments} = useWorkspacePermissions();
  const [cancellationPolicy, setCancellationPolicy] = useState("");
  const [paymentTerms, setPaymentTerms] = useState("");
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
  const [roomPrices, setRoomPrices] = useState(EMPTY_ROOM_PRICES);
  const [editing, setEditing] = useState<TravelPackage | null>(null);
  const [description, setDescription] = useState("");
  const [inclusions, setInclusions] = useState("");
  const [exclusions, setExclusions] = useState("");
  const [formErrors, setFormErrors] = useState<Record<string, string | null>>({});
  const [busy, setBusy] = useState(false);
  const [childPrice, setChildPrice] = useState("");
  const [infantPrice, setInfantPrice] = useState("");
  const [addonsText, setAddonsText] = useState("");
  const [costsText, setCostsText] = useState("");

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
    focusRecord(pkg.id);
    setMessage(`${pkg.code}: ${label}.`);
    load(query);
  }

  async function onAdd(event: React.FormEvent) {
    event.preventDefault();
    const duration = Number(durationDays);
    const variants = Object.entries(roomPrices).filter(([, value]) => value.trim() !== "").map(([room_type, value]) => ({ room_type, price_idr: Number(value) }));
    const priceValue = variants.length ? Math.min(...variants.map((row) => row.price_idr)) : Number(price);
    const errors: Record<string, string | null> = {
      name: name.trim() ? null : "Nama paket wajib diisi.",
      duration_days:
        Number.isInteger(duration) && duration >= 0 && duration <= 365
          ? null
          : "Durasi 0–365 hari.",
      price_idr:
        (variants.length > 0 || price.trim() !== "") && Number.isInteger(priceValue) && priceValue >= 0 && priceValue <= 10_000_000_000
          ? null
          : "Harga Rp0 – Rp10 miliar (integer rupiah).",
      room_prices: variants.every((row) => Number.isInteger(row.price_idr) && row.price_idr >= 0 && row.price_idr <= 10_000_000_000) ? null : "Harga kamar harus integer Rp0–Rp10 miliar.",
    };
    const addons = parseRows(addonsText).map(([code, label, amount]) => ({ code: code.toUpperCase(), name: label, price_idr: digits(amount) }));
    const costs = parseRows(costsText).map(([category, label, amount]) => ({ category, description: label, amount_idr: digits(amount) }));
    errors.addons = addons.every((row) => /^[A-Z0-9_-]{2,24}$/.test(row.code) && row.name && row.price_idr >= 0) ? null : "Format layanan tambahan: KODE | Nama | harga (satu per baris).";
    errors.estimated_costs = costs.every((row) => row.category && row.description) ? null : "Format estimasi biaya: Kategori | Uraian | jumlah per jamaah.";
    setFormErrors(errors);
    if (Object.values(errors).some(Boolean)) return;

    setBusy(true);
    setMessage(null);
    setError(null);
    const values = {
        name: name.trim(),
        kind,
        duration_days: duration,
        price_idr: priceValue,
        room_prices: variants,
        description: description.trim(),
        inclusions: inclusions.split("\n").map((line) => line.trim()).filter(Boolean),
        exclusions: exclusions.split("\n").map((line) => line.trim()).filter(Boolean),
        cancellation_policy:cancellationPolicy.trim(), payment_terms:paymentTerms.trim(),
        child_no_bed_price_idr: childPrice.trim() ? digits(childPrice) : null,
        infant_price_idr: infantPrice.trim() ? digits(infantPrice) : null,
        addons, estimated_costs: costs,
      };
    const result = await apiFetch<TravelPackage>(editing ? `/packages/${editing.id}` : "/packages", {
      method: editing ? "PATCH" : "POST",
      body:JSON.stringify(editing ? changedFields(values, editing) : values),
    });
    setBusy(false);
    if (!result.ok) {
      setFormErrors(apiFormErrors(result.error));
      return;
    }
    setName("");
    setKind("umroh");
    setDurationDays("");
    setPrice("");
    setRoomPrices(EMPTY_ROOM_PRICES);
    setEditing(null);
    setDescription("");
    setInclusions("");
    setExclusions(""); setCancellationPolicy(""); setPaymentTerms(""); setChildPrice(""); setInfantPrice(""); setAddonsText(""); setCostsText("");
    focusRecord(result.data.id);
    setMessage(`Paket ${result.data.code} tersimpan${editing ? "; harga booking yang sudah ada tetap" : " sebagai draf"}.`);
    load(query);
  }

  async function removePackage(pkg: TravelPackage) {
    if (!window.confirm(`Hapus paket ${pkg.code} — ${pkg.name}? Data yang belum pernah dipakai dihapus permanen.`)) return;
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch(`/packages/${pkg.id}`, { method: "DELETE" });
    setBusy(false);
    if (!result.ok) { setError(problemMessage(result.error)); return; }
    setMessage(`Paket ${pkg.code} dihapus.`);
    load(query);
  }

  function editPackage(pkg: TravelPackage) {
    setEditing(pkg); setCancellationPolicy(pkg.cancellation_policy); setPaymentTerms(pkg.payment_terms);
    focusForm("package-form");
    setName(pkg.name); setKind(pkg.kind); setDurationDays(String(pkg.duration_days));
    setPrice(String(pkg.price_idr)); setDescription(pkg.description);
    setInclusions(pkg.inclusions.join("\n")); setExclusions(pkg.exclusions.join("\n"));
    setRoomPrices({ ...EMPTY_ROOM_PRICES, ...Object.fromEntries((pkg.room_prices ?? []).map((row) => [row.room_type, String(row.price_idr)])) });
    setChildPrice(pkg.child_no_bed_price_idr != null ? String(pkg.child_no_bed_price_idr) : ""); setInfantPrice(pkg.infant_price_idr != null ? String(pkg.infant_price_idr) : "");
    setAddonsText((pkg.addons ?? []).map((a) => `${a.code} | ${a.name} | ${a.price_idr}`).join("\n"));
    setCostsText((pkg.estimated_costs ?? []).map((c) => `${c.category} | ${c.description} | ${c.amount_idr}`).join("\n"));
    setFormErrors({});
  }

  if (noAccess) {
    return (
      <div className="workspace-page">
        <RevealText as="h1" variant="title" className="text-2xl font-bold">Paket</RevealText>
        <div className="mt-6">
          <EmptyState
            title="Halaman ini khusus staf dengan akses katalog"
            description="Peran Anda belum diberi akses melihat paket. Hubungi Owner travel."
          />
        </div>
      </div>
    );
  }

  return (
    <div className="workspace-page">
      <RevealText as="h1" variant="title" className="text-2xl font-bold">Paket</RevealText>
      <p className="mt-1 text-sm text-muted">
        Katalog paket perjalanan beserta harganya. Aktifkan paket sebelum
        menerbitkannya. Perubahan harga hanya berlaku untuk booking baru; booking
        dan invoice yang sudah ada tidak berubah.
      </p>

      <FloatingNotice message={message} onDismiss={() => setMessage(null)} />
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
                <li key={pkg.id} data-record={pkg.id} className="py-4 text-sm">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 font-semibold">
                      {pkg.name}
                      <StatusBadge tone={STATUS_TONE[pkg.status] ?? "neutral"}>{STATUS_LABEL[pkg.status] ?? pkg.status}</StatusBadge>
                      {pkg.published ? <StatusBadge tone="success">Terbit</StatusBadge> : null}
                    </p>
                    <p className="text-xs text-muted">
                      {pkg.code} · {KIND_LABEL[pkg.kind] ?? pkg.kind} ·{" "}
                      {pkg.duration_days ? `${pkg.duration_days} hari · ` : ""}{(pkg.room_prices ?? []).length ? "Mulai " : ""}{formatIdr(pkg.price_idr)}
                    </p>
                    {(pkg.room_prices ?? []).length ? <p className="mt-1 text-xs text-muted">{pkg.room_prices.map((room) => `${ROOM_LABELS[room.room_type]} ${formatIdr(room.price_idr)}`).join(" · ")}</p> : null}
                    {pkg.child_no_bed_price_idr != null || pkg.infant_price_idr != null ? <p className="mt-1 text-xs text-muted">{[pkg.child_no_bed_price_idr != null ? `Anak tanpa kasur ${formatIdr(pkg.child_no_bed_price_idr)}` : "", pkg.infant_price_idr != null ? `Bayi ${formatIdr(pkg.infant_price_idr)}` : ""].filter(Boolean).join(" · ")}</p> : null}
                    {pkg.addons?.length ? <p className="mt-1 text-xs text-muted">Layanan tambahan: {pkg.addons.map((a) => `${a.name} ${formatIdr(a.price_idr)}`).join(" · ")}</p> : null}
                    {pkg.estimated_cost_per_pax_idr ? <p className="mt-1 text-xs text-muted">Estimasi biaya {formatIdr(pkg.estimated_cost_per_pax_idr)}/jamaah · estimasi margin {formatIdr(pkg.estimated_margin_per_pax_idr ?? 0)} dari harga terendah</p> : null}
                  </div>
                  {can("packages.write") && canEditEnvironment(pkg.environment) ? <div className="mt-3 flex flex-wrap gap-1.5">
                    {pkg.status === "DRAFT" ? (
                      <Btn
                        variant="solid"
                        size="xs"
                        disabled={busyId === pkg.id}
                        onClick={() => patch(pkg, { status: "ACTIVE" }, "diaktifkan")}
                      >
                        Aktifkan
                      </Btn>
                    ) : null}
                    {pkg.status === "ACTIVE" && !pkg.published ? (
                      <Btn
                        variant="solid"
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
                    <Btn variant="tint" size="xs" disabled={busy} onClick={() => editPackage(pkg)}>Ubah paket / harga</Btn>
                    {pkg.deletable ? <Btn variant="danger" size="xs" disabled={busy || editing?.id === pkg.id} onClick={() => void removePackage(pkg)}>Hapus</Btn> : null}
                  </div> : null}
                </li>
              ))}
            </ul>
          )}
        </section>

        {can("packages.write") && writableEnvironments.length > 0 ? <section className="card p-6">
          <h2 className="font-semibold">{editing ? `Ubah ${editing.code}` : "Tambah paket"}</h2>
          {/* Workspace controls use compact typography and field spacing. */}
          <form id="package-form" onSubmit={onAdd} className="mt-6 scroll-mt-24"><fieldset className="min-w-0" disabled={busy}>
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
              label="Harga standar tanpa varian (Rp)"
              htmlFor="package-price"
              hint="Isi bila tidak memakai harga per tipe kamar. Semua harga dihitung per jamaah."
              error={formErrors.price_idr}
              value={price}
              onChange={(event) => setPrice(event.target.value)}
              inputMode="numeric"
              placeholder="28500000"
            />
            <fieldset className="my-6 border-t border-border pt-6">
              <legend className="text-sm font-semibold">Harga per tipe kamar (Rp / jamaah)</legend>
              <p className="mt-2 text-xs text-muted">Isi tipe kamar yang tersedia. Kosongkan tipe yang tidak ditawarkan.</p>
              {(Object.keys(ROOM_LABELS) as RoomType[]).map((room) => (
                <FormField key={room} label={`Harga ${ROOM_LABELS[room]}`} htmlFor={`price-${room.toLowerCase()}`} inputMode="numeric" value={roomPrices[room]} onChange={(event) => setRoomPrices((prev) => ({...prev, [room]: event.target.value}))} />
              ))}
              {formErrors.room_prices ? <p className="error-message" role="alert">{formErrors.room_prices}</p> : null}
            </fieldset>
            <fieldset className="my-6 border-t border-border pt-6">
              <legend className="text-sm font-semibold">Varian anak & bayi (opsional)</legend>
              <p className="mt-2 text-xs text-muted">Anak tanpa kasur: usia di bawah 12 tahun saat berangkat. Bayi: di bawah 2 tahun. Kosongkan bila tidak ditawarkan.</p>
              <FormField label="Anak tanpa kasur (Rp)" htmlFor="price-child" inputMode="numeric" value={childPrice} onChange={(event) => setChildPrice(event.target.value)} hint={childPrice ? formatIdr(digits(childPrice)) : undefined} />
              <FormField label="Bayi (Rp)" htmlFor="price-infant" inputMode="numeric" value={infantPrice} onChange={(event) => setInfantPrice(event.target.value)} hint={infantPrice ? formatIdr(digits(infantPrice)) : undefined} />
            </fieldset>
            <FormTextarea label="Layanan tambahan" htmlFor="package-addons" hint="Satu per baris: KODE | Nama | harga per jamaah, mis. KERETA | Kereta cepat Makkah–Madinah | 1200000" value={addonsText} onChange={(event) => setAddonsText(event.target.value)} error={formErrors.addons} />
            <FormTextarea label="Estimasi biaya per jamaah" htmlFor="package-costs" hint="Satu per baris: Kategori | Uraian | jumlah, mis. HOTEL | Hotel Makkah 5 malam | 9000000. Dipakai untuk estimasi margin." value={costsText} onChange={(event) => setCostsText(event.target.value)} error={formErrors.estimated_costs} />
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
            <FormTextarea label="Ketentuan pembayaran" htmlFor="package-payment-terms" value={paymentTerms} onChange={(event) => setPaymentTerms(event.target.value)} />
            <FormTextarea label="Kebijakan pembatalan" htmlFor="package-cancellation-policy" value={cancellationPolicy} onChange={(event) => setCancellationPolicy(event.target.value)} />
            {formErrors.form ? (
              <p className="error-message" role="alert">
                {formErrors.form}
              </p>
            ) : null}
            <div className="form-submit">
              <Btn type="submit" disabled={busy}>
                {busy ? "Menyimpan…" : editing ? "Simpan perubahan" : "Tambah paket"}
              </Btn>
              {editing ? <Btn variant="tint" type="button" className="ml-2" onClick={() => { setEditing(null); setName(""); setPrice(""); setRoomPrices(EMPTY_ROOM_PRICES); setKind("umroh"); setDurationDays(""); setDescription(""); setInclusions(""); setExclusions(""); setCancellationPolicy(""); setPaymentTerms(""); setFormErrors({}); }}>Batal ubah</Btn> : null}
            </div>
          </fieldset></form>
        </section> : null}
      </div>
    </div>
  );
}
