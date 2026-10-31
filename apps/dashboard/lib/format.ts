/**
 * Helper format tampilan (S06) — nominal integer rupiah (§4.4: tanpa desimal,
 * gaya `Rp50.000`) dan tanggal absolut locale id-ID (§4.3 countdown absolut).
 */

export function formatIdr(amount: number): string {
  // Kelompokkan digit saja: regex pada "Rp…" menyisipkan titik setelah "Rp"
  // bila jumlah digit kelipatan tiga (mis. "Rp.100.000").
  const value = Math.round(amount);
  const digits = String(Math.abs(value)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${value < 0 ? "−" : ""}Rp${digits}`;
}

/** Angka mentah ("-1500000") → tampilan bertitik ribuan ("-1.500.000"). */
export function groupThousands(raw: string): string {
  const sign = raw.startsWith("-") ? "-" : "";
  return sign + raw.slice(sign.length).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

/** Teks ketikan/tempelan ("Rp 1.500.000") → angka mentah ("1500000"); `signed` mempertahankan minus di depan. */
export function stripThousands(text: string, signed = false): string {
  const sign = signed && text.trim().startsWith("-") ? "-" : "";
  return sign + text.replace(/\D/g, "").replace(/^0+(?=\d)/, "");
}

/** Tanggal absolut, contoh: "20 November 2026". */
export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("id-ID", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

/** Sisa waktu relatif menuju `iso`, contoh: "29 hari 3 jam lagi". */
export function formatRemaining(iso: string, now: number = Date.now()): string {
  const ms = new Date(iso).getTime() - now;
  if (Number.isNaN(ms)) return "-";
  if (ms <= 0) return "telah berakhir";
  const days = Math.floor(ms / 86_400_000);
  const hours = Math.floor((ms % 86_400_000) / 3_600_000);
  const minutes = Math.floor((ms % 3_600_000) / 60_000);
  if (days > 0) return `${days} hari ${hours} jam lagi`;
  if (hours > 0) return `${hours} jam ${minutes} menit lagi`;
  return `${minutes} menit lagi`;
}

/** Nomor tersamar dari server ("************0001") → ringkas "•••• 0001". */
export function formatMasked(value: string): string {
  return value.replace(/^\*+/, "•••• ");
}
