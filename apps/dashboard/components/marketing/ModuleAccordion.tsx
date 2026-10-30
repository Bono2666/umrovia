"use client";

import { useState } from "react";
import { RevealText } from "./RevealText";
import { MarketingAccordion } from "./MarketingAccordion";

const MODULES = [
  {
    id: "dasbor",
    title: "Dasbor real-time",
    description: "Penjualan, kas, dan keberangkatan hari ini tersaji dalam satu tampilan.",
  },
  {
    id: "katalog",
    title: "Katalog & paket",
    description: "Susun paket, harga, kuota, dan periode keberangkatan tanpa spreadsheet terpisah.",
  },
  {
    id: "keuangan",
    title: "Laporan keuangan",
    description: "Arus kas, piutang, dan laporan bulanan yang bisa langsung diekspor kapan pun.",
  },
  {
    id: "tim",
    title: "Tim & peran",
    description: "Struktur cabang, peran, dan izin akses yang bisa diatur sendiri oleh Anda.",
  },
  {
    id: "portal",
    title: "Portal jamaah",
    description: "Jamaah memantau tagihan, mengunggah dokumen, dan membaca pengumuman dari ponselnya.",
  },
] as const;

/* Lingkaran bertumpuk mengisi kanvas 380 × 260 (r ≈ 130): pusat pertama 130, terakhir 250. */
const CIRCLE_STEP = 120 / (MODULES.length - 1);

/** Accordion and linked circle artwork from web_template's capabilities section. */
export function ModuleAccordion() {
  const [active, setActive] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [focused, setFocused] = useState<number | null>(null);

  return (
    <div className="mkt-container module-capabilities">
      <div className="module-capabilities__left">
        <RevealText as="h2" id="modul-title" className="text--t3-md">Modul kami</RevealText>
        <svg
          viewBox="0 0 380 260"
          fill="none"
          role="img"
          aria-label={active === null
            ? "Lima modul operasional Umrovia"
            : `Modul aktif: ${MODULES[active].title}`}
          data-active-module={active === null ? "" : MODULES[active].id}
          className="module-capabilities__art"
        >
          {MODULES.map((module, index) => (
            <circle
              key={module.id}
              cx={130 + index * CIRCLE_STEP}
              cy="130"
              r="129.5"
              stroke="currentColor"
              data-module={module.id}
              data-state={active === index ? "active" : hovered === index || focused === index ? "hovered" : "idle"}
            />
          ))}
        </svg>
      </div>

      <MarketingAccordion
        items={MODULES}
        labelledBy="modul-title"
        idPrefix="module"
        onActiveChange={setActive}
        onHoverChange={setHovered}
        onFocusChange={setFocused}
      />
    </div>
  );
}
