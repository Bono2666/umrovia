const CHECKLIST = [
  { step: "1", label: "Buat 1 paket umroh", note: "Paket → kode, harga, inklusi" },
  { step: "2", label: "Buat 1 jadwal keberangkatan", note: "Kuota kursi & tanggal" },
  { step: "3", label: "Daftar 1 jamaah & booking dummy", note: "Trial: maks 20 booking dummy" },
  { step: "4", label: "Simulasikan DP & invoice", note: "Verifikasi DP oleh finance" },
  { step: "5", label: "Lihat manifest & laporan", note: "Siap operasional" },
];

/**
 * Ringkasan workspace — quick-start checklist trial (Spec §7.1 langkah 4).
 * Data live dari API mulai S07 (modul catalog/booking).
 */
export default function DashboardPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-bold">Selamat datang di Umrovia</h1>
      <p className="mt-1 text-sm text-muted">
        Selesaikan langkah berikut untuk mencoba alur operasional lengkap (data
        demo tidak pernah menjadi tagihan).
      </p>

      <section className="card mt-6 p-6">
        <h2 className="font-semibold">Quick-start checklist</h2>
        <ol className="mt-4 space-y-3">
          {CHECKLIST.map((item) => (
            <li key={item.step} className="flex items-start gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-white">
                {item.step}
              </span>
              <div>
                <div className="text-sm font-medium">{item.label}</div>
                <div className="text-xs text-muted">{item.note}</div>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="card mt-4 p-6 text-sm text-muted">
        <span className="font-semibold text-ink">Status S01:</span> fondasi
        backend & shell frontend siap. Menu di kiri akan aktif bertahap mengikuti
        sprint (S07 jamaah → S09 booking → S11 pembayaran → S15 manifest).
      </section>
    </div>
  );
}
