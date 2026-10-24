import type { Metadata } from "next";
import Link from "next/link";
import { MarketingPage, PageIntro } from "@/components/marketing/MarketingPage";
import { MarketingSection } from "@/components/marketing/MarketingSection";
import { ContactForm } from "@/components/marketing/ContactForm";
import { MarketingAccordion } from "@/components/marketing/MarketingAccordion";
import { RevealText } from "@/components/marketing/RevealText";

export const metadata: Metadata = { title: "Kontak", description: "Hubungi Umrovia untuk membahas kebutuhan software travel, harga, bantuan penggunaan, dan privasi data." };

const CONTACT_TOPICS = [
  { id: "produk", title: "Produk & demo", description: "Kenali alur kerja yang sesuai dengan travel Anda." },
  { id: "harga", title: "Harga & penggunaan", description: "Pahami biaya per booking-jamaah dan trial 30 hari." },
  { id: "dukungan", title: "Dukungan & privasi", description: "Sampaikan kendala penggunaan atau permintaan terkait data." },
] as const;

export default function ContactPage() {
  return <MarketingPage title="Kontak">
    <PageIntro eyebrow="Kontak" title="Mari bicara tentang travel Anda." description="Sedang memilih sistem untuk tim, ingin memahami skema harga, atau membutuhkan bantuan? Ceritakan kebutuhan Anda kepada kami." href="#formulir" linkLabel="Tulis pesan" gray />
    <MarketingSection id="topik-kontak" aria-labelledby="topik-kontak-title" className="bg-primary text-white" innerClassName="mkt-container marketing-two-column py-16 min-[980px]:py-28">
      <RevealText as="h2" id="topik-kontak-title" className="text--t3-md">Kami siap mendengarkan</RevealText>
      <MarketingAccordion items={CONTACT_TOPICS} labelledBy="topik-kontak-title" idPrefix="contact-topic" />
    </MarketingSection>
    <MarketingSection id="formulir" className="scroll-mt-16 bg-white" innerClassName="mkt-container marketing-two-column py-16 min-[980px]:py-28">
      <div><h2 className="text--t3-md">Hubungi kami</h2><p className="mt-6 max-w-[230px] text--t3-md text-muted">Isi formulir di sebelah ini. Untuk pertanyaan umum, Anda juga bisa membaca <Link href="/pricing#faq" className="text-primary hover:text-primary-hover">FAQ harga</Link>.</p></div>
      <ContactForm />
    </MarketingSection>
  </MarketingPage>;
}
