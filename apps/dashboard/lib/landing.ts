import type { UserPayload } from "@/lib/api";

/** Tujuan setelah login: staf → dashboard; akun portal saja → portal jamaah.
 *  `next` hanya diterima untuk path portal internal (tanpa open redirect). */
export function landingPath(me: UserPayload, next?: string | null): string {
  const hasWorkspace = me.memberships.some((m) => m.status === "ACTIVE");
  if (next && /^\/portal(\/|\?|$)/.test(next) && !next.startsWith("//")) return next;
  if (!hasWorkspace && me.portal_access_count > 0) return "/portal";
  return "/dashboard";
}

export function nextParam(): string | null {
  return typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("next");
}
