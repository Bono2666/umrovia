# Matriks UAT MVP Umrovia

Skenario wajib Product Spec §14.2/§14.3 dan PRD §51.6, beserta test otomatis
yang membuktikannya. Setiap rujukan `tests/...::test_...` dijaga oleh
`tests/test_uat_traceability.py`: bila test diganti nama atau dihapus, CI
gagal. Kolom "Uji manual" berisi langkah singkat untuk penerimaan oleh
pengguna sebelum pilot.

Status per 27 Oktober 2026: semua test di bawah lulus pada suite penuh
(lihat [verifikasi S19](../development/SPRINT_S19_VERIFICATION.md)).

## Trial (TR)

| ID | Skenario | Hasil yang diharapkan | Bukti otomatis | Uji manual |
|---|---|---|---|---|
| TR01 | Provision lalu trial mulai | 30×24 jam tepat; waktu setup tidak dihitung | `tests/test_trial.py::test_tr01_provision_starts_trial_30_days` | Daftar → verifikasi email → cek tanggal akhir trial |
| TR02 | Buat 20 peserta demo | 20 berhasil, ke-21 ditolak | `tests/test_trial.py::test_tr02_demo_booking_quota_20_then_rejected` | Buat 21 booking demo |
| TR03 | Hapus record demo | Hitungan pemakaian tidak berkurang | `tests/test_trial.py::test_tr03_delete_demo_record_keeps_counter` | Hapus 1 booking demo, cek kuota |
| TR04 | 3 pengguna internal | Ke-4 ditolak; akun portal tidak dihitung | `tests/test_trial.py::test_tr04_internal_user_limit` | Undang staf ke-4 saat trial |
| TR05 | PDF demo invoice & manifest | Watermark DEMO, tanpa gateway/laporan produksi | `tests/test_operations.py::test_demo_documents_are_watermarked`, `tests/test_reports.py::test_demo_reports_are_marked` | Unduh invoice/manifest di workspace demo |
| TR06 | Simulasi DP demo | Ledger SaaS tidak berubah | `tests/test_billing.py::test_demo_verification_never_creates_charges` | Verifikasi DP simulasi, cek SaaS Wallet |
| TR07 | Pengingat H-7/H-3/H-1 diulang | Satu pesan logis per penerima/kanal/event | `tests/test_notifications.py::test_tr07_trial_reminders_once_per_recipient_and_day` | Cek log Notifikasi owner |
| TR08 | Trial berakhir | Otomatis aktif, tanpa tagihan/suspensi | `tests/test_trial.py::test_tr08_expiry_auto_active_without_bill` | — (job worker) |
| TR09 | Konversi dini | Sekali, tidak bisa kembali trial | `tests/test_trial.py::test_tr09_early_conversion_single_and_idempotent` | Konversi dari banner trial |
| TR10 | Akses lintas tenant/environment | 403/404, tanpa kebocoran | `tests/test_rls.py::test_rls_fail_closed_and_cross_tenant_isolation`, `tests/test_wallet.py::test_demo_read_never_exposes_production_ledger` | Coba buka URL data travel lain |

## Pembayaran & SaaS Wallet (PAY, INV)

