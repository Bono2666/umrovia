"use client";

import { MarketingHeader } from "@/components/marketing/MarketingHeader";
import { MarketingFooter } from "@/components/marketing/MarketingFooter";
import { Parallax } from "@/components/marketing/Parallax";
import {
  CircleArrow,
  MockCard,
  NumberBadge,
  type MockKind,
} from "@/components/marketing/MarketingBits";
import { BtnLink } from "@/components/workspace/ui";

type FiturSegmen = {
  n: string;
  title: string;
  desc: string;
  cards: Array<{ kind: MockKind; title: string; tags: string }>;
};

/**
 * Halaman marketing `/` (tema web_template): hero + wordmark raksasa,
 * pita gelap pernyataan dengan mock produk, empat segmen fitur bernomor
 * (2 kolom ala expertise), daftar modul gelap (ala capabilities), pita
 * uji coba abu-abu dengan angka besar (ala company), tiga langkah mulai
 * (ala insights), dan footer terang. Elemen bervariasi di tiap section
 * digerakkan paralaks (locomotive-style) lewat `data-scroll-speed`.
 */
const FITUR: FiturSegmen[] = [
  {
    n: "01",
    title: "Leads & pendaftaran",
    desc: "Catat calon jamaah dari formulir, WhatsApp, atau rujukan—lalu lacak statusnya sampai benar-benar terdaftar.",
    cards: [
      { kind: "list", title: "Kanal leads", tags: "Formulir, Referensi" },
      { kind: "profile", title: "Profil jamaah", tags: "Paspor, Keluarga" },
    ],
  },
  {
    n: "02",
    title: "Pembayaran & termin",
    desc: "Tagih DP, termin, dan pelunasan dengan status yang selalu mutakhir; kuitansi siap dikirim ke jamaah.",
    cards: [
      {
        kind: "progress",
        title: "Termin paket Arafah",
        tags: "DP, Pelunasan",
      },
      { kind: "invoice", title: "Kuitansi digital", tags: "PDF, WhatsApp" },
    ],
  },
  {
    n: "03",
    title: "Jamaah & dokumen",
    desc: "Kelengkapan paspor, visa, dan berkas terpantau per jamaah—tak ada yang tertinggal di detik terakhir.",
    cards: [
      { kind: "check", title: "Kelengkapan berkas", tags: "Visa, Passing" },
      { kind: "team", title: "Daftar jamaah", tags: "Kuota, Kelompok" },
    ],
  },
  {
    n: "04",
    title: "Keberangkatan & manifest",
    desc: "Jadwal, kuota kursi, dan manifest akhir tersusun rapi—siap diekspor untuk maskapai dan imigrasi.",
    cards: [
      { kind: "chart", title: "Kuota jadwal", tags: "Seat, Hari-H" },
      { kind: "list", title: "Manifest final", tags: "Ekspor, PDF" },
    ],
  },
];

