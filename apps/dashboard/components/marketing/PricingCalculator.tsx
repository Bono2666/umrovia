"use client";

import { useState } from "react";

const rupiah = (value: number) => new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(value);

export function PricingCalculator() {
  const [count, setCount] = useState(20);
  return <div className="pricing-calculator">
    <div>
      <label htmlFor="pricing-count" className="text--t3-md">Booking-jamaah dengan DP terverifikasi</label>
      <div className="mt-7 flex items-baseline gap-3">
        <input id="pricing-count" type="number" min={0} max={10000} step={1} value={count} onChange={(event) => setCount(Math.max(0, Math.min(10000, Math.floor(Number(event.target.value) || 0))))} className="w-40 border-b border-black/30 bg-transparent text-5xl tracking-tight outline-offset-8" />
        <span className="text-muted">jamaah</span>
      </div>
      <input type="range" min={0} max={Math.max(200, count)} step={1} value={count} onChange={(event) => setCount(Number(event.target.value))} aria-label="Jumlah booking-jamaah" className="mt-8 w-full accent-[#191b1d]" />
    </div>
    <div className="border-t border-black/20 pt-6 min-[980px]:border-t-0 min-[980px]:border-l min-[980px]:pl-12 min-[980px]:pt-0">
      <p className="text--t3-md text-muted">Estimasi biaya penggunaan</p>
      <output htmlFor="pricing-count" aria-live="polite" className="mt-5 block break-words text-[clamp(2rem,4vw,4rem)] font-medium leading-none tracking-[-0.06em]">{rupiah(count * 50000)}</output>
      <p className="mt-6 text--t3-md text-muted">{count.toLocaleString("id-ID")} × Rp50.000. Leads dan pendaftaran yang belum memiliki DP terverifikasi tidak dihitung.</p>
    </div>
  </div>;
}
