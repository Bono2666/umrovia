/**
 * Produksi memisahkan host: halaman marketing di domain utama (umrovia.com),
 * aplikasi (login, daftar, workspace, portal) di app.umrovia.com. Keduanya
 * diisi saat build; bila kosong (dev lokal) tautan tetap relatif di host yang sama.
 */
const APP_URL = (process.env.NEXT_PUBLIC_APP_URL ?? "").replace(/\/$/, "");
const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? "").replace(/\/$/, "");

/** Tautan ke rute aplikasi, mis. `appUrl("/register")`. */
export const appUrl = (path: string) => APP_URL + path;

/** Tautan ke halaman marketing, mis. `siteUrl("/kebijakan-privasi")`. */
export const siteUrl = (path: string) => SITE_URL + path;