const MODUL: Array<{ title: string; desc: string }> = [
  {
    title: "Dasbor real-time",
    desc: "Penjualan, kas, dan keberangkatan hari ini tersaji dalam satu tampilan.",
  },
  {
    title: "Katalog & paket",
    desc: "Susun paket, harga, kuota, dan periode keberangkatan tanpa spreadsheet terpisah.",
  },
  {
    title: "Laporan keuangan",
    desc: "Arus kas, piutang, dan laporan bulanan yang bisa langsung diekspor kapan pun.",
  },
  {
    title: "Tim & peran",
    desc: "Struktur cabang, peran, dan izin akses yang bisa diatur sendiri oleh Anda.",
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

const NAVIGASI_MOCK_SIDEBAR = ["w-4/5", "w-3/5", "w-2/3", "w-1/2", "w-3/4"];

function ProductMock() {
  return (
    <div className="overflow-hidden rounded-[8px] border border-white/15 bg-white/[0.04]">
      {/* Bilah jendela */}
      <div className="flex h-10 items-center gap-2 border-b border-white/10 px-4">
        <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
        <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
        <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
        <span className="ml-3 h-2 w-40 rounded-full bg-white/10" />
      </div>

      <div className="grid gap-6 p-5 md:grid-cols-[180px_1fr] md:p-7">
        {/* Rail samping */}
        <div className="hidden flex-col gap-3 md:flex">
          <span className="mb-2 h-3 w-24 rounded-full bg-white/30" />
          {NAVIGASI_MOCK_SIDEBAR.map((width, i) => (
            <span
              key={i}
              className={`flex h-7 items-center rounded-[4px] px-3 ${
                i === 0 ? "bg-white/15" : "bg-white/[0.06]"
              }`}
            >
              <span className={`h-2 rounded-full bg-white/25 ${width}`} />
            </span>
          ))}
        </div>

        {/* Konten */}
        <div className="flex min-w-0 flex-col gap-5">
          <div className="flex items-center justify-between gap-4">
            <span className="h-4 w-44 rounded-full bg-white/25" />
            <span className="h-7 w-24 rounded-full bg-white/15" />
          </div>

          <div className="grid grid-cols-3 gap-4">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="rounded-[6px] border border-white/10 bg-white/[0.05] p-4"
              >
                <span className="block h-2 w-14 rounded-full bg-white/20" />
                <span className="mt-3 block h-4 w-10 rounded-full bg-white/40" />
              </div>
            ))}
          </div>

          <div className="overflow-hidden rounded-[6px] border border-white/10">
            {[0, 1, 2, 3].map((i) => (
              <div
                key={i}
                className="flex items-center gap-4 border-t border-white/10 px-4 py-3 first:border-t-0"
              >
                <span className="h-6 w-6 shrink-0 rounded-full bg-white/10" />
                <span className="h-2 min-w-0 flex-1 rounded-full bg-white/15" />
                <span className="hidden h-2 w-16 rounded-full bg-white/20 sm:block" />
                <span className="h-4 w-14 shrink-0 rounded-full bg-white/10" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <>
      <Parallax />
      <MarketingHeader />

      <main>
        {/* Hero — judul dua baris (baris kedua muted) + wordmark yang
            lebih kecil, rapat, dan rata kiri */}
        <section className="mkt-container flex min-h-[480px] flex-col pt-16 md:min-h-[760px] md:pt-32">
          <h1 className="text--lead max-w-[760px]">
            Pendaftaran. Pembayaran. Manifest.
            <span className="block text--color-small">
              Satu ruang kerja untuk travel Anda.
            </span>
          </h1>

          <div className="mt-auto pt-14 md:pt-20 md:pb-14">
            <p
              data-scroll-speed="1"
              className="text-[56px] font-medium leading-none tracking-[-0.04em] text-[#191b1d] md:text-[120px]"
            >
              Umrovia
            </p>
          </div>
        </section>

        {/* Pita gelap — pernyataan besar (ala awards) + mock produk */}
        <section className="bg-[#191b1d] py-16 text-white md:py-28">
          <div className="mkt-container">
            <div className="grid gap-6 md:grid-cols-12 md:gap-10">
              <p className="text--t3-md text-white/50 md:col-span-3">
                Untuk travel modern
              </p>
              {/* Pernyataan di separuh kanan — komposisi awards template */}
              <h2
                data-scroll-speed="1"
                className="text--h2 md:col-span-6 md:col-start-7"
              >
                Satu layar untuk seluruh operasi travel.
              </h2>
            </div>
            <div className="mt-12 md:mt-20" data-scroll-speed="1.5">
              <ProductMock />
            </div>
          </div>
        </section>

        {/* Segmen fitur bernomor01–04 — dua kolom ala expertise */}
        <section id="fitur" className="mkt-container scroll-mt-16 pt-16 md:pt-24">
          <h2 className="sr-only">Fitur</h2>
          {FITUR.map((segmen, index) => (
            <div
              key={segmen.n}
              className={`grid gap-10 py-14 md:grid-cols-[1fr_320px] md:gap-16 md:py-24 ${
                index > 0 ? "border-t border-black/10" : ""
              }`}
            >
              <div className="order-2 md:order-none" data-scroll-speed="1">
                <div className="flex items-center gap-3">
                  <NumberBadge n={segmen.n} />
                  <BtnLink href="#modul" variant="tint">
                    Selengkapnya
                  </BtnLink>
                </div>
                <div className="mt-8 grid gap-4 sm:grid-cols-2 md:mt-10">
                  {segmen.cards.map((card) => (
                    <MockCard key={card.title} {...card} />
                  ))}
                </div>
              </div>

              <div className="order-1 flex flex-col gap-5 md:order-none">
                <h3 className="text--h3">{segmen.title}</h3>
                <p className="text--t3-md text--color-small">{segmen.desc}</p>
              </div>
            </div>
          ))}
        </section>

        {/* Daftar modul gelap — ala capabilities (label + elips di kiri,
            baris judul + panah lingkaran di kanan) */}
        <section id="modul" className="scroll-mt-16 bg-[#191b1d] text-white">
          <div className="mkt-container grid gap-12 py-16 md:grid-cols-12 md:py-28">
            <div className="md:col-span-4">
              <h2 className="text--t3-md text-white/50">
                Satu aplikasi
                <br />
                untuk operasional
              </h2>
              <div
                className="mt-12 hidden md:flex"
                aria-hidden="true"
                data-scroll-speed="2"
              >
                {[0, 1, 2, 3].map((i) => (
                  <span
                    key={i}
                    className="h-16 w-28 rounded-[50%] border border-white/25"
                    style={{ marginLeft: i ? "-40px" : undefined }}
                  />
                ))}
              </div>
            </div>

            <div className="md:col-span-8">
              {MODUL.map((modul) => (
                <div
                  key={modul.title}
                  className="group border-t border-white/15 py-8 first:border-t-0 first:pt-0"
                >
                  <div className="flex items-start justify-between gap-6">
                    <h3 className="text--h3">{modul.title}</h3>
                    <CircleArrow />
                  </div>
                  <p className="mt-4 max-w-[560px] text--t3-md text-white/70">
                    {modul.desc}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Pita uji coba abu-abu — ala company: pernyataan + angka raksasa
            putih + garis + CTA */}
        <section className="relative overflow-hidden bg-[#cdcfd0] text-[#191b1d]">
          <span
            aria-hidden="true"
            data-scroll-speed="2"
            className="absolute -left-40 top-10 hidden h-96 w-96 rounded-full bg-[#191b1d] md:block"
          />
          <div className="mkt-container relative scroll-mt-16 py-16 md:py-28">
            <div className="grid gap-8 md:grid-cols-12">
              {/* Label putih karena duduk di atas lingkaran dekoratif hitam
                  (mobile: lingkaran disembunyikan → label tetap soft-black) */}
              <p className="text--t3-md text-[#191b1d] md:col-span-3 md:text-white">
                Uji coba
              </p>
              <div className="md:col-span-9">
                <h2 className="text--h3 max-w-[880px]">
                  Semua fitur terbuka selama 30 hari—tanpa kartu kredit, tanpa
                  instalasi.
                </h2>
                <div className="mt-14 flex items-end justify-between gap-6">
                  <span className="text--h1 text-white">30</span>
                  <span className="pb-1 text--t3-md text-right">
                    Hari uji coba
                    <br />
                    gratis
                  </span>
                </div>
              </div>
            </div>

            <div className="mt-14 border-t border-black/20 pt-8">
              <BtnLink href="/register" variant="solid">
                Mulai gratis
              </BtnLink>
            </div>
          </div>
        </section>

        {/* Tiga langkah — ala insights: judul raksasa + pill, tiga kartu */}
        <section
          id="mulai"
          className="mkt-container scroll-mt-16 py-16 md:py-24"
        >
          <div className="flex flex-wrap items-end justify-between gap-6">
            <h2 className="text--h2">Cara mulai</h2>
            <BtnLink href="/register" variant="tint">
              Daftar sekarang
            </BtnLink>
          </div>

          <div
            className="mt-12 grid gap-5 md:mt-16 md:grid-cols-3"
            data-scroll-speed="1"
          >
            {LANGKAH.map((langkah) => (
              <article
                key={langkah.tag}
                className="flex min-h-[320px] flex-col rounded-[6px] border border-black/10 p-6 md:min-h-[400px] md:p-8"
              >
                <p className="text-[17px] leading-[1.4] tracking-[-0.04em]">
                  {langkah.title}
                </p>
                <div className="mt-auto pt-10">
                  <p className="text--t3-md text--color-small">
                    {langkah.time}
                  </p>
                  <p className="mt-1 text--t3-sm">{langkah.tag}</p>
                </div>
              </article>
            ))}
          </div>
        </section>
      </main>

      <MarketingFooter />
    </>
  );
}