| ID | Skenario | Hasil yang diharapkan | Bukti otomatis | Uji manual |
|---|---|---|---|---|
| PAY01 | DP terverifikasi, wallet Rp100rb | Charge Rp50rb sekali; saldo Rp50rb | `tests/test_billing.py::test_pay01_verified_dp_charges_once_and_confirms` | Top-up 100rb → verifikasi DP |
| PAY02 | Verifikasi berulang 10× paralel | Satu charge, satu kuitansi | `tests/test_billing_concurrency.py::test_pay02_ten_concurrent_verifications_one_charge`, `tests/test_payment_concurrency.py::test_ten_concurrent_verifications_issue_one_receipt` | Klik verifikasi berulang |
| PAY03 | DP terverifikasi, wallet 0 | DP VERIFIED; charge tertunda; kuitansi terbit | `tests/test_billing.py::test_pay03_zero_wallet_keeps_dp_receipt_and_restricts` | Verifikasi DP saat saldo 0 |
| PAY04 | Top-up setelah tertunda | Satu kredit; charge tertunda terpotong sekali | `tests/test_billing.py::test_pay04_topup_settles_pending_once_and_lifts_restriction`, `tests/test_midtrans.py::test_online_topup_settles_pending_saas_charges` | Top-up saat ada biaya tertunda |
| PAY05 | Webhook ganda/tidak berurutan | Tanpa kredit ganda, status tidak mundur | `tests/test_midtrans.py::test_concurrent_duplicate_notifications_credit_once`, `tests/test_midtrans.py::test_forged_or_stale_notification_never_credits` | Sandbox Midtrans: kirim ulang notifikasi |
| PAY06 | DP grup 3 peserta dialokasikan ke 1 | Hanya 1 charge | `tests/test_billing.py::test_pay06_group_dp_allocated_to_one_participant_charges_one` | Bayar DP grup ke 1 peserta |
| PAY07 | Cicilan kedua peserta sama | Tidak ada charge tambahan | `tests/test_billing.py::test_pay07_second_installment_never_charges_again` | Catat pelunasan |
| PAY08 | Batal sebelum DP terverifikasi | Tidak ada charge | `tests/test_billing.py::test_pay08_cancel_before_verified_dp_never_charges` | Batalkan booking tanpa DP |
| PAY09 | Batal setelah charge terpotong | Tidak ada refund otomatis; perlu persetujuan | `tests/test_billing.py::test_pay09_cancel_after_posted_charge_requires_approved_refund` | Ajukan refund di SaaS Wallet |
| PAY10 | 5 charge paralel, dana untuk 2 | Tepat 2 terpotong, 3 tertunda; saldo tidak negatif | `tests/test_billing_concurrency.py::test_pay10_five_charges_funds_for_two` | — (konkurensi) |
| INV01 | Terbitkan invoice dua kali | Satu nomor/versi aktif | `tests/test_payment_concurrency.py::test_concurrent_invoice_issuance_is_one_document` | Klik terbitkan invoice berulang |
| INV03 | Booking direservasi (INV-01) | Invoice terbit otomatis dengan pembayar & diskon/biaya tambahan per peserta; kegagalan konfigurasi tidak membatalkan reservasi | `tests/test_agents.py::test_reservation_auto_issues_invoice_with_payer_and_discounts`, `tests/test_payment_security.py::test_invoice_due_config_and_unimplemented_tax_are_not_ignored` | Reservasi kursi → buka Invoice |
| INV04 | Koreksi invoice (INV-03) | Revisi berversi: nomor tetap, versi lama + PDF diarsipkan; ditolak bila sudah ada pembayaran | `tests/test_agents.py::test_invoice_revision_is_versioned_and_blocked_after_payment` | Invoice → Revisi → beri diskon |
| INV05 | Diskon tanpa izin | Diskon perlu `bookings.discount`; alasan wajib; harga bersih minimal Rp1 | `tests/test_agents.py::test_discount_rules_and_permission` | Login Sales → coba isi diskon |
| INV02 | Kuitansi dikirim ulang | Kuitansi sama, tanpa duplikat | `tests/test_payments.py::test_verification_idempotency_and_exactly_one_receipt`, `tests/test_notifications.py::test_ntf01_provider_failure_retries_then_dead_letters_payment_untouched` | Kirim ulang email kuitansi |

## Portal, operasional, notifikasi, laporan (POR, OPS, NTF, RPT)

