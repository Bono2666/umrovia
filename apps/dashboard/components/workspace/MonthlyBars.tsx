"use client";

import { useState } from "react";

type Point = { label: string; value: number };

/** Ringkas: 1.250.000 → "1,3 jt", 2.500.000.000 → "2,5 M". */
export function compactIdr(value: number) {
  const abs = Math.abs(value);
  const fmt = (n: number) => n.toLocaleString("id-ID", {maximumFractionDigits: 1});
  if (abs >= 1e9) return `${fmt(value / 1e9)} M`;
  if (abs >= 1e6) return `${fmt(value / 1e6)} jt`;
  if (abs >= 1e3) return `${fmt(value / 1e3)} rb`;
  return fmt(value);
}

/**
 * Grafik kolom satu seri per bulan (MOD-02). Satu warna (primary) sehingga tanpa
 * legenda; judul menamai seri. Kolom ≤ 24px dengan ujung membulat 4px, grid
 * hairline, tooltip saat hover/fokus pada area kolom penuh, dan tabel data
 * sebagai tampilan aksesibel.
 */
export function MonthlyBars({ title, points, format, unit }: { title: string; points: Point[]; format: (value: number) => string; unit: string }) {
  const [active, setActive] = useState<number | null>(null);
  const max = Math.max(...points.map((p) => p.value), 0);
  const top = max > 0 ? niceCeil(max) : 1;
  const ticks = [top, top / 2, 0];
  const last = points.length - 1;
  return <figure className="min-w-0">
    <figcaption className="text-sm font-semibold">{title}</figcaption>
    <div className="relative mt-4 flex gap-2" style={{height: 180}}>
      <div className="flex w-12 shrink-0 flex-col justify-between text-right text-[0.7rem] tabular-nums text-muted" aria-hidden="true">
        {ticks.map((tick) => <span key={tick} className="-translate-y-1/2 first:translate-y-0 last:translate-y-0">{unit === "idr" ? compactIdr(tick) : tick.toLocaleString("id-ID")}</span>)}
      </div>
      <div className="relative min-w-0 flex-1">
        {ticks.map((tick, i) => <div key={tick} aria-hidden="true" className="absolute inset-x-0 border-t border-border" style={{top: `${(i / (ticks.length - 1)) * 100}%`}} />)}
        <div className="absolute inset-0 flex items-end" role="list" aria-label={title}>
          {points.map((point, index) => {
            const height = top ? (point.value / top) * 100 : 0;
            return <div key={point.label} role="listitem" className="relative flex h-full flex-1 items-end justify-center outline-none"
              tabIndex={0} aria-label={`${point.label}: ${format(point.value)}`}
              onMouseEnter={() => setActive(index)} onMouseLeave={() => setActive(null)} onFocus={() => setActive(index)} onBlur={() => setActive(null)}>
              <div className={`w-full max-w-6 rounded-t-[4px] bg-primary transition-opacity ${active !== null && active !== index ? "opacity-40" : ""}`} style={{height: `${height}%`, minHeight: point.value > 0 ? 2 : 0}} />
              {index === last && point.value > 0 ? <span className="absolute -translate-y-1 text-[0.7rem] font-semibold tabular-nums" style={{bottom: `${height}%`}}>{unit === "idr" ? compactIdr(point.value) : point.value.toLocaleString("id-ID")}</span> : null}
              {active === index ? <div role="tooltip" className={`pointer-events-none absolute z-10 whitespace-nowrap border border-border bg-surface px-2 py-1 text-xs shadow-sm ${index > last - 3 ? "right-0" : "left-1/2 -translate-x-1/2"}`} style={{bottom: `calc(${height}% + 8px)`}}>
                <span className="text-muted">{point.label}</span> · <strong className="tabular-nums">{format(point.value)}</strong>
              </div> : null}
            </div>;
          })}
        </div>
      </div>
    </div>
    <div className="ml-14 mt-2 flex text-[0.65rem] text-muted" aria-hidden="true">
      {points.map((point, index) => <span key={point.label} className="flex-1 text-center">{index % 2 === last % 2 ? point.label.split(" ")[0] : ""}</span>)}
    </div>
    <details className="mt-3 text-xs">
      <summary className="cursor-pointer text-muted">Lihat sebagai tabel</summary>
      <table className="mt-2 w-full text-left">
        <thead><tr className="text-muted"><th className="py-1 font-medium">Bulan</th><th className="py-1 text-right font-medium">{title}</th></tr></thead>
        <tbody>{points.map((point) => <tr key={point.label} className="border-t border-border"><td className="py-1">{point.label}</td><td className="py-1 text-right tabular-nums">{format(point.value)}</td></tr>)}</tbody>
      </table>
    </details>
  </figure>;
}

function niceCeil(value: number) {
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((s) => s * magnitude >= value) ?? 10;
  return step * magnitude;
}
