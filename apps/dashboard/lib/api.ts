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
  /** Grant portal jamaah aktif (S14) — akun portal tidak punya membership. */
  portal_access_count: number;
  /** Sesi switch aktif (S06); null = fallback membership ACTIVE pertama. */
  active_tenant_slug?: string | null;
  /** S18: staf platform → konsol /platform (server tetap memeriksa izin + MFA). */
  is_platform_staff?: boolean;
};

/** Payload jamaah (S07, Spec §8.3) — field sensitif SELALU masked (§10.1). */
export type Pilgrim = {
  /** Belum dipakai; data terpakai diarsipkan/dinonaktifkan/dibatalkan (S13+). */
  deletable: boolean;
  /** MOD-04: kelompok keluarga. */
  family?: {id: string; name: string; relation: string} | null;
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
  /** MOD-08 masa berlaku dokumen. */
  valid_from?: string | null; expires_at?: string | null; expired?: boolean;
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
  uploaded_at: string;
  /** Berkas nyata tersimpan (S14); dokumen lama hanya metadata. */
  has_file: boolean;
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
  /** MOD-05 varian harga, layanan tambahan, estimasi biaya per jamaah. */
  child_no_bed_price_idr?: number | null; infant_price_idr?: number | null;
  addons?: {code: string; name: string; price_idr: number}[];
  estimated_costs?: {category: string; description: string; amount_idr: number}[];
  estimated_cost_per_pax_idr?: number; estimated_margin_per_pax_idr?: number;
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
  lines: {participant_id: string; pilgrim_name: string; description: string; amount_idr: number; room_type: string; gross_idr?: number; discount_idr?: number; extra_idr?: number}[];
  dp_policy: PaymentRules;
  /** INV-03: revisi berversi — nomor tetap, versi naik. */
  version: number; gross_idr: number; discount_idr: number; extra_idr: number; revision_reason: string;
  revisions?: {version: number; total_idr: number; reason: string; revised_at: string; revised_by: string | null}[];
  revisable?: boolean;
};
export type PaymentRules = {dp_policy?: "any_positive"; dp_minimum_idr?: number; maker_checker?: boolean};
export type SaasWallet = {
  id: string | null; currency: "IDR"; environment: "demo" | "production";
  status: string; balance_idr: number; standard_rate_idr: number;
  estimated_participant_capacity: number; pending_participant_count: number;
  version: number; ledger_balance_idr: number; balance_matches_ledger: boolean;
  topup_available: boolean; provider: "manual"; topup_minimum_idr: number | null;
  pending_charge_count: number; pending_charge_idr: number; posted_charge_count: number; tenant_state: string;
  topup_methods: {manual: boolean; midtrans: boolean};
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
  payment_reference: string; evidence_ref: string; evidence_file: boolean; provider_txn_id: string;
  expires_at: string; created_at: string; paid_at: string | null;
  ledger_entry_id: string | null; reason: string;
  /** Midtrans: last gateway status/method and the Snap page while still payable. */
  gateway_status: string; payment_type: string; payment_url: string | null;
};
export type WalletLedger = {
  id: string; sequence: number; kind: string; signed_amount_idr: number;
  balance_after_idr: number; reference_type: string; reference_id: string;
  description: string; created_at: string;
};
export type Paginated<T> = {count: number; next: string | null; previous: string | null; results: T[]};
export type PlatformSession = {email: string; full_name: string; permissions: string[]; mfa: {enrolled: boolean; verified: boolean; recovery_codes_left: number}};
export type PlatformTrial = {status: string; started_at: string; ends_at: string; converted_at: string | null; dummy_used: number; dummy_limit: number};
export type PlatformTenant = {
  id: string; slug: string; display_name: string; legal_name: string; state: string; state_label: string; created_at: string; active_at: string | null;
  suspended_at: string | null; suspension_reason: string; terminated_at: string | null; owner_email: string; members: number; environments: string[];
  trial: PlatformTrial | null;
  usage?: {wallet_balance_idr: number; wallet_status: string | null; pending_charges: number; pending_charge_idr: number; posted_charges: number; active_bookings: number; active_participants: number};
};
export type PlatformLifecycleRequest = {id: string; kind: string; status: string; reason: string; requested_by: string; requested_at: string; decided_by: string | null; decided_at: string | null; decision_reason: string};
export type PlatformAuditRow = {id: string; occurred_at: string; action: string; object_type: string; object_id: string; tenant: string | null; actor: string; actor_platform: boolean; changes: Record<string, string | number | boolean>};
export type PlatformTenantDetail = PlatformTenant & {members_detail: {email: string; role: string | null; status: string; joined_at: string}[]; lifecycle_requests: PlatformLifecycleRequest[]; history: PlatformAuditRow[]; open_tickets: number};
export type SupportMessage = {id: string; created_at: string; from_platform: boolean; internal: boolean; body: string; author: string};
export type SupportTicket = {
  id: string; number: string; subject: string; category: string; category_label: string; status: string; status_label: string; priority: string;
  created_at: string; last_message_at: string; resolved_at: string | null; opened_by: string | null;
  tenant?: {id: string; slug: string; display_name: string; state: string}; assigned_to?: string | null; messages?: SupportMessage[]; diagnosis?: PlatformTenant;
};
export type LeadStage = "NEW" | "CONTACTED" | "QUALIFIED" | "QUOTED" | "WON" | "LOST";
export type LeadActivity = {id: string; kind: string; kind_label: string; body: string; actor: string | null; created_at: string};
export type Lead = {
  id: string; code: string; environment: string; name: string; phone: string; email: string; city: string; source: string; source_label: string;
  pax: number; notes: string; interest_package: {id: string; name: string} | null; interest_departure: {id: string; code: string; start_at: string} | null;
  stage: LeadStage; stage_label: string; stage_changed_at: string; lost_reason: string; owner: {id: string; name: string | null} | null;
  next_follow_up_at: string | null; follow_up_overdue: boolean; converted_pilgrim: {id: string; code: string; name: string} | null;
  converted_at: string | null; created_at: string; deletable: boolean;
  activities?: LeadActivity[]; duplicates?: {leads: {id: string; code: string; name: string; stage: string}[]; pilgrims: {id: string; code: string; name: string}[]};
};
export type LeadSummary = {
  stages: {stage: LeadStage; label: string; count: number}[]; total: number; open: number; conversion_rate: number | null;
  follow_up_overdue: number; follow_up_today: number; sources: {source: string; label: string; count: number; won: number}[];
};
export type ReportColumn = {key: string; label: string; type: "text" | "money" | "int" | "percent" | "date"};
export type ReportSection = {key: string; title: string; description: string; columns: ReportColumn[]; rows: Record<string, string | number | null>[]; totals: Record<string, string | number | null> | null; truncated: boolean};
export type Report = {
  report: "operational" | "finance" | "saas" | "sales" | "payments" | "commissions" | "pilgrims"; title: string; travel: string; environment: string; as_of: string; timezone: string;
  period: {from: string; to: string}; filters: {package: string; departure: string; status: string; agent?: string; account?: string; branch?: string}; note?: string;
  kpis: {key: string; label: string; value: number | null; type: ReportColumn["type"]; hint: string}[];
  sections: ReportSection[]; checks: {label: string; ok: boolean; detail: string}[];
};
export type TravelExpense = {
  id: string; environment: string; spent_on: string; category: string; category_label: string; amount_idr: number;
  departure: {id: string; code: string; package_name: string} | null; bank_account: {id: string; label: string} | null;
  description: string; reference: string; status: "RECORDED" | "VOIDED"; void_reason: string; voided_at: string | null;
  created_by_name: string | null; created_at: string;
  /** MOD-11 maker-checker, penerima dana, lampiran bukti, cabang. */
  approval_status: "APPROVED" | "PENDING" | "REJECTED"; approved_by_name: string | null; rejection_reason: string;
  payee: string; has_evidence: boolean; branch: {id: string; code: string; name: string} | null;
};
export type NotificationStatus = "PENDING" | "SENT" | "FAILED" | "DEAD";
export type NotificationDelivery = {
  id: string; created_at: string; event_type: string; template_key: string; template_label: string; template_version: number;
  channel: "EMAIL" | "IN_APP"; recipient_type: "PILGRIM" | "USER"; recipient_name: string; recipient_email: string;
  subject: string; status: NotificationStatus; attempts: number; resend_count: number; last_error: string;
  next_attempt_at: string | null; sent_at: string | null; read_at: string | null; body?: string;
};
export type NotificationLog = Paginated<NotificationDelivery> & {summary: Record<NotificationStatus, number>};
export type NotificationTemplate = {
  key: string; label: string; audience: "pilgrim" | "owner"; editable: boolean; subject: string; body: string;
  version: number; customized: boolean; default_subject: string; default_body: string;
  variables: {name: string; label: string; required: boolean}[];
};
export type PortalNotification = {id: string; access_id: string; travel: string; event_type: string; subject: string; body: string; created_at: string; read_at: string | null};
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
  /** MOD-07: nama pembayar pada invoice (kosong = peserta pertama). */
  payer_name: string;
  /** MOD-10: agen yang mendapat kredit penjualan. */
  agent: {id: string; code: string; name: string} | null;
  /** MOD-03: cabang pencatat. */
  branch: {id: string; code: string; name: string} | null;
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
  /** S15: kamar, DP diterima dan status pembayaran milik peserta ini. */
  room_type: string;
  dp_received: boolean;
  amount_idr: number;
  paid_idr: number;
  balance_idr: number;
  payment_status: "paid" | "partial" | "unpaid";
  /** Hanya terisi pada respons ekspor ber-PII. */
  identity_number?: string;
  passport_number?: string;
  address?: string;
  special_needs?: string;
};