| ID | Skenario | Hasil yang diharapkan | Bukti otomatis | Uji manual |
|---|---|---|---|---|
| POR01 | Unggah, ditolak, unggah ulang | Riwayat versi, alasan terlihat jamaah | `tests/test_portal.py::test_upload_review_reupload_history` | Portal: unggah paspor buram → tolak → unggah ulang |
| POR02 | Tebak UUID invoice jamaah lain | 403/404, tanpa signed URL | `tests/test_portal.py::test_overview_shows_only_own_participant_in_group_booking`, `tests/test_portal.py::test_signed_download_bound_expiring_and_rechecked` | Ubah ID di URL portal |
| OPS01 | Dua staf berebut kursi terakhir | Satu berhasil, satu ditolak | `tests/test_departures.py::test_uat02_two_staff_race_for_last_seat`, `tests/test_departures.py::test_concurrent_reserve_never_overbooks` | Uji beban: 20 permintaan untuk 1 kursi (S19) |
| OPS02 | Siap berangkat tanpa dokumen wajib | Ditolak kecuali pengecualian disetujui | `tests/test_manifest.py::test_departure_ready_gate_blocks_until_docs_approved`, `tests/test_manifest.py::test_departure_ready_approved_exception_audited` | Tandai siap saat dokumen kurang |
| OPS03 | Ekspor manifest dengan PII tanpa izin | Ditolak dan diaudit | `tests/test_manifest.py::test_export_csv_pii_without_permission_denied_and_audited`, `tests/test_operations.py::test_pii_exports_require_permission_and_are_audited` | Login Operations → ekspor dengan data pribadi |
| NTF01 | Pengiriman email gagal | Antrean retry; pembayaran tidak terpengaruh | `tests/test_notifications.py::test_ntf01_provider_failure_retries_then_dead_letters_payment_untouched`, `tests/test_notifications.py::test_hook_failure_never_breaks_payment` | Matikan SMTP, verifikasi DP, cek Notifikasi |
| RPT01 | Rekonsiliasi laporan keuangan as-of | Sama dengan total transaksi sumber | `tests/test_reports.py::test_rpt01_finance_report_equals_source_records` | Bandingkan laporan dengan daftar Pembayaran |
| RPT02 | Laporan SaaS wallet vs kas travel | Agregat terpisah sepenuhnya | `tests/test_reports.py::test_rpt02_saas_wallet_report_is_separate_from_travel_cash` | Bandingkan tab Keuangan dan SaaS Wallet |

## Keamanan (SEC) dan gate platform

| ID | Skenario | Hasil yang diharapkan | Bukti otomatis | Uji manual |
|---|---|---|---|---|
| SEC01 | Menyisipkan `tenant_id` travel lain | Diabaikan/ditolak; RLS memblokir | `tests/test_payment_security.py::test_cross_tenant_financial_objects_denied`, `tests/test_wallet.py::test_optional_minimum_and_unknown_field`, `tests/test_rls.py::test_rls_fail_closed_and_cross_tenant_isolation` | — |
| SEC02 | Signed download kedaluwarsa | Ditolak | `tests/test_portal.py::test_signed_download_bound_expiring_and_rechecked` | Buka tautan unduh setelah 10 menit |
| SEC03 | Replay permintaan refund/adjustment | Satu entri ledger kompensasi | `tests/test_billing_concurrency.py::test_sec03_concurrent_refund_approvals_credit_once` | — |
| PLT01 | Konsol platform tanpa MFA | Ditolak `mfa_required`; kode tidak bisa dipakai ulang | `tests/test_platform_console.py::test_mfa_enrollment_verify_replay_and_recovery` | Login staf → daftar MFA |
| PLT02 | Respons konsol platform | Tanpa data pribadi jamaah | `tests/test_platform_console.py::test_platform_responses_contain_no_pilgrim_pii` | Telusuri konsol, cari nama jamaah |
| PLT03 | Suspend tenant | API & portal tertutup, Bantuan tetap | `tests/test_platform_console.py::test_suspend_blocks_workspace_and_portal_then_reactivate` | Suspend travel uji dari konsol |
| SEC-REL | Setting produksi, host/CSRF/CORS, log tanpa PII | `check --deploy` bersih; tanpa kebocoran | `tests/test_release_security.py::test_production_settings_pass_deploy_check`, `tests/test_release_security.py::test_logs_never_contain_pilgrim_pii`, `tests/test_release_security.py::test_csrf_enforced_for_session_writes` | `infra/deploy/smoke.sh` di staging |

