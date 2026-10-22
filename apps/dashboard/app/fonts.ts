import localFont from "next/font/local";

/**
 * Font self-hosted (S06/opsi-3) — build tidak lagi bergantung
 * fonts.googleapis.com (build container hermetic; hint next/font:
 * "if you are offline or behind a proxy, self-host the font").
 *
 * Poppins: SIL Open Font License — subset latin, weight 400–700 (paket UI).
 * Geist Mono: OFL (Vercel) — variabel 100–900 untuk blok kode/angka.
 * Sumber: Google Fonts CSS API (diunduh ke fonts/, di-commit ke repo).
 */
export const poppins = localFont({
  src: [
    { path: "../fonts/Poppins-400.woff2", weight: "400", style: "normal" },
    { path: "../fonts/Poppins-500.woff2", weight: "500", style: "normal" },
    { path: "../fonts/Poppins-600.woff2", weight: "600", style: "normal" },
    { path: "../fonts/Poppins-700.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-poppins",
  display: "swap",
  fallback: ["system-ui", "sans-serif"],
});

export const geistMono = localFont({
  src: [{ path: "../fonts/GeistMono-Variable.woff2", weight: "100 900" }],
  variable: "--font-geist-mono",
  display: "swap",
  fallback: ["monospace"],
});
