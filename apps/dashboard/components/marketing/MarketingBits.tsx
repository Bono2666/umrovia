/**
 * Elemen dekoratif halaman marketing (landing `/`, tema web_template).
 *
 * Semua animasi memakai pola roll yang sama dengan sidebar workspace:
 * dua lapis konten bergeser -100% pada hover dengan `--ease-editorial`,
 * dan dinetralkan oleh prefers-reduced-motion.
 */

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

export type MockKind =
  | "list"
  | "profile"
  | "progress"
  | "invoice"
  | "chart"
  | "team"
  | "check";

const LIST_ROWS: Array<{ width: string; active?: boolean }> = [
  { width: "w-5/6", active: true },
  { width: "w-3/4" },
  { width: "w-4/5" },
  { width: "w-2/3" },
  { width: "w-1/2" },
];

const CHECK_ROWS: Array<{ done: boolean; width: string }> = [
  { done: true, width: "w-2/3" },
  { done: true, width: "w-1/2" },
  { done: false, width: "w-3/5" },
  { done: false, width: "w-2/5" },
];

const CHART_BARS = [38, 55, 88, 62, 74, 48];

function MockArt({ kind }: { kind: MockKind }) {
  switch (kind) {
    case "list":
      return (
        <ul className="flex h-full flex-col gap-2">
          {LIST_ROWS.map((row, i) => (
            <li
              key={i}
              className={`flex items-center gap-2.5 rounded px-2 ${
                row.active ? "bg-white" : ""
              }`}
            >
              <span
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                  row.active ? "bg-[#0e6b5c]" : "bg-black/20"
                }`}
              />
              <span
                className={`h-2 rounded-full ${
                  row.active ? "bg-black/45" : "bg-black/15"
                } ${row.width}`}
              />
            </li>
          ))}
        </ul>
      );
    case "profile":
      return (
        <div className="flex h-full flex-col gap-3">
          <div className="flex items-center gap-3">
            <span className="h-9 w-9 rounded-full bg-black/15" />
            <span className="flex flex-col gap-1.5">
              <span className="h-2.5 w-24 rounded-full bg-black/45" />
              <span className="h-2 w-16 rounded-full bg-black/15" />
            </span>
          </div>
          <span className="mt-1 h-2 w-full rounded-full bg-black/10" />
          <span className="h-2 w-5/6 rounded-full bg-black/10" />
          <span className="h-2 w-2/3 rounded-full bg-black/10" />
          <span className="mt-auto h-4 w-24 self-start rounded-full bg-black/10" />
        </div>
      );
    case "progress":
      return (
        <div className="flex h-full flex-col">
          <span className="h-2.5 w-24 rounded-full bg-black/45" />
          <span className="mt-3 h-5 w-28 rounded-[3px] bg-[#191b1d]" />
          <span className="mt-3 block h-1.5 w-full overflow-hidden rounded-full bg-black/10">
            <span
              className="block h-full w-2/3 rounded-full"
              style={{ background: "var(--brand-primary)" }}
            />
          </span>
          <span className="mt-auto flex items-center justify-between">
            <span className="h-2 w-16 rounded-full bg-black/15" />
            <span className="h-2 w-10 rounded-full bg-black/15" />
          </span>
        </div>
      );
    case "invoice":
      return (
        <div className="flex h-full flex-col gap-2.5">
          <span className="flex items-center justify-between">
            <span className="h-2.5 w-20 rounded-full bg-black/45" />
            <span className="h-4 w-16 rounded-full bg-[#0e6b5c]/20" />
          </span>
          <span className="h-px w-full bg-black/10" />
          <span className="h-2 w-full rounded-full bg-black/10" />
          <span className="h-2 w-4/5 rounded-full bg-black/10" />
          <span className="mt-auto h-2 w-1/2 rounded-full bg-black/10" />
          <span className="h-5 w-24 rounded-[3px] bg-[#191b1d]" />
        </div>
      );
    case "chart":
      return (
        <div className="flex h-full items-end gap-2">
          {CHART_BARS.map((height, i) => (
            <span
              key={i}
              className={`flex-1 rounded-[2px] ${
                i === 2 ? "bg-[#191b1d]" : "bg-black/12"
              }`}
              style={{ height: `${height}%` }}
            />
          ))}
        </div>
      );
    case "team":
      return (
        <div className="flex h-full flex-col gap-3">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="flex items-center gap-3 rounded-[4px] bg-white px-3 py-2"
            >
              <span className="h-7 w-7 shrink-0 rounded-full bg-black/12" />
              <span className="h-2 w-20 rounded-full bg-black/25" />
              <span className="ml-auto h-4 w-14 shrink-0 rounded-full bg-black/10" />
            </span>
          ))}
        </div>
      );
    case "check":
      return (
        <div className="flex h-full flex-col justify-between">
          {CHECK_ROWS.map((row, i) => (
            <span key={i} className="flex items-center gap-2.5">
              <span
                className={`grid h-3.5 w-3.5 shrink-0 place-items-center rounded-[3px] border ${
                  row.done ? "border-[#191b1d] bg-[#191b1d]" : "border-black/25"
                }`}
              >
                {row.done && (
                  <svg
                    viewBox="0 0 10 10"
                    className="h-2 w-2 text-white"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M2 5.2 4 7.2 8 2.8" />
                  </svg>
                )}
              </span>
              <span
                className={`h-2 rounded-full ${
                  row.done ? "bg-black/25" : "bg-black/12"
                } ${row.width}`}
              />
            </span>
          ))}
        </div>
      );
  }
}

/**
 * Kartu "tangkapan layar" — padanan thumbnail proyek pada segmen expertise
 * template: bidang seni (mock UI abstrak) di atas, nama + tag di bawah,
 * dibingkai hairline.
 */
export function MockCard({
  kind,
  title,
  tags,
}: {
  kind: MockKind;
  title: string;
  tags: string;
}) {
  return (
    <figure className="rounded-[6px] border border-black/10 bg-white p-5 md:p-6">
      <div className="h-40 overflow-hidden rounded-[4px] bg-[#f2f2f3] p-4 md:h-44">
        <MockArt kind={kind} />
      </div>
      <figcaption className="mt-4 md:mt-5">
        <p className="text--t2-short">{title}</p>
        <p className="mt-1 text--t3-sm text--color-small">{tags}</p>
      </figcaption>
    </figure>
  );
}