## Alur ujung ke ujung (§14.3) dan operasi

| ID | Skenario | Hasil yang diharapkan | Bukti otomatis | Uji manual |
|---|---|---|---|---|
| E2E | signup → 20 dummy → konversi → top-up → booking → DP → charge → kuitansi → unggah dokumen → manifest → berangkat → laporan | Semua langkah berhasil; laporan cocok; integritas utuh | `tests/test_e2e_mvp.py::test_mvp_end_to_end_flow` | Ulangi alur di staging dengan akun uji |
| OPS-BKP | Backup terenkripsi & restore | Restore lengkap, integritas OK, hitungan sama | `tests/test_release_security.py::test_integrity_check_passes_and_detects_tampering` + drill `infra/backup/restore_drill.sh` | Drill bulanan (runbook restore) |
| PERF | Daftar besar tanpa N+1 | Query konstan, paginasi | `tests/test_performance.py::test_list_query_count_does_not_grow_per_row`, `tests/test_performance.py::test_list_endpoints_paginate_on_request` | `infra/load/load_test.py` di staging |

## Pasca-MVP: CRM & Lead (MOD-19, ADR-0015)

| ID | Skenario | Hasil yang diharapkan | Bukti otomatis | Uji manual |
|---|---|---|---|---|
| CRM01 | Lead dengan telepon yang sudah ada | Peringatan duplikat (lead/jamaah), bisa tetap disimpan | `tests/test_crm.py::test_create_lead_normalizes_and_detects_duplicates` | Tambah lead dengan nomor jamaah lama |
| CRM02 | Tahap, alasan tidak jadi, follow-up terlambat | LOST wajib alasan; WON hanya lewat konversi; follow-up terlambat terhitung | `tests/test_crm.py::test_stage_rules_activities_and_follow_up` | Catat WA dengan follow-up kemarin |
| CRM03 | Konversi lead → jamaah → booking | Jamaah dibuat/ditautkan sekali; halaman Booking terisi | `tests/test_crm.py::test_convert_to_new_or_existing_pilgrim` | "Jadikan jamaah" → "Buat booking" |
| CRM04 | Izin & isolasi | Finance/Operations 403; travel lain 404; RLS | `tests/test_crm.py::test_permissions_and_owner_choices`, `tests/test_crm.py::test_tenant_isolation_and_rls` | Login Finance → menu Leads tidak tampil |

## Agen & Komisi (MOD-10, ADR-0016) dan laporan MOD-13

| ID | Skenario | Hasil yang diharapkan | Bukti otomatis | Uji manual |
|---|---|---|---|---|
| UAT-09 | Agen menerima komisi setelah syarat tercapai | Komisi sesuai snapshot kebijakan; ESTIMATED → ELIGIBLE → APPROVED → PAID; pembayaran tercatat sebagai pengeluaran | `tests/test_agents.py::test_commission_lifecycle_paid_creates_expense` | Booking beragen → verifikasi DP → Komisi Agen → Setujui → Bayar |
| UAT-10 | Booking dibatalkan / agen diganti | Komisi belum dibayar REVERSED; histori agen tercatat | `tests/test_agents.py::test_cancel_and_agent_change_reverse_commission`, `tests/test_agents.py::test_manual_reversal_is_not_recreated_and_no_policy_means_no_commission` | Batalkan booking beragen |
| AGT01 | Izin & isolasi agen | Sales baca saja; Operations 403; travel lain 404; RLS | `tests/test_agents.py::test_agent_permissions_and_isolation` | Login Sales → menu Agen |
| RPT07 | Laporan booking/penjualan, pembayaran, komisi | Gross − diskon + tambahan = net; per rekening/petugas; komisi dibayar = pengeluaran komisi | `tests/test_agents.py::test_sales_payments_and_commission_reports` | Laporan → tab baru, unduh XLSX |

