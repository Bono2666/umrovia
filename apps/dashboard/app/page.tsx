"use client";

import { MarketingHeader } from "@/components/marketing/MarketingHeader";
import { MarketingFooter } from "@/components/marketing/MarketingFooter";
import { SectionScroller } from "@/components/marketing/SectionScroller";
import { MarketingSection } from "@/components/marketing/MarketingSection";
import { ModuleAccordion } from "@/components/marketing/ModuleAccordion";
import { RevealText } from "@/components/marketing/RevealText";
import Image from "next/image";
import { NumberBadge, ScreenCard } from "@/components/marketing/MarketingBits";
import { BtnLink } from "@/components/workspace/ui";
import { appUrl } from "@/lib/siteUrls";

type FiturSegmen = {
  n: string;
  title: string;
  desc: string;
  cards: Array<{ src: string; alt: string; title: string; tags: string }>;
};

/**
 * Halaman marketing `/` (tema web_template): hero + wordmark raksasa,
 * pita gelap pernyataan dengan tangkapan layar Ringkasan, empat segmen fitur bernomor
 * (2 kolom ala expertise), daftar modul gelap (ala capabilities), pita
 * uji coba abu-abu dengan angka besar (ala company), tiga langkah mulai
 * (ala insights), dan footer terang. Setiap section bergerak sebagai blok
 * mengikuti pola parallax `section-out` dan smooth scroll web_template.
 */
const FITUR: FiturSegmen[] = [
  {
    n: "01",
    title: "Leads & pendaftaran",
    desc: "Catat calon jamaah dari formulir, WhatsApp, atau rujukan—lalu lacak statusnya sampai benar-benar terdaftar.",
    cards: [
      { src: "/marketing/kanal-leads.webp", alt: "Daftar leads Umrovia dengan sumber, tahap, dan jadwal follow-up", title: "Kanal leads", tags: "Formulir, Referensi" },
      { src: "/marketing/profil-jamaah.webp", alt: "Detail jamaah dengan NIK dan paspor tersamar serta dokumen yang disetujui", title: "Profil jamaah", tags: "Paspor, Keluarga" },
    ],
  },
  {
    n: "02",
    title: "Pembayaran & termin",
    desc: "Tagih DP, termin, dan pelunasan dengan status yang selalu mutakhir; kuitansi siap dikirim ke jamaah.",
    cards: [
      { src: "/marketing/termin.webp", alt: "Invoice dibayar sebagian dengan total, sisa tagihan, dan rincian per jamaah", title: "Termin paket Arafah", tags: "DP, Pelunasan" },
      { src: "/marketing/kuitansi.webp", alt: "Kuitansi PDF pelunasan yang diterbitkan Umrovia", title: "Kuitansi digital", tags: "PDF, WhatsApp" },
    ],
  },
  {
    n: "03",
    title: "Jamaah & dokumen",
    desc: "Kelengkapan paspor, visa, dan berkas terpantau per jamaah—tak ada yang tertinggal di detik terakhir.",
    cards: [
      { src: "/marketing/kelengkapan-berkas.webp", alt: "Status kelengkapan dokumen dan pembayaran per jamaah di manifest", title: "Kelengkapan berkas", tags: "Visa, Passing" },
      { src: "/marketing/daftar-jamaah.webp", alt: "Daftar jamaah Umrovia dengan ekspor Excel dan CSV", title: "Daftar jamaah", tags: "Kuota, Kelompok" },
    ],
  },
  {
    n: "04",
    title: "Keberangkatan & manifest",
    desc: "Jadwal, kuota kursi, dan manifest akhir tersusun rapi—siap diekspor untuk maskapai dan imigrasi.",
    cards: [
      { src: "/marketing/kuota-jadwal.webp", alt: "Keberangkatan terdekat dengan kursi terisi dan sisa kuota", title: "Kuota jadwal", tags: "Seat, Hari-H" },
      { src: "/marketing/manifest-final.webp", alt: "Roster manifest dengan ekspor PDF, Excel, dan CSV", title: "Manifest final", tags: "Ekspor, PDF" },
    ],
  },
];

const LANGKAH: Array<{ time: string; tag: string; title: string }> = [
  {
    time: "±1 menit",
    tag: "Langkah 01",
    title: "Buat workspace travel Anda—cukup nama biro dan email admin.",
  },
  {
    time: "±2 menit",
    tag: "Langkah 02",
    title: "Undang staf dan atur peran: pendaftaran, finance, atau kurir dokumen.",
  },
  {
    time: "Hari pertama",
    tag: "Langkah 03",
    title: "Masukkan paket dan jadwal, lalu sambut pendaftaran jamaah pertama.",
  },
];

/** Tangkapan layar Ringkasan workspace (data demo fiktif) dalam bingkai tipis. */
function ProductScreen() {
  return (
    <div className="overflow-hidden rounded-[8px] border border-white/15 bg-white shadow-[0_24px_60px_-20px_rgb(0_0_0/0.45)]">
      <Image
        src="/marketing/ringkasan.webp"
        alt="Ringkasan workspace Umrovia: jamaah terdaftar, booking, tagihan, pembayaran masuk, dan kuota keberangkatan terdekat"
        width={2400}
        height={1233}
        unoptimized
        priority
        className="block h-auto w-full"
      />
    </div>
  );
}

