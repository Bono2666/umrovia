"""Rekening bank travel — Spec §5.3 travel_bank_accounts + §8.1 pola RBAC.

Keamanan: endpoint HANYA menerima `account_number` (write-only) dan menyimpan
`account_masked` (4 digit terakhir) — nomor penuh tidak pernah disimpan/dikirim
kembali; audit memakai nilai masked. Role: Finance/Owner (matriks §3);
Admin/Sales tanpa akses rekening.
"""
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.payments.models import TravelPayment
from modules.tenants.rbac import require_permission
from modules.travel_finance.models import TravelBankAccount, mask_account_number


def _payload(account: TravelBankAccount) -> dict:
    return {
        "id": str(account.id),
        "bank_name": account.bank_name,
        "account_name": account.account_name,
        "account_masked": account.account_masked,
        "active": account.active,
        "number_editable": not (account.has_payments if hasattr(account, "has_payments") else TravelPayment.objects.filter(bank_account=account).exists()),
    }


class CreateBankAccountSerializer(serializers.Serializer):
    bank_name = serializers.CharField(max_length=100)
    account_name = serializers.CharField(max_length=160)
    account_number = serializers.CharField(max_length=34, min_length=4, write_only=True)


class PatchBankAccountSerializer(serializers.Serializer):
    bank_name = serializers.CharField(max_length=100, required=False)
    account_name = serializers.CharField(max_length=160, required=False)
    active = serializers.BooleanField(required=False)
    account_number = serializers.RegexField(r"^\d{8,32}$", required=False, write_only=True)


class BankAccountsListCreateView(APIView):
    """GET/POST /bank-accounts — daftar & tambah rekening travel (§5.3)."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), require_permission("bank_accounts.write")()]
        return [IsAuthenticated(), require_permission("bank_accounts.read")()]

    def get(self, request):
        accounts = TravelBankAccount.objects.annotate(has_payments=Exists(TravelPayment.objects.filter(bank_account_id=OuterRef("pk"))))
        return Response({"results": [_payload(a) for a in accounts]}, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = CreateBankAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        masked = mask_account_number(serializer.validated_data["account_number"])
        duplicate = TravelBankAccount.objects.filter(
            bank_name=serializer.validated_data["bank_name"], account_masked=masked
        ).exists()
        if duplicate:
            raise ValidationError(
                {"account_number": "Rekening dengan nomor terakhir sama sudah terdaftar."}
            )
        try:
            account = TravelBankAccount.objects.create(
                tenant=request.tenant,  # manager scoped TIDAK meng-inject kolom saat create
                bank_name=serializer.validated_data["bank_name"],
                account_name=serializer.validated_data["account_name"],
                account_masked=masked,
            )
        except IntegrityError as exc:
            if "uq_bank_account_masked" not in str(exc):
                raise  # bug programming lain ≠ duplikat (biarkan 500)
            raise ValidationError(
                {"account_number": "Rekening dengan nomor terakhir sama sudah terdaftar."}
            ) from exc
        log_event(
            action="bank_accounts.created",
            request=request,
            object_type="travel_bank_account",
            object_id=account.id,
            changes={
                "bank_name": account.bank_name,
                "account_masked": account.account_masked,  # masked — nomor asli tak masuk audit
            },
        )
        return Response({"bank_account": _payload(account)}, status=status.HTTP_201_CREATED)


class BankAccountDetailView(APIView):
    """Correct metadata; number corrections only before the first payment.

    Used accounts retain their number. Deactivate and add a new account instead.
    """

    permission_classes = [IsAuthenticated, require_permission("bank_accounts.write")]

    @transaction.atomic
    def patch(self, request, bank_account_id):
        account = TravelBankAccount.objects.select_for_update().filter(pk=bank_account_id).first()
        if account is None:
            raise NotFound("Rekening tidak ditemukan di workspace ini.")
        serializer = PatchBankAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data:
            raise serializers.ValidationError({"detail": "Tidak ada perubahan yang dikirim."})
        if "account_number" in serializer.validated_data:
            if TravelPayment.objects.filter(bank_account=account).exists():
                raise ValidationError({"account_number": "Nomor rekening telah dipakai pada pembayaran. Nonaktifkan rekening lama dan tambahkan rekening baru untuk mempertahankan riwayat."})
            account.account_masked = mask_account_number(serializer.validated_data.pop("account_number"))
        for field, value in serializer.validated_data.items():
            setattr(account, field, value)
        try:
            with transaction.atomic():
                account.save()
        except IntegrityError:
            raise ValidationError({"account_number": "Rekening dengan nama bank dan nomor terakhir sama sudah terdaftar."}) from None
        log_event(
            action="bank_accounts.updated",
            request=request,
            object_type="travel_bank_account",
            object_id=account.id,
            changes={"updated_fields": sorted(request.data.keys())},
        )
        return Response({"bank_account": _payload(account)}, status=status.HTTP_200_OK)
