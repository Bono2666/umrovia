"""Template bawaan notifikasi (NTF-03). Variabel ditulis `{{ nama_variabel }}`.

Template jamaah dapat diubah travel; variabel wajib tidak boleh dihilangkan.
Template untuk pengguna travel (owner) milik platform dan tidak dapat diubah.
Footer berisi identitas travel ditambahkan sistem dan tidak dapat diubah.
"""
from dataclasses import dataclass

COMMON = {
    "nama_travel": "Nama travel",
    "nama_jamaah": "Nama jamaah",
    "tautan_portal": "Tautan portal jamaah",
}


@dataclass(frozen=True)
class TemplateDef:
    key: str
    label: str
    audience: str  # "pilgrim" | "owner"
    subject: str
    body: str
    variables: dict
    required: tuple
    editable: bool = True


def _vars(**extra):
    return {**COMMON, **extra}


TEMPLATES = {t.key: t for t in [
    TemplateDef(
        "booking.reserved", "Booking berhasil", "pilgrim",
        "Booking {{ kode_booking }} berhasil — {{ nama_travel }}",
        "Assalamu'alaikum {{ nama_jamaah }},\n\n"
        "Booking {{ kode_booking }} untuk paket {{ paket }} sudah tercatat dan kursi Anda telah diamankan.\n"
        "Keberangkatan: {{ tanggal_berangkat }} dari {{ kota_asal }}.\n\n"
        "Pantau jadwal, pembayaran dan dokumen Anda di portal jamaah:\n{{ tautan_portal }}",
        _vars(kode_booking="Kode booking", paket="Nama paket", tanggal_berangkat="Tanggal berangkat", kota_asal="Kota keberangkatan"),
        ("kode_booking", "tanggal_berangkat"),
    ),
    TemplateDef(
        "booking.confirmed", "Booking dikonfirmasi", "pilgrim",
        "Booking {{ kode_booking }} dikonfirmasi — {{ nama_travel }}",
        "Assalamu'alaikum {{ nama_jamaah }},\n\n"
        "Alhamdulillah, booking {{ kode_booking }} untuk paket {{ paket }} telah dikonfirmasi oleh {{ nama_travel }}.\n"
        "Keberangkatan: {{ tanggal_berangkat }} dari {{ kota_asal }}.\n\n"
        "Langkah berikutnya adalah melengkapi dokumen perjalanan. Cek dokumen yang diminta di portal jamaah:\n{{ tautan_portal }}",
        _vars(kode_booking="Kode booking", paket="Nama paket", tanggal_berangkat="Tanggal berangkat", kota_asal="Kota keberangkatan"),
        ("kode_booking",),
    ),
    TemplateDef(
        "booking.document_process", "Dokumen sedang diproses", "pilgrim",
        "Dokumen perjalanan booking {{ kode_booking }} sedang diproses — {{ nama_travel }}",
        "Assalamu'alaikum {{ nama_jamaah }},\n\n"
        "Booking {{ kode_booking }} untuk paket {{ paket }} kini memasuki tahap pengurusan dokumen perjalanan oleh {{ nama_travel }}.\n\n"
        "Pastikan semua dokumen yang diminta sudah Anda kirim, dan pantau statusnya di portal jamaah:\n{{ tautan_portal }}",
        _vars(kode_booking="Kode booking", paket="Nama paket"),
        ("kode_booking",),
    ),
    TemplateDef(
        "booking.ready_to_depart", "Siap berangkat", "pilgrim",
        "Booking {{ kode_booking }} siap berangkat — {{ nama_travel }}",
        "Assalamu'alaikum {{ nama_jamaah }},\n\n"
        "Alhamdulillah, persiapan booking {{ kode_booking }} untuk paket {{ paket }} telah selesai dan Anda dinyatakan siap berangkat.\n\n"
        "Berangkat: {{ tanggal_berangkat }}\nKota keberangkatan: {{ kota_asal }}\nTitik kumpul: {{ titik_kumpul }}\n\n"
        "Informasi perjalanan selengkapnya di portal jamaah:\n{{ tautan_portal }}",
        _vars(kode_booking="Kode booking", paket="Nama paket", tanggal_berangkat="Tanggal berangkat", kota_asal="Kota keberangkatan", titik_kumpul="Titik kumpul"),
        ("kode_booking", "tanggal_berangkat"),
    ),
    TemplateDef(
        "booking.canceled", "Booking dibatalkan", "pilgrim",
        "Booking {{ kode_booking }} dibatalkan — {{ nama_travel }}",
        "Assalamu'alaikum {{ nama_jamaah }},\n\n"
        "Booking {{ kode_booking }} untuk paket {{ paket }} (keberangkatan {{ tanggal_berangkat }}) telah dibatalkan oleh {{ nama_travel }}.\n\n"
        "Untuk informasi lebih lanjut, termasuk pembayaran yang sudah Anda lakukan, silakan hubungi {{ nama_travel }}.",
        _vars(kode_booking="Kode booking", paket="Nama paket", tanggal_berangkat="Tanggal berangkat"),
        ("kode_booking",),
    ),
    TemplateDef(
        "invoice.issued", "Invoice terbit", "pilgrim",
        "Invoice {{ nomor_invoice }} — {{ nama_travel }}",
        "Assalamu'alaikum {{ nama_jamaah }},\n\n"
        "Invoice {{ nomor_invoice }} untuk booking {{ kode_booking }} telah terbit.\n"
        "Tagihan Anda: {{ tagihan }}\nJatuh tempo: {{ jatuh_tempo }}\n\n"
        "Rincian dan cara pembayaran tersedia di portal jamaah:\n{{ tautan_portal }}",
        _vars(nomor_invoice="Nomor invoice", kode_booking="Kode booking", tagihan="Tagihan jamaah", jatuh_tempo="Tanggal jatuh tempo"),
        ("nomor_invoice", "tagihan", "jatuh_tempo"),
    ),
    TemplateDef(
        "invoice.revised", "Invoice diperbarui", "pilgrim",
        "Invoice {{ nomor_invoice }} diperbarui — {{ nama_travel }}",
        "Assalamu'alaikum {{ nama_jamaah }},\n\n"
        "Invoice {{ nomor_invoice }} untuk booking {{ kode_booking }} telah diperbarui (versi {{ versi }}) dan menggantikan versi sebelumnya.\n"
        "Tagihan Anda kini: {{ tagihan }}\nJatuh tempo: {{ jatuh_tempo }}\n\n"
        "Rincian dan cara pembayaran tersedia di portal jamaah:\n{{ tautan_portal }}",
        _vars(nomor_invoice="Nomor invoice", kode_booking="Kode booking", versi="Versi invoice", tagihan="Tagihan jamaah", jatuh_tempo="Tanggal jatuh tempo"),
        ("nomor_invoice", "tagihan", "jatuh_tempo"),
    ),
    TemplateDef(
        "payment.verified", "Pembayaran diterima", "pilgrim",
        "Pembayaran {{ nominal }} diterima — {{ nama_travel }}",
        "Assalamu'alaikum {{ nama_jamaah }},\n\n"
        "Pembayaran Anda sebesar {{ nominal }} untuk booking {{ kode_booking }} telah kami verifikasi.\n"
        "Nomor kuitansi: {{ nomor_kuitansi }}\nTotal terbayar: {{ total_terbayar }}\nSisa tagihan: {{ sisa_tagihan }}\n\n"
        "Kuitansi dapat dilihat di portal jamaah:\n{{ tautan_portal }}",
        _vars(nominal="Nominal pembayaran", kode_booking="Kode booking", nomor_kuitansi="Nomor kuitansi", total_terbayar="Total terbayar", sisa_tagihan="Sisa tagihan"),
        ("nominal", "nomor_kuitansi", "sisa_tagihan"),
    ),
    TemplateDef(
        "payment.settled", "Pembayaran lunas", "pilgrim",
        "Pembayaran booking {{ kode_booking }} lunas — {{ nama_travel }}",
        "Assalamu'alaikum {{ nama_jamaah }},\n\n"
        "Alhamdulillah, pembayaran Anda untuk booking {{ kode_booking }} ({{ paket }}) telah lunas dengan total {{ total_terbayar }}.\n"
        "Keberangkatan: {{ tanggal_berangkat }}.\n\n"
        "Lengkapi dokumen perjalanan Anda melalui portal jamaah:\n{{ tautan_portal }}",
        _vars(kode_booking="Kode booking", paket="Nama paket", total_terbayar="Total terbayar", tanggal_berangkat="Tanggal berangkat"),
        ("kode_booking", "total_terbayar"),
    ),
    TemplateDef(
        "document.approved", "Dokumen disetujui", "pilgrim",
        "Dokumen {{ jenis_dokumen }} disetujui — {{ nama_travel }}",
        "Assalamu'alaikum {{ nama_jamaah }},\n\n"
        "Dokumen {{ jenis_dokumen }} yang Anda kirim telah diperiksa dan disetujui.\n\n"
        "Cek kelengkapan dokumen lainnya di portal jamaah:\n{{ tautan_portal }}",
        _vars(jenis_dokumen="Jenis dokumen"),
        ("jenis_dokumen",),
    ),
    TemplateDef(
        "document.rejected", "Dokumen perlu diperbaiki", "pilgrim",
        "Dokumen {{ jenis_dokumen }} perlu diperbaiki — {{ nama_travel }}",
        "Assalamu'alaikum {{ nama_jamaah }},\n\n"
        "Dokumen {{ jenis_dokumen }} yang Anda kirim belum dapat kami terima.\n"
        "Alasan: {{ alasan }}\n\n"
        "Silakan unggah ulang dokumen yang sudah diperbaiki melalui portal jamaah:\n{{ tautan_portal }}",
        _vars(jenis_dokumen="Jenis dokumen", alasan="Alasan penolakan"),
        ("jenis_dokumen", "alasan"),
    ),
    TemplateDef(
        "departure.changed", "Perubahan jadwal", "pilgrim",
        "Perubahan jadwal keberangkatan {{ paket }} — {{ nama_travel }}",
        "Assalamu'alaikum {{ nama_jamaah }},\n\n"
        "Ada perubahan pada keberangkatan {{ paket }} ({{ kode_keberangkatan }}): {{ perubahan }}.\n\n"
        "Jadwal terbaru:\nBerangkat: {{ tanggal_berangkat }}\nKembali: {{ tanggal_pulang }}\n"
        "Kota keberangkatan: {{ kota_asal }}\nTitik kumpul: {{ titik_kumpul }}\n\n"
        "Detail selengkapnya di portal jamaah:\n{{ tautan_portal }}",
        _vars(paket="Nama paket", kode_keberangkatan="Kode keberangkatan", perubahan="Daftar perubahan", tanggal_berangkat="Tanggal berangkat", tanggal_pulang="Tanggal kembali", kota_asal="Kota keberangkatan", titik_kumpul="Titik kumpul"),
        ("tanggal_berangkat", "perubahan"),
    ),
    TemplateDef(
        "saas.charge.pending", "Biaya layanan tertunda", "owner",
        "Saldo SaaS Wallet tidak cukup — {{ nama_travel }}",
        "Halo,\n\nPembayaran DP untuk booking {{ kode_booking }} sudah terverifikasi, tetapi biaya layanan Umrovia "
        "{{ nominal_biaya }} belum dapat dipotong ({{ alasan }}). Konfirmasi peserta menunggu hingga saldo mencukupi; "
        "data DP dan kuitansi jamaah tetap tersimpan.\n\nIsi saldo SaaS Wallet:\n{{ tautan_wallet }}",
        {"nama_travel": "Nama travel", "kode_booking": "Kode booking", "nominal_biaya": "Biaya layanan", "alasan": "Alasan", "tautan_wallet": "Tautan wallet"},
        ("kode_booking", "nominal_biaya"), editable=False,
    ),
    TemplateDef(
        "support.replied", "Balasan tiket dukungan", "owner",
        "Balasan untuk tiket {{ nomor_tiket }} — Umrovia",
        "Halo,\n\nTim Umrovia telah membalas tiket {{ nomor_tiket }} ({{ judul }}).\n\n"
        "Baca balasan dan tanggapi melalui menu Bantuan:\n{{ tautan_bantuan }}",
        {"nama_travel": "Nama travel", "nomor_tiket": "Nomor tiket", "judul": "Judul tiket", "tautan_bantuan": "Tautan bantuan"},
        ("nomor_tiket",), editable=False,
    ),
    TemplateDef(
        "trial.reminder", "Pengingat masa trial", "owner",
        "Masa trial Umrovia berakhir {{ sisa_hari }} hari lagi — {{ nama_travel }}",
        "Halo,\n\nMasa trial {{ nama_travel }} di Umrovia berakhir pada {{ tanggal_berakhir }} ({{ sisa_hari }} hari lagi). "
        "Setelah itu workspace otomatis aktif tanpa tagihan bulanan; biaya hanya Rp50.000 per jamaah dengan DP terverifikasi.\n\n"
        "Siapkan data produksi Anda di dashboard:\n{{ tautan_dashboard }}",
        {"nama_travel": "Nama travel", "sisa_hari": "Sisa hari", "tanggal_berakhir": "Tanggal berakhir", "tautan_dashboard": "Tautan dashboard"},
        ("sisa_hari", "tanggal_berakhir"), editable=False,
    ),
]}