export default function Home() {
  return (
    <div data-marketing-page="Beranda" className="contents">
      <SectionScroller />
      <MarketingHeader />

      <main>
        {/* Hero — judul dua baris (baris kedua muted) + wordmark yang
            lebih kecil, rapat, dan rata kiri */}
        <MarketingSection
          className="bg-white"
          innerClassName="mkt-container flex flex-col py-12 md:py-16"
        >
          <RevealText as="h1" variant="title" delay={100} className="text--lead max-w-[760px]">
            Pendaftaran. Pembayaran. Manifest.
            <span className="block text--color-small">
              Satu ruang kerja untuk travel Anda.
            </span>
          </RevealText>

          <RevealText variant="title" delay={180} className="mt-4 text-[56px] font-medium leading-none tracking-[-0.04em] text-primary md:mt-6 md:text-[120px]">
            Umrovia
          </RevealText>
        </MarketingSection>

        {/* Pita gelap — pernyataan besar (ala awards) + tangkapan layar produk */}
        <MarketingSection
          className="bg-primary text-white"
          innerClassName="pt-12 pb-16 md:pt-16 md:pb-28"
        >
          <div className="mkt-container">
            <div className="grid gap-6 xl:grid-cols-12 xl:gap-10">
              <RevealText className="text--t3-md text-white/50 xl:col-span-3">
                Untuk travel modern
              </RevealText>
              {/* Pernyataan di separuh kanan — komposisi awards template */}
              <RevealText as="h2" className="text--h2 xl:col-span-6 xl:col-start-7">
                Satu layar untuk seluruh operasi travel.
              </RevealText>
            </div>
            <div className="mt-12 md:mt-20">
              <ProductScreen />
            </div>
          </div>
        </MarketingSection>

        {/* Segmen fitur bernomor01–04 — dua kolom ala expertise */}
        <section
          aria-labelledby="fitur-title"
          className="bg-white pt-16 md:pt-24"
        >
          <h2 id="fitur-title" className="sr-only">Fitur</h2>
          {FITUR.map((segmen, index) => (
            <MarketingSection
              key={segmen.n}
              id={index === 0 ? "fitur" : undefined}
              aria-label={segmen.title}
              className="scroll-mt-16 bg-white"
              innerClassName={`mkt-container grid gap-10 py-14 md:grid-cols-[1fr_320px] md:gap-16 md:py-24 ${
                index > 0 ? "border-t border-black/10" : ""
              }`}
            >
              <div className="order-2 md:order-none">
                <div className="flex items-center gap-3">
                  <NumberBadge n={segmen.n} />
                  <BtnLink href="#modul" variant="tint">
                    Selengkapnya
                  </BtnLink>
                </div>
                <div className="mt-8 grid gap-4 sm:grid-cols-2 md:mt-10">
                  {segmen.cards.map((card) => (
                    <ScreenCard key={card.title} {...card} />
                  ))}
                </div>
              </div>

              <div className="order-1 flex flex-col gap-5 md:order-none">
                <RevealText as="h3" variant="title" className="text--h3">{segmen.title}</RevealText>
                <RevealText delay={100} className="text--t3-md text--color-small">{segmen.desc}</RevealText>
              </div>
            </MarketingSection>
          ))}
        </section>

        {/* Accordion dan ilustrasi terhubung — capabilities web_template. */}
        <MarketingSection
          id="modul"
          aria-labelledby="modul-title"
          className="scroll-mt-16 bg-primary text-white"
        >
          <ModuleAccordion />
        </MarketingSection>

        {/* Pita uji coba abu-abu — ala company: pernyataan + angka raksasa
            putih + garis + CTA */}
        <MarketingSection className="bg-[#cdcfd0] text-[#191b1d]">
          <div className="mkt-container relative scroll-mt-16 py-16 md:py-28">
            <div className="grid gap-8 md:grid-cols-12">
              <RevealText className="text--t3-md text-black md:col-span-3">
                Uji coba
              </RevealText>
              <div className="md:col-span-9">
                <RevealText as="h2" className="text--h3 max-w-[880px]">
                  Semua fitur terbuka selama 30 hari—tanpa kartu kredit, tanpa
                  instalasi.
                </RevealText>
                <div className="mt-14 flex items-end justify-between gap-6">
                  <RevealText as="span" variant="title" className="text--h1 text-white">30</RevealText>
                  <RevealText as="span" className="pb-1 text--t3-md text-right">
                    Hari uji coba
                    <br />
                    gratis
                  </RevealText>
                </div>
              </div>
            </div>

            <div className="mt-14 border-t border-black/20 pt-8">
              <BtnLink href={appUrl("/register")} variant="solid">
                Mulai gratis
              </BtnLink>
            </div>
          </div>
        </MarketingSection>

        {/* Tiga langkah — ala insights: judul raksasa + pill, tiga kartu */}
        <MarketingSection
          id="mulai"
          className="scroll-mt-16 bg-white"
          innerClassName="mkt-container py-16 md:py-24"
        >
          <div className="flex flex-wrap items-end justify-between gap-6">
            <RevealText as="h2" variant="title" className="text--h2">Cara mulai</RevealText>
            <BtnLink href={appUrl("/register")} variant="tint">
              Daftar sekarang
            </BtnLink>
          </div>

          <div className="mt-12 grid gap-5 md:mt-16 md:grid-cols-3">
            {LANGKAH.map((langkah) => (
              <article
                key={langkah.tag}
                className="flex min-h-[320px] flex-col rounded-[6px] border border-black/10 p-6 md:min-h-[400px] md:p-8"
              >
                <RevealText className="text-[17px] leading-[1.4] tracking-[-0.04em]">
                  {langkah.title}
                </RevealText>
                <div className="mt-auto pt-10">
                  <p className="text--t3-md text--color-small">
                    {langkah.time}
                  </p>
                  <p className="mt-1 text--t3-sm">{langkah.tag}</p>
                </div>
              </article>
            ))}
          </div>
        </MarketingSection>
      </main>

      <MarketingFooter />
    </div>
  );
}
