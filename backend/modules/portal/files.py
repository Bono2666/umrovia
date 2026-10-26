"""Berkas dokumen jamaah: validasi, penyimpanan privat dan URL unduh bertanda tangan.

Spec §10: allowlist PDF/JPEG/PNG lewat magic bytes (nama/MIME klien diabaikan),
maks `PILGRIM_DOCUMENT_MAX_MB`, tanpa ACL publik, signed URL ≤ 10 menit dan
setiap unduhan diaudit. Pemindaian antimalware belum tersedia: PDF berisi aksi
aktif ditolak dan semua unggahan menunggu review petugas sebelum dipakai.
"""
import re
import uuid

from django.conf import settings
from django.core import signing
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException, ValidationError

from modules.pilgrims.models import Pilgrim, PilgrimDocument, PilgrimDocumentKind

SIGNATURES = [
    (b"%PDF-", "pdf", "application/pdf"),
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
]
CONTENT_TYPES = {ext: content_type for _, ext, content_type in SIGNATURES}
# Heuristik tanpa pemindai: PDF dengan skrip/peluncur/lampiran tersemat ditolak.
ACTIVE_PDF = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFile|RichMedia|XFA)\b")
SALT = "umrovia.pilgrim-document"


class Conflict(APIException):
    status_code = 409
    default_code = "document_conflict"


def inspect_upload(upload):
    """→ (data, ext). Menolak ukuran, format dan PDF aktif."""
    if upload is None:
        raise ValidationError({"file": "Pilih berkas untuk diunggah."})
    limit = settings.PILGRIM_DOCUMENT_MAX_MB * 1024 * 1024
    if not upload.size:
        raise ValidationError({"file": "Berkas kosong."})
    if upload.size > limit:
        raise ValidationError({"file": f"Ukuran maksimal {settings.PILGRIM_DOCUMENT_MAX_MB} MB."})
    data = upload.read(limit + 1)
    if len(data) > limit:
        raise ValidationError({"file": f"Ukuran maksimal {settings.PILGRIM_DOCUMENT_MAX_MB} MB."})
    for magic, ext, _ in SIGNATURES:
        if data.startswith(magic):
            if ext == "pdf" and ACTIVE_PDF.search(data):
                raise ValidationError({"file": "PDF berisi skrip atau lampiran tersemat tidak diterima. Simpan ulang sebagai PDF biasa atau foto."})
            return data, ext
    raise ValidationError({"file": "Format tidak didukung. Unggah PDF, JPG atau PNG."})


def add_uploaded_document(*, pilgrim_id, kind, data, ext):
    """Simpan berkas privat lalu catat versi baru (status UPLOADED → review petugas).

    Caller berada di konteks tenant pemilik jamaah. Versi dihitung di bawah
    lock baris jamaah; berkas dihapus lagi bila pencatatan gagal.
    """
    if kind not in PilgrimDocumentKind.values:
        raise ValidationError({"kind": "Jenis dokumen tidak dikenal."})
    pilgrim = Pilgrim.objects.select_for_update().get(pk=pilgrim_id)
    last = PilgrimDocument.objects.filter(pilgrim=pilgrim, kind=kind).order_by("-version").first()
    if last and last.status == "APPROVED":
        raise Conflict("Dokumen ini sudah disetujui. Hubungi travel bila perlu menggantinya.")
    key = f"tenants/{pilgrim.tenant_id}/environments/{pilgrim.environment}/pilgrims/{pilgrim.pk}/{kind}/{uuid.uuid4()}.{ext}"
    stored = default_storage.save(key, ContentFile(data))
    try:
        with transaction.atomic():
            return PilgrimDocument.objects.create(
                tenant_id=pilgrim.tenant_id, pilgrim=pilgrim, environment=pilgrim.environment,
                kind=kind, object_key=stored, version=(last.version + 1) if last else 1,
            )
    except IntegrityError:
        default_storage.delete(stored)
        raise Conflict("Dokumen sedang diunggah dari tempat lain. Muat ulang lalu coba lagi.") from None


def has_file(document):
    return bool(document.object_key) and default_storage.exists(document.object_key)


def signed_download_path(*, document, user, scope):
    """Path relatif (klien menambahkan origin API-nya); terikat dokumen, user dan cakupan."""
    token = signing.dumps({"t": str(document.tenant_id), "d": str(document.pk), "u": str(user.pk), "s": scope}, salt=SALT)
    return f"/api/v1/files/pilgrim-documents/{token}"


def read_download_token(token):
    """→ payload; `signing.SignatureExpired`/`BadSignature` bila kedaluwarsa/dipalsukan."""
    return signing.loads(token, salt=SALT, max_age=settings.SIGNED_URL_TTL_SECONDS)


def content_type(document):
    return CONTENT_TYPES.get(document.object_key.rsplit(".", 1)[-1].lower(), "application/octet-stream")