## Operasional & kas (MOD-02/03/06/11, ADR-0017)

| ID | Skenario | Hasil yang diharapkan | Bukti otomatis | Uji manual |
|---|---|---|---|---|
| BR01 | Cabang & cabang default staf | Booking baru terisi cabang default; cabang nonaktif ditolak; laporan per cabang | `tests/test_operations_b.py::test_branches_master_default_and_booking_filter` | Cabang → atur default staf → buat booking |
| WL01 | Keberangkatan penuh | Daftar tunggu hanya saat penuh, FIFO, menjadi booking draf saat kursi kosong | `tests/test_operations_b.py::test_waitlist_only_when_full_and_fifo_booking` | Batalkan booking pada keberangkatan penuh → Daftar Tunggu → Buat booking |
| CASH01 | Saldo awal, transfer, koreksi berotorisasi | Transfer tidak mengubah total kas; koreksi saldo awal disetujui staf lain | `tests/test_operations_b.py::test_opening_balance_transfers_and_cash_book` | Kas & Bank → Saldo awal → Transfer |
| CASH02 | Maker-checker pengeluaran & lampiran | Pengeluaran menunggu persetujuan staf lain; bukti PDF/JPG/PNG tersimpan privat | `tests/test_operations_b.py::test_expense_maker_checker_and_evidence` | Finance catat pengeluaran → Owner setujui |
| DSH01 | Dashboard KPI | KPI, pengingat dan grafik sesuai izin role | `tests/test_operations_b.py::test_dashboard_summary_respects_permissions` | Buka Ringkasan sebagai Owner dan Operations |

## Keamanan sesi, portal & data jamaah (AUTH, POR, MOD-04/05/08, ADR-0018)

| ID | Skenario | Hasil yang diharapkan | Bukti otomatis | Uji manual |
|---|---|---|---|---|
| AUTH02 | Login sukses/gagal, keluar dari semua perangkat, batas sesi | Semua tercatat; sesi perangkat lain & sesi melewati batas absolut berakhir | `tests/test_portal_data_c.py::test_login_audit_logout_all_and_absolute_timeout`, `tests/test_portal_data_c.py::test_password_reset_ends_existing_sessions` | Akun Saya → Keluar dari semua perangkat |
| AUTH05 | Owner menangguhkan, reset sandi, akhiri sesi anggota | Akses ditolak saat ditangguhkan; email reset terkirim; riwayat tercatat | `tests/test_portal_data_c.py::test_owner_suspends_resets_and_revokes_member_sessions` | Pengguna & Role → Keamanan |
| POR05 | Pengumuman per keberangkatan | Hanya jamaah rombongan terkait yang melihat; draf tidak tampil | `tests/test_portal_data_c.py::test_announcements_targeting_and_portal_visibility` | Pengumuman Portal → buka portal jamaah |
| POR06 | Koreksi identitas dari portal | Nilai terenkripsi, diterapkan hanya setelah disetujui staf | `tests/test_portal_data_c.py::test_identity_change_request_encrypted_and_verified_by_staff` | Portal → Koreksi data identitas → Jamaah → Setujui |
| PIL01 | Keluarga, riwayat, ekspor jamaah | Satu kepala keluarga; ekspor termask kecuali Owner; diaudit | `tests/test_portal_data_c.py::test_family_history_and_authorized_export` | Jamaah → detail → Keluarga; Ekspor Excel |
| PKG01 | Harga anak/bayi & layanan tambahan | Usia divalidasi; invoice memuat kategori & layanan tambahan | `tests/test_portal_data_c.py::test_price_variants_addons_flow_to_invoice` | Paket → varian; Booking → kategori & layanan |
| DOC01 | Masa berlaku dokumen & laporan Jamaah | Dokumen kedaluwarsa tidak bisa disetujui; ditandai bila habis sebelum berangkat | `tests/test_portal_data_c.py::test_document_validity_metadata_and_pilgrim_report` | Review dokumen dengan tanggal berlaku → Laporan Jamaah |

