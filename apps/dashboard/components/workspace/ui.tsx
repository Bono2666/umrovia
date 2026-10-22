/**
 * Komponen dasar workspace (S06, Spec §4.2: form, tabel, empty/loading/error
 * state, validasi inline). Satu file kecil berisi primitif dipakai semua
 * halaman dashboard.
 */
import type { ReactNode } from "react";

export function LoadingState({ label = "Memuat…" }: { label?: string }) {
  return (
    <div className="card p-8 text-center text-sm text-muted" role="status">
      {label}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="card p-8 text-center">
      <p className="font-semibold">{title}</p>
      {description ? (
        <p className="mt-1 text-sm text-muted">{description}</p>
      ) : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className="card border-danger/30 p-6 text-sm text-danger"
      role="alert"
    >
      <p>{message}</p>
      {onRetry ? (
        <button type="button" onClick={onRetry} className="mt-3 text-xs font-semibold underline">
          Coba lagi
        </button>
      ) : null}
    </div>
  );
}

/** Status chip teks (§4.3: status memakai teks, bukan warna saja). */
export function StatusBadge({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "success" | "warning" | "danger";
  children: ReactNode;
}) {
  const tones: Record<string, string> = {
    neutral: "text-muted border-border",
    success: "text-success border-success/30 bg-success/10",
    warning: "text-warning border-warning/30 bg-warning/10",
    danger: "text-danger border-danger/30 bg-danger/10",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

/**
 * Field form dengan label + error inline (Spec §4.2 — validasi inline;
 * pesan error tampil di bawah field terkait, bukan hanya alert global).
 */
export function FormField({
  label,
  htmlFor,
  error,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  error?: string | null;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="block text-sm font-semibold">
        {label}
      </label>
      {hint ? <p className="mt-0.5 text-xs text-muted">{hint}</p> : null}
      <div className="mt-1">{children}</div>
      {error ? (
        <p className="mt-1 text-xs text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export const BTN_SECONDARY =
  "rounded border border-border bg-surface px-3 py-1.5 text-sm font-semibold hover:bg-background";

export const BTN_DANGER =
  "rounded border border-danger/30 bg-danger/10 px-3 py-1.5 text-sm font-semibold text-danger hover:bg-danger/20";
