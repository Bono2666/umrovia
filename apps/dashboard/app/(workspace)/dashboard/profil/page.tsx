"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Btn,
  ErrorState,
  FormField,
  FormTextarea,
  LoadingState,
} from "@/components/workspace/ui";
import {
  apiFetch,
  hasPermission,
  problemMessage,
  type SettingsPayload,
  type UserPayload,
} from "@/lib/api";
import { RevealText } from "@/components/marketing/RevealText";

type Section = "branding" | "invoice";
type Draft = { address: string; dueDays: string; notes: string };

const EMPTY: Draft = { address: "", dueDays: "", notes: "" };

function toDraft(settings: SettingsPayload): Draft {
  const dueDays = settings.invoice_config_json.due_days;
  return {
    address: typeof settings.branding_json.address === "string" ? settings.branding_json.address : "",
    dueDays: typeof dueDays === "number" ? String(dueDays) : "",
    notes: typeof settings.invoice_config_json.notes === "string" ? settings.invoice_config_json.notes : "",
  };
}

/**
 * Profil Travel: GET/PATCH /tenant/settings memakai form biasa, bukan JSON.
 * Hanya kunci yang dipakai dokumen yang diedit (alamat, jatuh tempo, catatan
 * invoice); kunci lain yang sudah tersimpan dipertahankan saat menyimpan.
 * Aturan DP memiliki form sendiri di halaman Invoice.
 */
