import type { Metadata } from "next";
import { MarketingPage, PageIntro } from "@/components/marketing/MarketingPage";
import { MarketingSection } from "@/components/marketing/MarketingSection";
import { PricingCalculator } from "@/components/marketing/PricingCalculator";
import { BtnLink } from "@/components/workspace/ui";
import { MarketingAccordion } from "@/components/marketing/MarketingAccordion";

export const metadata: Metadata = { title: "Pricing", description: "Rp50.000 per booking-jamaah setelah DP terverifikasi. Tanpa biaya bulanan dan setup standar. Coba Umrovia gratis 30 hari." };

const FAQ = [
  ["Kapan biaya Rp50.000 dikenakan?", "Setelah DP pertama diterima dan diverifikasi untuk satu jamaah pada satu pendaftaran perjalanan. Biaya dikenakan sekali untuk booking-jamaah tersebut, bukan setiap termin pembayaran."],
  ["Apakah ada biaya bulanan atau setup?", "Tidak ada biaya berlangganan bulanan atau tahunan wajib, dan setup standar gratis. Biaya penggunaan mengikuti jumlah booking-jamaah yang memenuhi syarat."],
  ["Bagaimana cara pembayaran penggunaan?", "Penggunaan nyata didanai dari saldo prepaid wallet travel. Ketika DP terverifikasi, biaya dipotong dari saldo yang tersedia. Biaya gateway atau pajak, jika berlaku, diinformasikan terpisah."],
  ["Apa yang termasuk trial 30 hari?", "Mode demo selama 30 hari dengan maksimal 20 booking-jamaah dummy dan 3 pengguna internal aktif, termasuk owner. Gunakan data simulasi; pembayaran simulasi tidak memotong wallet dan tidak menghasilkan biaya penggunaan."],
  ["Apa yang terjadi setelah trial berakhir?", "Workspace beralih ke penggunaan aktif tanpa kewajiban biaya bulanan. Booking-jamaah nyata yang DP-nya diterima dan diverifikasi mengikuti tarif Rp50.000, dengan pendanaan dari wallet."],
  ["Bagaimana jika satu jamaah berangkat lagi?", "Biaya berlaku per booking-jamaah. Jamaah yang sama pada pendaftaran perjalanan lain merupakan unit penggunaan baru setelah DP perjalanan tersebut terverifikasi."],
];

export default function PricingPage() {
  return <MarketingPage title="Pricing">
    <PageIntro eyebrow="Pricing" title="Tumbuh bersama perjalanan Anda." description="Mulai tanpa biaya bulanan. Bayar penggunaan ketika jamaah sudah membayar DP dan pembayaran tersebut terverifikasi." href="#harga" linkLabel="Lihat skema harga" gray />
    <MarketingSection id="harga" className="scroll-mt-16 bg-white" innerClassName="mkt-container marketing-two-column py-16 min-[980px]:py-28">
      <h2 className="text--t3-md">Satu skema.<br />Tanpa langganan.</h2>
      <div>
        <p className="text--t3-md text-muted">Biaya penggunaan standar</p>
        <p className="pricing-price mt-6"><span className="text-[0.3em]">Rp</span>50.000</p>
        <p className="mt-5 text--lead">per booking-jamaah<br /><span className="text-muted">setelah DP terverifikasi.</span></p>
        <div className="mt-10 flex flex-wrap gap-4"><BtnLink href="/register">Coba gratis 30 hari</BtnLink><BtnLink href="/kontak" variant="tint">Bicara dengan kami</BtnLink></div>
        <div className="mt-14 grid grid-cols-3 gap-4 border-t border-black/15 pt-8">
          {[["Rp0", "Biaya bulanan"], ["Rp0", "Setup standar"], ["30 hari", "Trial gratis"]].map(([value, label]) => <div key={label}><p className="text--h3">{value}</p><p className="mt-3 text--t3-md text-muted">{label}</p></div>)}
        </div>
      </div>
    </MarketingSection>
    <MarketingSection className="bg-[#f0f0ef]" innerClassName="mkt-container py-16 min-[980px]:py-24">
      <div className="marketing-two-column"><h2 className="text--t3-md">Hitung kebutuhan Anda</h2><div><h3 className="text--h3 max-w-[700px]">Biaya yang mudah dihitung, sesuai penggunaan.</h3><p className="mt-6 text--t3-md text-muted">Simulasi ini menghitung biaya platform, bukan nilai DP atau harga paket perjalanan jamaah.</p></div></div>
      <PricingCalculator />
    </MarketingSection>
    <MarketingSection className="bg-primary text-white" innerClassName="mkt-container marketing-two-column py-16 min-[980px]:py-28">
      <h2 className="text--t3-md text-white/60">Mulai dari mode demo</h2>
      <div><h3 className="text--h2">Kenali alurnya.<br />Coba 30 hari.</h3><p className="mt-8 max-w-[550px] text--t3-md text-white/65">Jelajahi workspace dengan data simulasi, maksimal 20 booking-jamaah dummy dan 3 pengguna internal. Trial gratis dan tanpa pemotongan wallet.</p><BtnLink href="/register" className="mt-10 text-primary before:bg-[#e8e8e8] after:bg-white">Buat workspace</BtnLink></div>
    </MarketingSection>
    <MarketingSection id="faq" className="scroll-mt-16 bg-white" innerClassName="mkt-container marketing-two-column py-16 min-[980px]:py-28">
      <h2 id="faq-title" className="text--t3-md">Pertanyaan umum</h2>
      <MarketingAccordion items={FAQ.map(([title, description], index) => ({ id: String(index + 1), title, description }))} labelledBy="faq-title" idPrefix="faq" tone="light" />
    </MarketingSection>
  </MarketingPage>;
}
