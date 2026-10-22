/**
 * Helper format tampilan (S06) — nominal integer rupiah (§4.4: tanpa desimal,
 * gaya `Rp50.000`) dan tanggal absolut locale id-ID (§4.3 countdown absolut).
 */

export function formatIdr(amount: number): string {
  return `Rp${Math.round(amount)}`.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
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
