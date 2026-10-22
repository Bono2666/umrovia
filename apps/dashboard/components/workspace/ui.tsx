/**
 * Komponen dasar workspace (S06, Spec §4.2: form, tabel, empty/loading/error
 * state, validasi inline). Satu file kecil berisi primitif dipakai semua
 * halaman dashboard.
 */
import type {
  AnchorHTMLAttributes,
  ButtonHTMLAttributes,
  ReactNode,
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

/**
 * Tombol — sistem `.btn` web_template (lihat globals.css untuk port CSS 1:1).
 *
 * Struktur DOM persis template: `.btn > .btn__inner > .btn__content > .btn__text`,
 * dengan `.btn__content` ganda (yang kedua `aria-hidden`): template meng-klon
 * konten via JS saat runtime (`btn--cloned`) untuk animasi teks berguling
 * saat hover; kami merender duplikatnya secara statis.
 *
 * Varian (dipetakan ke kelas template):
 * - "solid"  = CTA utama, pill ink pekat (template `btn--secondary` light)
 * - "tint"   = aksi sekunder, tint + slide-fill (template `btn--primary`)
 * - "danger" = destruktif, mekanisme sama, nada danger
 * - "link"   = tautan bergaya (template `btn--link`)
 *
 * Ukuran opsional; tanpa `size` = tombol default template (30px/16px).
 */
export type BtnVariant = "solid" | "tint" | "danger" | "link";
export type BtnSize = "xs" | "sm" | "md" | "lg" | "circle";

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
      </span>
      <span className="btn__content" aria-hidden="true">
        <span className="btn__text">{children}</span>
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
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: BtnVariant;
  size?: BtnSize;
}) {
  return (
    <button
      type={type}
      className={btnClass(variant, size, className)}
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
