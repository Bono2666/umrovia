/**
 * Elemen dekoratif halaman marketing (landing `/`, tema web_template).
 *
 * Semua animasi memakai pola roll yang sama dengan sidebar workspace:
 * dua lapis konten bergeser -100% pada hover dengan `--ease-editorial`,
 * dan dinetralkan oleh prefers-reduced-motion.
 */
import Image from "next/image";

const ROLL =
  "transition-transform duration-[600ms] ease-[cubic-bezier(.25,.74,.22,.99)] motion-reduce:transition-none";

/** Badge lingkaran bernomor "01" (padanan counter segmen template). */
export function NumberBadge({ n }: { n: string }) {
  return (
    <span className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-full bg-primary text-[11px] font-semibold leading-none tracking-[-0.02em] text-white">
      {n}
    </span>
  );
}

export function ArrowGlyph() {
  return (
    <svg
      viewBox="0 0 16 16"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M8 3v10M4 9l4 4 4-4" />
    </svg>
  );
}

/**
 * Tombol lingkaran berisi panah bawah — roll dua panah (satuan bergulir
 * keluar ke atas, berikutnya masuk dari bawah) ala panah awards/capabilities
 * template. Area potong dan jarak gulir mengikuti diameter lingkaran, bukan
 * ukuran SVG. Letakkan pada elemen induk berkelas `group`.
 */
export function CircleArrow({ className = "" }: { className?: string }) {
  return (
    <span
      className={`grid h-10 w-10 shrink-0 place-items-center rounded-full bg-[#e4e4e4] text-[#191b1d] ${className}`}
      aria-hidden="true"
    >
      <span className="relative block h-full w-full overflow-hidden rounded-full">
        <span
          className={`absolute inset-x-0 top-0 flex flex-col ${ROLL} group-hover:-translate-y-1/2 group-focus-visible:-translate-y-1/2`}
        >
          <span className="grid h-10 w-10 shrink-0 place-items-center"><ArrowGlyph /></span>
          <span className="grid h-10 w-10 shrink-0 place-items-center"><ArrowGlyph /></span>
        </span>
      </span>
    </span>
  );
}

/**
 * Kartu tangkapan layar — padanan thumbnail proyek pada segmen expertise
 * template: potongan layar Umrovia sungguhan (data demo fiktif, lihat
 * docs/runbooks/MARKETING_SCREENSHOTS.md) di atas, nama + tag di bawah, dibingkai hairline.
 */
export function ScreenCard({
  src,
  alt,
  title,
  tags,
}: {
  src: string;
  alt: string;
  title: string;
  tags: string;
}) {
  return (
    <figure className="rounded-[6px] border border-black/10 bg-white p-5 md:p-6">
      <div className="aspect-[16/10] overflow-hidden rounded-[4px] border border-black/10 bg-[#f2f2f3]">
        <Image
          src={src}
          alt={alt}
          width={880}
          height={550}
          unoptimized
          className="h-full w-full object-cover object-left-top"
        />
      </div>
      <figcaption className="mt-4 md:mt-5">
        <p className="text--t2-short">{title}</p>
        <p className="mt-1 text--t3-sm text--color-small">{tags}</p>
      </figcaption>
    </figure>
  );
}
