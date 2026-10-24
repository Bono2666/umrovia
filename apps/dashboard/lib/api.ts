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

/** Payload jamaah (S07, Spec §8.3) — field sensitif SELALU masked (§10.1). */
export type Pilgrim = {
  id: string;
  code: string;
  environment: string;
  name: string;
  gender: string;
  birth_date: string | null;
  birth_place: string;
  nationality: string;
  marital_status: string;
  address: string;
  email: string;
  phone: string;
  emergency_contact_name: string;
  emergency_contact_phone: string;
  guardian_name: string;
  guardian_relation: string;
  special_needs?: string;
  identity_masked: string;
  passport_masked: string;
  passport_name: string;
  passport_issued_at: string | null;
  passport_expires_at: string | null;
  passport_place_of_issue: string;
  status: string;
  possible_duplicate_of: string | null;
};

/** Metadata dokumen jamaah (S07) — object_key ber-prefix tenant/environment. */
export type PilgrimDocument = {
  id: string;
  pilgrim_id: string;
  environment: string;
  kind: string;
  object_key: string;
  version: number;
  status: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  reason: string;
};

/** Payload paket (S08, Spec §5.2/§8.3, MOD-05) — harga integer rupiah (§10.1). */
export type TravelPackage = {
  id: string;
  environment: string;
  code: string;
  name: string;
  kind: string;
  description: string;
  duration_days: number;
  price_idr: number;
  inclusions: string[];
  exclusions: string[];
  cancellation_policy: string;
  payment_terms: string;
  status: string;
  published: boolean;
};

/**
 * Payload keberangkatan (S08, §5.2/§6.5, MOD-06) — kursi atomik (BR-002):
 * `seats_taken` hanya lewat layanan atomik; `available = capacity − taken −
 * blocked` (formula MOD-06).
 */
export type Departure = {
  id: string;
  environment: string;
  code: string;
  package_id: string;
  package_code: string;
  package_name: string;
  start_at: string;
  end_at: string | null;
  city_of_origin: string;
  route: string;
  meeting_point: string;
  seat_capacity: number;
  seats_blocked: number;
  seats_taken: number;
  available_seats: number;
  registration_deadline: string | null;
  lead_staff: string | null;
  lead_staff_name: string | null;
  status: string;
  notes: string;
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
 * Perhatian: Django memutasi cookie CSRF saat login — baca ulang cookie
 * setiap saat (jangan cache), dan beri timeout agar tidak menggantung.
 */
export async function ensureCsrfToken(): Promise<string> {
  const existing = readCookie("csrftoken");
  if (existing) return existing;
  try {
    const response = await fetch(`${API_BASE}/api/v1/auth/csrf`, {
      credentials: "include",
      signal: AbortSignal.timeout(10_000),
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
      // Timeout: request menggantung harus tetap resolve sebagai error —
      // supaya state "busy" tombol di UI selalu bisa pulih (tombol tak
      // pernah macet selamanya).
      signal: init?.signal ?? AbortSignal.timeout(15_000),
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
