import type { Metadata } from "next";
import Link from "next/link";
import { MarketingPage, PageIntro } from "@/components/marketing/MarketingPage";
import { MarketingSection } from "@/components/marketing/MarketingSection";

export const metadata: Metadata = { title: "Kebijakan Privasi", description: "Informasi pemrosesan data pada situs dan layanan Umrovia, cookie, hak terkait data, dan cara menghubungi kami." };

const SECTIONS = [
  { id: "cakupan", title: "Tentang kebijakan ini", text: "Kebijakan ini menjelaskan penggunaan data pada situs dan layanan Umrovia. Pengelola platform menggunakan data akun dan komunikasi untuk menyediakan layanan. Untuk data jamaah yang dimasukkan oleh travel, travel menentukan tujuan penggunaannya; Umrovia menyediakan sistem untuk memproses data sesuai pengaturan dan kewenangan workspace tersebut." },
  { id: "data", title: "Data yang Anda berikan", text: "Data dapat mencakup nama, email, nama perusahaan, nomor telepon yang Anda pilih untuk dicantumkan, dan isi pesan pada formulir kontak. Pada pendaftaran akun, kami memproses identitas akun dan informasi workspace. Data operasional yang dimasukkan oleh travel mengikuti fitur yang digunakan serta izin akses masing-masing pengguna. Jangan mengirim dokumen jamaah, password, atau informasi pembayaran sensitif melalui formulir kontak." },
  { id: "tujuan", title: "Tujuan pemrosesan", text: "Data digunakan untuk menanggapi pertanyaan, menyediakan dan mengelola akun, menjalankan fungsi workspace, menjaga keamanan, serta menangani masalah penggunaan. Persetujuan pada formulir kontak diberikan khusus untuk menangani pesan Anda, bukan persetujuan menerima promosi. Pemrosesan juga dapat diperlukan untuk menjalankan layanan yang Anda minta atau memenuhi kewajiban hukum yang berlaku." },
  { id: "akses", title: "Akses dan penyedia layanan", text: "Akses data operasional dibatasi melalui akun, keanggotaan workspace, dan peran pengguna. Penyedia infrastruktur atau layanan pendukung dapat memproses data yang diperlukan untuk menjalankan layanan. Informasi juga dapat disampaikan jika diwajibkan oleh proses hukum yang sah. Travel bertanggung jawab mengatur akses staf dan memastikan data jamaah diperoleh serta digunakan secara sah." },
  { id: "cookie", title: "Cookie dan informasi teknis", text: "Layanan menggunakan cookie sesi untuk mempertahankan login dan cookie keamanan untuk membantu mencegah permintaan yang tidak sah. Informasi teknis seperti waktu akses dan identitas permintaan dapat diproses untuk operasional serta pemeriksaan gangguan. Anda dapat mengatur cookie melalui browser; menonaktifkan cookie yang diperlukan dapat mengganggu login atau penggunaan layanan." },
  { id: "penyimpanan", title: "Penyimpanan dan penghapusan", text: "Data disimpan selama diperlukan untuk tujuan pemrosesan, penyediaan layanan, penanganan permintaan, atau kewajiban hukum yang berlaku. Permintaan koreksi atau penghapusan ditinjau dengan mempertimbangkan kewenangan pemohon, kebutuhan pencatatan transaksi, dan ketentuan yang berlaku. Penghapusan dari sistem aktif dan siklus salinan cadangan dapat memiliki proses yang berbeda." },
  { id: "hak", title: "Hak terkait data Anda", text: "Sesuai ketentuan yang berlaku, Anda dapat mengajukan permintaan informasi, akses, koreksi, penghapusan, atau penarikan persetujuan atas pemrosesan data pribadi. Untuk data yang dikelola travel, hubungi travel terkait terlebih dahulu. Kami dapat meminta verifikasi identitas dan kewenangan sebelum memproses permintaan, agar data tidak diberikan kepada pihak yang tidak berhak." },
  { id: "perubahan", title: "Perubahan kebijakan", text: "Kebijakan dapat diperbarui ketika fitur atau praktik pemrosesan berubah. Tanggal pembaruan dicantumkan pada halaman ini. Perubahan yang memerlukan pemberitahuan atau persetujuan akan ditangani sesuai sifat perubahan dan ketentuan yang berlaku." },
];

export default function PrivacyPage() {
  return <MarketingPage title="Kebijakan Privasi">
    <PageIntro eyebrow="Privasi & data" title="Kebijakan Privasi." description="Pahami data yang diproses, tujuan penggunaannya, dan cara mengajukan permintaan terkait data Anda." href="#cakupan" linkLabel="Baca kebijakan">
      <p className="mt-6 text--t3-sm text-muted">Terakhir diperbarui: <time dateTime="2026-10-24">24 Oktober 2026</time></p>
    </PageIntro>
    {SECTIONS.map((section, index) => <MarketingSection key={section.id} id={section.id} className="scroll-mt-16 border-t border-black/10 bg-white" innerClassName="mkt-container marketing-two-column py-10 min-[980px]:py-16">
      <p className="text--t3-md text-muted">{String(index + 1).padStart(2, "0")}</p>
      <div className="privacy-copy"><h2 className="text--h3">{section.title}</h2><p>{section.text}</p>{section.id === "hak" && <p>Informasi mengenai hak subjek data dapat dibaca dalam <a href="https://jdih.komdigi.go.id/produk_hukum/view/id/832/t/crc32/" target="_blank" rel="noreferrer" className="text-primary hover:text-primary-hover">UU Nomor 27 Tahun 2022 tentang Pelindungan Data Pribadi</a>.</p>}</div>
    </MarketingSection>)}
    <MarketingSection className="border-t border-black/10 bg-[#f0f0ef]" innerClassName="mkt-container marketing-two-column py-12 min-[980px]:py-20">
      <h2 className="text--t3-md">Hubungi Umrovia</h2><div><p className="text--lead">Ada pertanyaan atau permintaan terkait data?</p><p className="mt-6 text--t3-md text-muted">Gunakan <Link href="/kontak#formulir" className="text-primary hover:text-primary-hover">formulir kontak</Link>, lalu pilih topik “Privasi & data pribadi”. Sertakan informasi yang cukup untuk mengenali permintaan Anda, tanpa mengirim dokumen sensitif.</p></div>
    </MarketingSection>
  </MarketingPage>;
}
