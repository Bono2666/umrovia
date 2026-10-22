"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ErrorState,
  FormField,
  LoadingState,
} from "@/components/workspace/ui";
import {
  apiFetch,
  hasPermission,
  problemMessage,
  type SettingsPayload,
  type UserPayload,
} from "@/lib/api";

type SectionKey = "branding_json" | "invoice_config_json" | "rules_json";

const SECTIONS: { key: SectionKey; label: string; hint: string }[] = [
  {
    key: "branding_json",
    label: "Branding",
    hint: "Identitas visual travel pada dokumen (mis. logo_url, primary_color). Maks 16KB.",
  },
  {
    key: "invoice_config_json",
    label: "Konfigurasi invoice",
    hint: "Pengaturan dokumen (mis. due_days, notes, pajak). Maks 16KB.",
  },
  {
    key: "rules_json",
    label: "Aturan operasional",
    hint: "Aturan bisnis travel (mis. batas DP, kebijakan refund). Maks 16KB.",
  },
];

/**
 * Profil Travel (S06, §4.1): GET/PATCH /tenant/settings — tiga bagian
 * config JSON bebas (branding, invoice, rules; §5.1). Validasi JSON inline
 * per bagian; simpan per bagian (PATCH hanya mengganti bagian yang dikirim).
 */
export default function ProfilPage() {
  const [values, setValues] = useState<Record<SectionKey, string> | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string | null>>({});
  const [messages, setMessages] = useState<Record<string, string | null>>({});
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [readOnly, setReadOnly] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);

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
      setReadOnly(!hasPermission(active?.permissions ?? [], "tenant.settings.write"));
    });
    apiFetch<SettingsPayload>("/tenant/settings").then((result) => {
      if (result.ok) {
        setValues({
          branding_json: JSON.stringify(result.data.branding_json, null, 2),
          invoice_config_json: JSON.stringify(result.data.invoice_config_json, null, 2),
          rules_json: JSON.stringify(result.data.rules_json, null, 2),
        });
      } else if (result.error.status === 403) {
        setReadOnly(true);
        setValues({ branding_json: "{}", invoice_config_json: "{}", rules_json: "{}" });
      } else {
        setGlobalError(problemMessage(result.error));
      }
    });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function validate(key: SectionKey, text: string): Record<string, unknown> | null {
    try {
      const parsed: unknown = JSON.parse(text || "{}");
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        setFieldErrors((prev) => ({ ...prev, [key]: "Harus berupa objek JSON { }." }));
        return null;
      }
      if (new Blob([text]).size > 16_384) {
        setFieldErrors((prev) => ({ ...prev, [key]: "Ukuran maksimal 16KB." }));
        return null;
      }
      setFieldErrors((prev) => ({ ...prev, [key]: null }));
      return parsed as Record<string, unknown>;
    } catch {
      setFieldErrors((prev) => ({ ...prev, [key]: "JSON tidak valid — periksa koma/tanda kurung." }));
      return null;
    }
  }

  async function onSave(key: SectionKey) {
    const text = values?.[key] ?? "{}";
    const parsed = validate(key, text);
    if (parsed === null) return;
    setBusyKey(key);
    setMessages((prev) => ({ ...prev, [key]: null }));
    const result = await apiFetch<SettingsPayload>("/tenant/settings", {
      method: "PATCH",
      body: JSON.stringify({ [key]: parsed }),
    });
    setBusyKey(null);
    if (!result.ok) {
      setMessages((prev) => ({ ...prev, [key]: problemMessage(result.error) }));
      return;
    }
    setMessages((prev) => ({ ...prev, [key]: "Tersimpan." }));
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-bold">Profil Travel</h1>
      <p className="mt-1 text-sm text-muted">
        Konfigurasi workspace (§5.1): branding dokumen, pengaturan invoice, dan
        aturan operasional. Setiap bagian berupa objek JSON.
      </p>
      {readOnly ? (
        <p className="mt-4 rounded border border-border bg-surface p-3 text-sm text-muted">
          Mode baca — peran Anda tidak memiliki <code>tenant.settings.write</code>.
        </p>
      ) : null}
      {globalError ? (
        <div className="mt-4">
          <ErrorState message={globalError} onRetry={load} />
        </div>
      ) : null}

      {values === null && !globalError ? (
        <div className="mt-6">
          <LoadingState label="Memuat pengaturan…" />
        </div>
      ) : (
        SECTIONS.map((section) => (
          <section key={section.key} className="card mt-4 p-6">
            <h2 className="font-semibold">{section.label}</h2>
            <div className="mt-3">
              <FormField
                label={section.label}
                htmlFor={section.key}
                hint={section.hint}
                error={fieldErrors[section.key]}
              >
                <textarea
                  id={section.key}
                  className="input min-h-40 font-mono text-sm"
                  value={values?.[section.key] ?? ""}
                  onChange={(event) => {
                    const text = event.target.value;
                    setValues((prev) => (prev ? { ...prev, [section.key]: text } : prev));
                    setMessages((prev) => ({ ...prev, [section.key]: null }));
                  }}
                  onBlur={() => values && validate(section.key, values[section.key])}
                  readOnly={readOnly}
                  spellCheck={false}
                />
              </FormField>
            </div>
            <div className="mt-3 flex items-center gap-3">
              {readOnly ? null : (
                <button
                  type="button"
                  className="btn-primary"
                  disabled={busyKey === section.key}
                  onClick={() => onSave(section.key)}
                >
                  {busyKey === section.key ? "Menyimpan…" : "Simpan"}
                </button>
              )}
              {messages[section.key] ? (
                <span
                  className={`text-xs ${
                    messages[section.key] === "Tersimpan." ? "text-success" : "text-danger"
                  }`}
                  role="status"
                >
                  {messages[section.key]}
                </span>
              ) : null}
            </div>
          </section>
        ))
      )}

      <p className="mt-4 text-xs text-muted">
        Nilai config dipakai modul menyusul: branding & invoice → template
        dokumen (S06 fondasi, endpoint PDF S11); rules → guard operasional.
      </p>
    </div>
  );
}
