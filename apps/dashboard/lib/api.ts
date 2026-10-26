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
  tenant: { id: string; slug: string; display_name: string; state: string; writable_environments?: string[] };
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
  /** Belum dipakai; data terpakai diarsipkan/dinonaktifkan/dibatalkan (S13+). */
  deletable: boolean;
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
  /** Belum dipakai; data terpakai diarsipkan/dinonaktifkan/dibatalkan (S13+). */
  deletable: boolean;
  id: string;
  environment: string;
  code: string;
  name: string;
  kind: string;
  description: string;
  duration_days: number;
  price_idr: number;
  room_prices: RoomPrice[];
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
  /** Belum dipakai; data terpakai diarsipkan/dinonaktifkan/dibatalkan (S13+). */
  deletable: boolean;
  has_bookings: boolean;
  id: string;
  environment: string;
  code: string;
  package_id: string;
  package_code: string;
  package_name: string;
  package_price_idr: number;
  room_prices: RoomPrice[];
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

export type DepartureStaff = { id: string; name: string };

export type RoomType = "QUAD" | "TRIPLE" | "DOUBLE" | "SINGLE";
export type RoomPrice = { room_type: RoomType; price_idr: number };
export type TravelInvoice = {
  id: string; environment: string; booking_id: string; booking_code: string;
  invoice_number: string; status: string; issue_at: string; due_at: string;
  total_idr: number; paid_idr: number; balance_idr: number; overdue: boolean;
  buyer_name: string; checksum: string;
  lines: {participant_id: string; pilgrim_name: string; description: string; amount_idr: number; room_type: string}[];
  dp_policy: PaymentRules;
};
export type PaymentRules = {dp_policy?: "any_positive"; dp_minimum_idr?: number; maker_checker?: boolean};
export type SaasWallet = {
  id: string | null; currency: "IDR"; environment: "demo" | "production";
  status: string; balance_idr: number; standard_rate_idr: number;
  estimated_participant_capacity: number; pending_participant_count: number;
  version: number; ledger_balance_idr: number; balance_matches_ledger: boolean;
  topup_available: boolean; provider: "manual"; topup_minimum_idr: number | null;
  pending_charge_count: number; pending_charge_idr: number; posted_charge_count: number; tenant_state: string;
  last_reconciliation: {at: string; consistent: boolean; variance_idr: number} | null;
};
export type SaasRefund = {
  id: string; charge_id: string; amount_idr: number; status: "REQUESTED" | "APPROVED" | "REJECTED";
  reason: string; decision_reason: string; created_at: string; decided_at: string | null; ledger_entry_id: string | null;
};
export type SaasCharge = {
  id: string; status: "PENDING" | "POSTED" | "VOID" | "REFUNDED"; saas_charge_status: string; pending_reason: string;
  unit_price_idr: number; price_version: string; booking_id: string; booking_code: string;
  booking_participant_id: string; booking_passenger_id: string; participant_status: string; pilgrim_name: string;
  eligible_at: string; charged_at: string | null; attempts: number; ledger_entry_id: string | null; void_reason: string;
  refund: SaasRefund | null; refundable: boolean;
};
export type ChargePreview = {
  environment: string; charges_applicable: boolean; price_version?: string; unit_fee_idr?: number; total_fee_idr?: number;
  participants: {booking_participant_id: string; pilgrim_name: string; allocation_idr: number; already_charged: boolean; will_attempt_charge: boolean; unit_fee_idr: number}[];
  wallet_balance_idr?: number; pending_queue_idr?: number; balance_after_idr?: number; sufficient?: boolean;
};
export type WalletTopup = {
  id: string; number: string; amount_idr: number; status: string; provider: string;
  instructions: {bank_name: string; account_name: string; account_number: string};
  payment_reference: string; evidence_ref: string; provider_txn_id: string;
  expires_at: string; created_at: string; paid_at: string | null;
  ledger_entry_id: string | null; reason: string;
};
export type WalletLedger = {
  id: string; sequence: number; kind: string; signed_amount_idr: number;
  balance_after_idr: number; reference_type: string; reference_id: string;
  description: string; created_at: string;
};
export type Paginated<T> = {count: number; next: string | null; previous: string | null; results: T[]};
export type TravelPayment = {
  id: string; environment: string; booking_id: string; booking_code: string;
  invoice_id: string; invoice_number: string; amount_idr: number; status: string;
  kind: string; method: string; received_at: string; reference: string; evidence_ref: string;
  simulated: boolean; reason: string; verified_at: string | null; verified_by_name: string | null;
  receipt: {id: string; receipt_no: string; status: string; checksum: string; issued_at: string} | null;
  allocations: {booking_participant_id: string; pilgrim_name: string; amount_idr: number}[];
  participants: {id: string; status: string; saas_charge_state: string; dp_eligible_at: string | null; saas_charge_status: string | null; unit_fee_idr: number | null}[];
};

