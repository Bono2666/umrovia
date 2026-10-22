/**
 * Helper akses API Umrovia (backend Django/DRF).
 * Base URL dari NEXT_PUBLIC_API_URL (Spec §18.4 — jangan percayai ?tenant_id dari client).
 */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ProblemDetail = {
  type: string;
  title: string;
  status: number;
  code: string;
  detail: string;
  request_id?: string;
  field_errors?: Record<string, string[]>;
};

export type Membership = {
  tenant: { id: string; slug: string; display_name: string; state: string };
  role: string | null;
  status: string;
  permissions: string[];
};

export type UserPayload = {
  id: string;
  email: string;
  full_name: string;
  email_verified: boolean;
  memberships: Membership[];
  /** Sesi switch aktif (S06); null = fallback membership ACTIVE pertama. */
  active_tenant_slug?: string | null;
};

/** Payload GET /trial/status (Spec §8.7). */
export type TrialStatus = {
  trial_status: string;
  started_at: string;
  ends_at: string;
  converted_at: string | null;
  dummy_bookings_used: number;
  dummy_bookings_limit: number;
  internal_users_used: number;
  internal_users_limit: number;
  trial_price_idr: number;
  can_convert_now: boolean;
};

/** Baris GET /memberships (S05). */
export type MembershipRow = {
  id: string;
  user: { id: string; email: string; full_name: string };
  role: string | null;
  role_id: string | null;
  status: string;
  permissions: string[];
};

/** Baris GET /roles (S05). */
export type RoleRow = {
  id: string;
  name: string;
  is_system: boolean;
  permissions: string[];
};

/** Payload GET/PATCH /tenant/settings (§5.1 — tiga bagian JSON bebas). */
export type SettingsPayload = {
  branding_json: Record<string, unknown>;
  invoice_config_json: Record<string, unknown>;
  rules_json: Record<string, unknown>;
};

/** Baris GET /bank-accounts (S05 — hanya nomor masked, §5.3). */
export type BankAccount = {
  id: string;
  bank_name: string;
  account_name: string;
  account_masked: string;
  active: boolean;
};

/**
 * Guard UI berbasis permission — SERVER tetap otoritas (semua endpoint
 * menegakkan permission sendiri); ini hanya untuk UX (sembunyikan/nonaktifkan).
 */
export function hasPermission(perms: string[], permission: string): boolean {
  return perms.includes("*") || perms.includes(permission);
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * Ambil token CSRF (S02): cookie `csrftoken` dibaca via JS; bila belum ada,
 * minta dulu lewat GET /auth/csrf (men-set cookie, Spec §8 logout pakai CSRF).
 */
export async function ensureCsrfToken(): Promise<string> {
  const existing = readCookie("csrftoken");
  if (existing) return existing;
  try {
    const response = await fetch(`${API_BASE}/api/v1/auth/csrf`, {
      credentials: "include",
    });
    const data = (await response.json().catch(() => ({}))) as {
      csrfToken?: string;
    };
    return data.csrfToken ?? "";
  } catch {
    return "";
  }
}

export function problemMessage(error: ProblemDetail): string {
  if (error.field_errors) {
    const first = Object.values(error.field_errors)[0]?.[0];
    if (first) return first;
  }
  return error.detail || "Terjadi kesalahan. Silakan coba lagi.";
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<{ ok: true; data: T } | { ok: false; error: ProblemDetail }> {
  try {
    const method = (init?.method ?? "GET").toUpperCase();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(init?.headers as Record<string, string> | undefined),
    };
    if (method !== "GET" && method !== "HEAD" && !headers["X-CSRFToken"]) {
      const csrf = await ensureCsrfToken();
      if (csrf) headers["X-CSRFToken"] = csrf;
    }
    const response = await fetch(`${API_BASE}/api/v1${path}`, {
      ...init,
      credentials: "include",
      headers,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return { ok: false, error: data as ProblemDetail };
    }
    return { ok: true, data: data as T };
  } catch (err) {
    return {
      ok: false,
      error: {
        type: "https://umrovia.com/problems/network",
        title: "Network error",
        status: 0,
        code: "network_error",
        detail: `Tidak dapat menghubungi API: ${String(err)}`,
      },
    };
  }
}