export default function ProfilPage() {
  const [settings, setSettings] = useState<SettingsPayload | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [travelName, setTravelName] = useState("");
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const [messages, setMessages] = useState<Record<Section, string | null>>({ branding: null, invoice: null });
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [readOnly, setReadOnly] = useState(false);
  const [busy, setBusy] = useState<Section | null>(null);

  const load = useCallback(() => {
    apiFetch<UserPayload>("/me").then((result) => {
      if (!result.ok) {
        setGlobalError("Sesi berakhir. Silakan login ulang.");
        return;
      }
      const { memberships, active_tenant_slug } = result.data;
      const active =
        memberships.find((m) => m.tenant.slug === (active_tenant_slug ?? "")) ??
        memberships.find((m) => m.status === "ACTIVE");
      setTravelName(active?.tenant.display_name ?? "");
      setReadOnly(!hasPermission(active?.permissions ?? [], "tenant.settings.write"));
    });
    apiFetch<SettingsPayload>("/tenant/settings").then((result) => {
      if (result.ok) {
        setSettings(result.data);
        setDraft(toDraft(result.data));
      } else if (result.error.status === 403) {
        setReadOnly(true);
        setGlobalError("Peran Anda tidak memiliki akses ke pengaturan travel.");
      } else {
        setGlobalError(problemMessage(result.error));
      }
    });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const saved = settings ? toDraft(settings) : EMPTY;
  const changed = {
    branding: draft.address !== saved.address,
    invoice: draft.dueDays !== saved.dueDays || draft.notes !== saved.notes,
  };

  function update(field: keyof Draft, value: string, section: Section) {
    setDraft((prev) => ({ ...prev, [field]: value }));
    setErrors((prev) => ({ ...prev, [field]: null }));
    setMessages((prev) => ({ ...prev, [section]: null }));
  }

  function reset(section: Section) {
    setDraft((prev) => section === "branding" ? { ...prev, address: saved.address } : { ...prev, dueDays: saved.dueDays, notes: saved.notes });
    setErrors({});
    setMessages((prev) => ({ ...prev, [section]: null }));
  }

  async function save(section: Section) {
    if (!settings) return;
    let body: Partial<SettingsPayload>;
    if (section === "branding") {
      const branding: Record<string, unknown> = { ...settings.branding_json };
      if (draft.address.trim()) branding.address = draft.address.trim();
      else delete branding.address;
      body = { branding_json: branding };
    } else {
      const config: Record<string, unknown> = { ...settings.invoice_config_json };
      const raw = draft.dueDays.trim();
      if (raw === "") {
        delete config.due_days;
      } else {
        const days = Number(raw);
        if (!Number.isInteger(days) || days < 0 || days > 365) {
          setErrors({ dueDays: "Isi bilangan bulat 0–365 hari." });
          return;
        }
        config.due_days = days;
      }
      if (draft.notes.trim()) config.notes = draft.notes.trim();
      else delete config.notes;
      body = { invoice_config_json: config };
    }
    setBusy(section);
    const result = await apiFetch<SettingsPayload>("/tenant/settings", { method: "PATCH", body: JSON.stringify(body) });
    setBusy(null);
    if (!result.ok) {
      setMessages((prev) => ({ ...prev, [section]: problemMessage(result.error) }));
      return;
    }
    setSettings(result.data);
    setDraft(toDraft(result.data));
    setMessages((prev) => ({ ...prev, [section]: "Tersimpan." }));
  }

  function actions(section: Section) {
    if (readOnly) return null;
    const message = messages[section];
    return (
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <Btn disabled={busy === section || !changed[section]} onClick={() => save(section)}>
          {busy === section ? "Menyimpan…" : "Simpan"}
        </Btn>
        {changed[section] ? <Btn variant="tint" disabled={busy === section} onClick={() => reset(section)}>Batal ubah</Btn> : null}
        {message ? (
          <span className={`text-xs ${message === "Tersimpan." ? "text-success" : "text-danger"}`} role="status">
            {message}
          </span>
        ) : null}
      </div>
    );
  }

  return (
    <div className="workspace-page">
      <RevealText as="h1" variant="title" className="text-2xl font-bold">Profil Travel</RevealText>
      <p className="mt-1 text-sm text-muted">
        Informasi travel yang dicetak pada invoice dan kuitansi, serta pengaturan bawaan untuk invoice baru.
      </p>
      {readOnly && !globalError ? (
        <p className="mt-4 border border-border p-3 text-sm text-muted">
          Mode baca — hanya Owner atau Admin yang dapat mengubah pengaturan travel.
        </p>
      ) : null}
      {globalError ? (
        <div className="mt-4">
          <ErrorState message={globalError} onRetry={load} />
        </div>
      ) : null}

      {settings === null && !globalError ? (
        <div className="mt-6">
          <LoadingState label="Memuat pengaturan…" />
        </div>
      ) : settings ? (
        <div className="workspace-columns mt-6">
          <section className="card p-6">
            <h2 className="font-semibold">Identitas pada dokumen</h2>
            <p className="mt-1 text-sm text-muted">
              Nama dan telepon {travelName ? <strong>{travelName}</strong> : "travel"} mengikuti data pendaftaran. Alamat di bawah dicetak sebagai penerbit invoice dan kuitansi.
            </p>
            <FormTextarea
              label="Alamat travel"
              htmlFor="profile-address"
              value={draft.address}
              maxLength={300}
              readOnly={readOnly}
              onChange={(event) => update("address", event.target.value, "branding")}
              hint="Contoh: Jl. Raya Haji No. 12, Jakarta Selatan 12345."
            />
            {actions("branding")}
          </section>

          <section className="card p-6">
            <h2 className="font-semibold">Invoice</h2>
            <p className="mt-1 text-sm text-muted">Berlaku untuk invoice yang diterbitkan berikutnya; invoice lama tidak berubah.</p>
            <FormField
              label="Jatuh tempo bawaan (hari)"
              htmlFor="profile-due-days"
              inputMode="numeric" thousands
              value={draft.dueDays}
              readOnly={readOnly}
              error={errors.dueDays}
              onChange={(event) => update("dueDays", event.target.value, "invoice")}
              hint="Jumlah hari setelah invoice terbit. Kosongkan untuk memakai 7 hari."
            />
            <FormTextarea
              label="Catatan pada invoice"
              htmlFor="profile-notes"
              value={draft.notes}
              maxLength={1000}
              readOnly={readOnly}
              onChange={(event) => update("notes", event.target.value, "invoice")}
              hint="Misalnya instruksi pembayaran atau ketentuan singkat."
            />
            {actions("invoice")}
          </section>

          <section className="card p-6">
            <h2 className="font-semibold">Aturan pembayaran DP</h2>
            <p className="mt-1 text-sm text-muted">
              Target minimum DP dan pemisahan pencatat–verifikator diatur di halaman Invoice.
            </p>
            <Link className="mt-4 inline-block text-sm text-primary underline" href="/dashboard/invoice">Buka aturan DP</Link>
          </section>
        </div>
      ) : null}
    </div>
  );
}