/** Envelope GET /departures/{id}/manifest (S10; UI-11 checklist + UI-12 roster). */
export type ManifestEnvelope = {
  /** TBD-08: false = roster dibatasi cakupan cabang staf. */
  full_scope?: boolean;
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
  /** Ringkasan kesiapan (S15, OPS-06) atas seluruh roster, bukan hasil filter. */
  readiness?: ManifestReadiness;
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
  branch?: {id: string; code: string; name: string} | null;
  branches?: {id: string; code: string; name: string}[];
  branch_scope?: "ALL" | "OWN";
};

/** Baris GET /roles (S05). */
export type RoleRow = {
  id: string;
  name: string;
  is_system: boolean;
  permissions: string[];
  /** TBD-08 opsi C: ALL = semua cabang, OWN = cabang yang ditugaskan + data tanpa cabang. */
  branch_scope?: "ALL" | "OWN";
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

/** Unggah multipart (tanpa Content-Type manual agar browser menulis boundary). */
export async function apiUpload<T>(path: string, form: FormData): Promise<{ ok: true; data: T } | { ok: false; error: ProblemDetail }> {
  try {
    const csrf = await ensureCsrfToken();
    const response = await fetch(`${API_BASE}/api/v1${path}`, {
      method: "POST", body: form, credentials: "include",
      headers: csrf ? { "X-CSRFToken": csrf } : undefined,
      signal: AbortSignal.timeout(60_000),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) signalSessionExpired(data as ProblemDetail);
    return response.ok ? { ok: true, data: data as T } : { ok: false, error: data as ProblemDetail };
  } catch (err) {
    return { ok: false, error: { type: "https://umrovia.com/problems/network", title: "Network error", status: 0, code: "network_error", detail: `Unggahan gagal: ${String(err)}` } };
  }
}

/** Unduh dari path API bertanda tangan (cookie sesi ikut, tab tetap). */
export function downloadFromApi(path: string) {
  const link = document.createElement("a");
  link.href = `${API_BASE}${path}`;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

/**
 * Sesi berakhir (idle/absolut habis, atau keluar dari tab lain): API menjawab 403
 * `not_authenticated`. Shell yang sedang tampil mengarahkan ke login lewat event ini,
 * supaya halaman tidak salah menampilkan "belum diberi akses".
 */
export const SESSION_EXPIRED_EVENT = "umrovia-session-expired";

function signalSessionExpired(error: ProblemDetail) {
  if (error?.code === "not_authenticated" && typeof window !== "undefined") window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
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
      signalSessionExpired(data as ProblemDetail);
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

/** Portal jamaah (S14): hanya data milik jamaah pemilik grant. */
export type PortalDocumentVersion = {
  id: string; version: number; status: string; reason: string;
  uploaded_at: string; reviewed_at: string | null; has_file: boolean;
};
export type PortalDocumentItem = {
  kind: string; label: string; required: boolean; mandatory: boolean; deadline: string | null;
  latest: PortalDocumentVersion | null; history: PortalDocumentVersion[]; can_upload: boolean;
};
export type PortalBooking = {
  booking_id: string; code: string; status: string; participant_status: string; progress: number | null; room_type: string;
  departure: {code: string; package_name: string; start_at: string; end_at: string | null; city_of_origin: string; route: string; meeting_point: string; status: string};
  payment: {amount_idr: number; paid_idr: number; balance_idr: number; invoice_id: string | null; invoice_number: string | null; due_at: string | null; group_invoice: boolean};
  receipts: {id: string | null; number: string | null; kind: string; amount_idr: number; received_at: string; downloadable: boolean}[];
};
export type PortalProfile = {
  name: string; code: string; phone: string; email: string; address: string;
  emergency_contact_name: string; emergency_contact_phone: string; identity_masked: string; passport_masked: string;
};
export type PortalAccessView = {
  access_id: string; environment: string; travel: {name: string; phone: string};
  profile: PortalProfile; bookings: PortalBooking[];
  /** POR-05 pengumuman travel & POR-06 permintaan koreksi identitas. */
  announcements: {id: string; title: string; body: string; published_at: string | null; departure: {id: string; code: string} | null}[];
  change_requests: ChangeRequest[];
};
export type ChangeRequest = {
  id: string; status: "PENDING" | "APPROVED" | "REJECTED"; status_label: string; fields: string[];
  changes: {field: string; label: string; value: string}[]; reason: string; decision_note: string; created_at: string; decided_at: string | null;
  pilgrim?: {id: string; code: string; name: string};
};
export type PortalInviteInfo = {
  valid: boolean; code: string | null; detail: string; travel_name: string;
  pilgrim_name: string; email: string; account_exists: boolean;
};
export type PilgrimPortalStatus = {
  accesses: {id: string; email: string; status: string; created_at: string}[];
  pending_invite: {id: string; email: string; expires_at: string} | null;
};

export type ManifestReadiness = {
  participants: number; docs_complete: number; dp_received: number; fully_paid: number;
  confirmed: number; pending_charge: number; outstanding_idr: number;
  seat_capacity: number; seats_taken: number; available_seats: number;
  checklist_ready: boolean; gap_count: number;
};

// MOD-10 Agen & Komisi
export type AgentRef = {id: string; code: string; name: string};
export type Agent = AgentRef & {
  phone: string; email: string; business_id: string; bank_name: string; bank_account_name: string; bank_account_masked: string;
  area: string; level: string; active: boolean; notes: string; created_at: string;
  booking_count: number; commission_open_idr: number; commission_paid_idr: number;
};
export type CommissionPolicy = {
  id: string; name: string; agent: AgentRef | null; package: {id: string; name: string} | null;
  kind: "FIXED_PER_PAX" | "PERCENT_NET"; kind_label: string; amount_idr: number; percent: number;
  trigger: "DP_VERIFIED" | "FULLY_PAID"; trigger_label: string; valid_from: string | null; valid_until: string | null; active: boolean;
};
export type CommissionStatus = "ESTIMATED" | "ELIGIBLE" | "APPROVED" | "PAID" | "REVERSED";
export type Commission = {
  id: string; status: CommissionStatus; status_label: string; agent: AgentRef;
  booking: {id: string; code: string; status: string; departure_code: string; package_name: string};
  policy: {name: string; kind: string; amount_idr: number; percent: string; trigger: string};
  pax: number; basis_idr: number; amount_idr: number; eligible_at: string | null; approved_at: string | null; approved_by: string | null;
  paid_on: string | null; paid_by: string | null; bank_account: string | null; reference: string; expense_id: string | null;
  reversed_at: string | null; reverse_reason: string; review_note: string; created_at: string;
};
export type BookingAgentInfo = {
  agent: AgentRef | null; commission: Commission | null;
  history: {id: string; from_agent: AgentRef | null; to_agent: AgentRef | null; reason: string; changed_by: string | null; changed_at: string}[];
};

// MOD-03 Cabang
export type Branch = {id: string; code: string; name: string; manager_name: string; phone: string; address: string; active: boolean; member_count: number | null};
// MOD-06 Daftar tunggu
export type WaitlistEntry = {
  id: string; status: "WAITING" | "BOOKED" | "CANCELED"; status_label: string; position: number | null;
  departure: {id: string; code: string; package_name: string; start_at: string; available_seats: number};
  pilgrim: {id: string; code: string; name: string; phone: string}; room_type: string; notes: string; cancel_reason: string;
  booking: {id: string; code: string} | null; created_at: string; created_by_name: string | null;
};

// MOD-04 keluarga & riwayat
export type FamilyGroup = {id: string; name: string; notes: string; members: {id: string; code: string; name: string; relation: string; gender: string}[]};
export type PilgrimHistory = {
  trips: {booking: {id: string; code: string; status: string; booked_at: string}; departure: {id: string; code: string; start_at: string; status: string}; package: string; room_type: string; participant_status: string; price_idr: number | null; paid_idr: number}[];
  completed_trips: number; documents: {kind: string; version: number; status: string; uploaded_at: string; expires_at: string | null}[];
  change_requests: ChangeRequest[]; family: FamilyGroup | null;
};
