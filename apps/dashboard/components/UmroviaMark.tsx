type UmroviaMarkProps = {
  className?: string;
};

/**
 * Monogram Umrovia — mengikuti logo referensi: lingkaran solid soft-black
 * (`--brand-ink`, padanan `--c-black` web_template) dengan inisial putih
 * huruf kecil "um" (Poppins 700, tracking -0.035em, rasio 0.53×diameter —
 * konsisten dengan `app/favicon.ico`).
 *
 * Berupa SVG inline agar tajam di segala DPI dan memakai font halaman
 * (`var(--font-poppins)` dari next/font/local di `<html>`).
 */
export function UmroviaMark({ className = "h-7 w-7" }: UmroviaMarkProps) {
  return (
    <svg
      viewBox="0 0 32 32"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      <circle cx="16" cy="16" r="16" fill="var(--brand-ink)" />
      <text
        x="16"
        y="16"
        textAnchor="middle"
        dominantBaseline="central"
        fill="#fff"
        fontSize={17}
        fontWeight={700}
        letterSpacing="-0.035em"
        style={{ fontFamily: "var(--font-poppins), sans-serif" }}
      >
        um
      </text>
    </svg>
  );
}
