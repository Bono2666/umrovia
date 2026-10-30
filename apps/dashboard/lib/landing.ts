import type { UserPayload } from "@/lib/api";

/** Tujuan setelah login: staf → dashboard; akun portal saja → portal jamaah.
 *  `next` hanya diterima untuk path portal internal (tanpa open redirect). */
export function landingPath(me: UserPayload, next?: string | null): string {
  const hasWorkspace = me.memberships.some((m) => m.status === "ACTIVE");
  if (next && /^\/(portal|platform)(\/|\?|$)/.test(next) && !next.startsWith("//")) return next;
  if (!hasWorkspace && me.is_platform_staff) return "/platform";
  if (!hasWorkspace && me.portal_access_count > 0) return "/portal";
  return "/dashboard";
}

/** Login dibuka dari portal jamaah (`?next=/portal…`): akun portal hanya lewat undangan travel. */
export function isPortalNext(next: string | null): boolean {
  return !!next && /^\/portal(\/|\?|$)/.test(next);
}

export function nextParam(): string | null {
  return typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("next");
}
