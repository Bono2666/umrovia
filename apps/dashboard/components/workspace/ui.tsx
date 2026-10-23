/**
 * Komponen dasar workspace (S06, Spec §4.2: form, tabel, empty/loading/error
 * state, validasi inline) — termasuk port 1:1 form kontak web_template
 * (label mengambang, garis hairline, progress line; lihat globals.css).
 */
import { useState } from "react";
import type {
  AnchorHTMLAttributes,
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import Link from "next/link";

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
        <Btn variant="link" size="xs" className="mt-3" onClick={onRetry}>
          Coba lagi
        </Btn>
      ) : null}
    </div>
  );
}

/** Status chip teks (§4.3: status memakai teks, bukan warna saja).
 * Gaya editorial: persegi, hairline border. */
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
      className={`inline-flex items-center border px-1.5 py-0.5 text-[0.7rem] font-semibold uppercase tracking-wide ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

/* ==========================================================================
   Form control — PORT 1:1 form kontak web_template.

   Struktur DOM persis sumber:
   `.form-group > .form-control.form-control--input.form-control--float >
    input + label.form-label + span.form-control__line + span.form-control__progress`.

   State wrapper (setara plugin `inputState` template, event
   input/change/focus/blur):
   - `is-focused` → label naik + progress line menggambar saat fokus
     (input & textarea; select sengaja dikecualikan CSS sumber)
   - `is-not-empty` → nilai trim non-kosong (label tetap naik walau blur);
     select selalu dianggap terisi (setara cek appearance menulist-button)
   - `form-control--error` → garis dasar diganti coretan bergelombang
   ========================================================================== */

type FormControlLabelProps = {
  label?: string;
  htmlFor: string;
  error?: string | null;
  hint?: string;
};

function controlClass(
  kind: "input" | "select" | "textarea",
  focused: boolean,
  notEmpty: boolean,
  error: string | null | undefined,
  withSuffix: boolean,
): string {
  return [
    "form-control",
    `form-control--${kind}`,
    "form-control--float",
    focused ? "is-focused" : "",
    notEmpty ? "is-not-empty" : "",
    error ? "form-control--error" : "",
    withSuffix ? "form-control--with-suffix" : "",
  ]
    .filter(Boolean)
    .join(" ");
}

/** Kerangka field: form-group (ritme 55px) > control + hint/error. */
function ControlShell({
  wrapperClass,
  id,
  label,
  children,
  hint,
  error,
}: {
  wrapperClass: string;
  id: string;
  label?: string;
  children: ReactNode;
  hint?: string;
  error?: string | null;
}) {
  return (
    <div className="form-group">
      <div className={wrapperClass}>
        {children}
        {label ? (
          <label htmlFor={id} className="form-label">
            {label}
          </label>
        ) : null}
        <span className="form-control__line" aria-hidden="true" />
        <span className="form-control__progress" aria-hidden="true" />
      </div>
      {hint ? <p className="form-control__hint">{hint}</p> : null}
      {error ? (
        <p className="error-message" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** Input teks float-label (email, password, nama, dst.). */
export function FormField({
  label,
  htmlFor,
  error,
  hint,
  suffix,
  className,
  value,
  onFocus,
  onBlur,
  onInput,
  ...rest
}: Omit<InputHTMLAttributes<HTMLInputElement>, "children"> &
  FormControlLabelProps & {
    suffix?: ReactNode;
  }) {
  const [focused, setFocused] = useState(false);
  const [typed, setTyped] = useState(false);
  const notEmpty =
    value !== undefined ? String(value).trim().length > 0 : typed;

  return (
    <ControlShell
      wrapperClass={controlClass(
        "input",
        focused,
        notEmpty,
        error,
        suffix !== undefined,
      )}
      id={htmlFor}
      label={label}
      hint={hint}
      error={error}
    >
      <input
        id={htmlFor}
        className={className}
        value={value}
        aria-invalid={error ? true : undefined}
        onFocus={(event) => {
          setFocused(true);
          onFocus?.(event);
        }}
        onBlur={(event) => {
          setFocused(false);
          onBlur?.(event);
        }}
        onInput={(event) => {
          setTyped(event.currentTarget.value.trim().length > 0);
          onInput?.(event);
        }}
        {...rest}
      />
      {suffix !== undefined ? (
        <span className="form-control__suffix">{suffix}</span>
      ) : null}
    </ControlShell>
  );
}

/** Textarea float-label (sama seperti input; tinggi 64px, resize vertikal). */
export function FormTextarea({
  label,
  htmlFor,
  error,
  hint,
  className,
  value,
  onFocus,
  onBlur,
  onInput,
  ...rest
}: Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "children"> &
  FormControlLabelProps) {
  const [focused, setFocused] = useState(false);
  const [typed, setTyped] = useState(false);
  const notEmpty =
    value !== undefined ? String(value).trim().length > 0 : typed;

  return (
    <ControlShell
      wrapperClass={controlClass("textarea", focused, notEmpty, error, false)}
      id={htmlFor}
      label={label}
      hint={hint}
      error={error}
    >
      <textarea
        id={htmlFor}
        className={className}
        value={value}
        aria-invalid={error ? true : undefined}
        onFocus={(event) => {
          setFocused(true);
          onFocus?.(event);
        }}
        onBlur={(event) => {
          setFocused(false);
          onBlur?.(event);
        }}
        onInput={(event) => {
          setTyped(event.currentTarget.value.trim().length > 0);
          onInput?.(event);
        }}
        {...rest}
      />
    </ControlShell>
  );
}

/** Select float-label; `label` opsional (select tanpa label visual,
 * mis. peran baris tabel / pemilih workspace). Select selalu terisi. */
export function FormSelect({
  label,
  htmlFor,
  error,
  hint,
  className,
  onFocus,
  onBlur,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & FormControlLabelProps) {
  const [focused, setFocused] = useState(false);

  return (
    <ControlShell
      wrapperClass={controlClass("select", focused, true, error, false)}
      id={htmlFor}
      label={label}
      hint={hint}
      error={error}
    >
      <select
        id={htmlFor}
        className={className}
        aria-invalid={error ? true : undefined}
        onFocus={(event) => {
          setFocused(true);
          onFocus?.(event);
        }}
        onBlur={(event) => {
          setFocused(false);
          onBlur?.(event);
        }}
        {...rest}
      />
    </ControlShell>
  );
}

/** Checkbox bulat 20px (.form-control-checkbox — centang SVG data-uri). */
export function FormCheckbox({
  id,
  label,
  checked,
  onChange,
  disabled,
  required,
}: {
  id: string;
  label: ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  required?: boolean;
}) {
  return (
    <div className="form-control-checkbox">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        required={required}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="form-control-checkbox__icon" aria-hidden="true" />
      <label className="form-control-checkbox__label" htmlFor={id}>
        {label}
      </label>
    </div>
  );
}

/**
 * Tombol — sistem `.btn` web_template (lihat globals.css untuk port CSS 1:1).
 *
 * Struktur DOM persis template: `.btn > .btn__inner > .btn__content > .btn__text`
 * dengan `.btn__content` ganda (yang kedua `aria-hidden`): template meng-klon
 * konten via JS saat runtime (`btn--cloned`) untuk animasi teks berguling
 * saat hover; kami merender duplikatnya secara statis. `<span class="spinner">`
 * dirender di kedua content (klon = salinan content di template).
 *
 * Varian (dipetakan ke kelas template):
 * - "solid"  = CTA utama, pill ink pekat (template `btn--secondary` light)
 * - "tint"   = aksi sekunder, tint + slide-fill (template `btn--primary`)
 * - "danger" = destruktif, mekanisme sama, nada danger
 * - "link"   = tautan bergaya (template `btn--link`)
 *
 * Ukuran opsional; tanpa `size` = tombol default template (30px/16px).
 * `size="circle-xl"` = submit form kontak (lingkaran 120px, `btn--start`
 * + `btn--large-circle`); prop `loading` menyalakan `.is-loading` → spinner.
 */
export type BtnVariant = "solid" | "tint" | "danger" | "link";
export type BtnSize = "xs" | "sm" | "md" | "lg" | "circle" | "circle-xl";

const BTN_VARIANT_CLASS: Record<BtnVariant, string> = {
  solid: "btn--secondary",
  tint: "btn--primary",
  danger: "btn--danger",
  link: "btn--link",
};

const BTN_SIZE_CLASS: Record<BtnSize, string> = {
  xs: "btn--xs",
  sm: "btn--sm",
  md: "btn--md",
  lg: "btn--lg",
  circle: "btn--circle-xs",
  "circle-xl": "btn--circle-xl btn--large-circle btn--start",
};

function btnClass(
  variant: BtnVariant,
  size: BtnSize | undefined,
  className?: string,
): string {
  return [
    "btn",
    BTN_VARIANT_CLASS[variant],
    size ? BTN_SIZE_CLASS[size] : "",
    "btn--animated-content",
    "btn--cloned",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");
}

function BtnInner({ children }: { children: ReactNode }) {
  return (
    <span className="btn__inner">
      <span className="btn__content">
        <span className="btn__text">{children}</span>
        <span className="spinner" aria-hidden="true" />
      </span>
      <span className="btn__content" aria-hidden="true">
        <span className="btn__text">{children}</span>
        <span className="spinner" aria-hidden="true" />
      </span>
    </span>
  );
}

export function Btn({
  variant = "solid",
  size,
  className,
  children,
  type = "button",
  loading = false,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: BtnVariant;
  size?: BtnSize;
  loading?: boolean;
}) {
  return (
    <button
      type={type}
      className={btnClass(
        variant,
        size,
        [loading ? "is-loading" : "", className ?? ""]
          .filter(Boolean)
          .join(" "),
      )}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      <BtnInner>{children}</BtnInner>
    </button>
  );
}

export function BtnLink({
  variant = "solid",
  size,
  className,
  children,
  ...rest
}: AnchorHTMLAttributes<HTMLAnchorElement> & {
  variant?: BtnVariant;
  size?: BtnSize;
  href: string;
}) {
  return (
    <Link className={btnClass(variant, size, className)} {...rest}>
      <BtnInner>{children}</BtnInner>
    </Link>
  );
}