/** Peserta booking (S09, §6.2 + PRD MOD-07 saverules). */
export type BookingParticipant = {
  id: string;
  pilgrim_id: string;
  pilgrim_code: string;
  pilgrim_name: string;
  /** UUID permanen unit billing "booking-jamaah" (POL-02/POL-04). */
  booking_passenger_id: string;
  participant_status: string;
  saas_charge_state: string;
  dp_eligible_at: string | null;
  pricing_snapshot: Record<string, unknown>;
};

/** Baris snapshot harga booking (S09, §5.2; UAT-04). */
export type BookingPriceLine = {
  id: string;
  item_type: string;
  description: string;
  qty: number;
  unit_price: number;
  amount: number;
};

/**
 * Payload booking (S09, §5.2/§8.3/UI-07): status header MOD-07, peserta
 * §6.2, kursi di-reserve atomik saat DRAFT → RESERVED, snapshot harga bebas
 * perubahan harga paket (UAT-04).
 */
export type Booking = {
  /** Belum dipakai; data terpakai diarsipkan/dinonaktifkan/dibatalkan (S13+). */
  deletable: boolean;
  /** Pendaftaran keberangkatan ditutup → booking boleh ditandai kedaluwarsa. */
  registration_closed: boolean;
  id: string;
  environment: string;
  code: string;
  departure_id: string;
  departure_code: string;
  departure_start_at: string;
  departure_status: string;
  available_seats: number;
  package_id: string;
  package_code: string;
  package_name: string;
  status: string;
  booked_at: string;
  notes: string;
  cancel_reason: string;
  canceled_by_name: string | null;
  created_by_name: string | null;
  participant_count: number;
  participants: BookingParticipant[];
  price_lines: BookingPriceLine[];
  total_amount: number;
};

/**
 * Syarat dokumen / checklist operasional (S10, §5.2 `document_requirements`,
 * UI-11; MOD-08): global (`package_id` null) atau per paket — spesifikasi
 * paket menimpa global per `kind`; `deadline_rule` menggerakkan gerbang
 * `before_ready` (READY keberangkatan + booking READY_TO_DEPART) /
 * `before_departure` (DEPARTED).
 */
export type ManifestRequirement = {
  id: string;
  environment: string;
  package_id: string | null;
  package_code: string | null;
  kind: "ktp" | "passport" | "photo" | "kk" | "other";
  mandatory: boolean;
  deadline_rule: "before_ready" | "before_departure";
};

/** Versi snapshot manifest (S10, §5.2 `manifest_versions`, §7.6; UI-12). */
export type ManifestVersion = {
  id: string;
  version_no: number;
  published_by_name: string | null;
  checksum: string;
  snapshot_object_key: string;
  created_at: string;
};

/**
 * Baris roster manifest (S10, §8.3/UI-12; UAT-14: hanya peserta keberangkatan
 * terkait, booking CANCELED/EXPIRED dikeluarkan). Field SELALU masked (§10.1);
 * nilai mentah NIK/paspor + kebutuhan khusus hanya di ekspor `pii=1` yang
 * berizin & diaudit (OPS-03).
 */
export type ManifestRow = {
  booking_id: string;
  booking_code: string;
  participant_id: string;
  participant_status: string;
  saas_charge_state: string;
  pilgrim_id: string;
  pilgrim_code: string;
  name: string;
  gender: string;
  birth_date: string | null;
  phone: string;
  identity_masked: string;
  passport_masked: string;
  docs: Record<string, string>;
  docs_required: string[];
  docs_missing: string[];
  docs_complete: boolean;
  /** Hanya terisi pada respons ekspor ber-PII. */
  identity_number?: string;
  passport_number?: string;
  address?: string;
  special_needs?: string;
};

/** Envelope GET /departures/{id}/manifest (S10; UI-11 checklist + UI-12 roster). */
export type ManifestEnvelope = {
  departure: {
    id: string;
    code: string;
    package_id: string;
    package_code: string;
    package_name: string;
    start_at: string;
    city_of_origin: string;
    route: string;
    status: string;
    seat_capacity: number;
    seats_taken: number;
    available_seats: number;
  };
  rows: ManifestRow[];
  row_count: number;
  versions: ManifestVersion[];
  requirements: ManifestRequirement[];
  /** Hanya ada bila `?checklist_gaps=1` — kekurangan gerbang READY. */
  checklist_gaps?: string[];
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
  /** Belum dipakai; data terpakai diarsipkan/dinonaktifkan/dibatalkan (S13+). */
  deletable: boolean;
  number_editable: boolean;
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
