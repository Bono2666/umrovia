"""Rekening bank travel — Spec §5.3 travel_bank_accounts + §8.1 pola RBAC.

Keamanan: endpoint HANYA menerima `account_number` (write-only) dan menyimpan
`account_masked` (4 digit terakhir) — nomor penuh tidak pernah disimpan/dikirim
kembali; audit memakai nilai masked. Role: Finance/Owner (matriks §3);
Admin/Sales tanpa akses rekening.
"""
from datetime import date
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Sum
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.departures.models import Departure
from modules.payments.dates import tenant_today
from modules.payments.models import TravelPayment
from modules.tenants.environment import assert_environment_writable, resolve_active_environment
from modules.tenants.rbac import require_permission
from modules.travel_finance.models import ExpenseCategory, TravelBankAccount, TravelExpense, mask_account_number


def _payload(account: TravelBankAccount) -> dict:
    used = account.has_payments if hasattr(account, "has_payments") else TravelPayment.objects.filter(bank_account=account).exists()
    return {
        "id": str(account.id),
        "bank_name": account.bank_name,
        "account_name": account.account_name,
        "account_masked": account.account_masked,
        "active": account.active,
        "number_editable": not used,
        "deletable": not used,  # rekening terpakai dinonaktifkan, tidak dihapus
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

    @transaction.atomic
    def delete(self, request, bank_account_id):
        account = TravelBankAccount.objects.select_for_update().filter(pk=bank_account_id).first()
        if account is None:
            raise NotFound("Rekening tidak ditemukan di workspace ini.")
        if TravelPayment.objects.filter(bank_account=account).exists():
            raise ValidationError({"bank_account": "Rekening telah dipakai pada pembayaran. Nonaktifkan rekening agar riwayat tetap utuh."})
        log_event(action="bank_accounts.deleted", request=request, object_type="travel_bank_account", object_id=account.id, changes={"bank_name": account.bank_name, "account_masked": account.account_masked})
        account.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------ pengeluaran --


class ExpensePagination(PageNumberPagination):
    page_size = 50


class ExpenseSerializer(serializers.Serializer):
    spent_on = serializers.DateField()
    category = serializers.ChoiceField(choices=ExpenseCategory.choices)
    amount_idr = serializers.IntegerField(min_value=1, max_value=100_000_000_000)
    departure = serializers.UUIDField(required=False, allow_null=True)
    bank_account = serializers.UUIDField(required=False, allow_null=True)
    description = serializers.CharField(max_length=240)
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")


class VoidExpenseSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=240)


def expense_payload(expense: TravelExpense) -> dict:
    account = expense.bank_account
    departure = expense.departure
    return {
        "id": str(expense.pk), "environment": expense.environment, "spent_on": expense.spent_on.isoformat(),
        "category": expense.category, "category_label": expense.get_category_display(), "amount_idr": expense.amount_idr,
        "departure": {"id": str(departure.pk), "code": departure.code, "package_name": departure.package.name} if departure else None,
        "bank_account": {"id": str(account.pk), "label": f"{account.bank_name} {account.account_masked}"} if account else None,
        "description": expense.description, "reference": expense.reference,
        "status": "VOIDED" if expense.voided_at else "RECORDED", "void_reason": expense.void_reason,
        "voided_at": expense.voided_at.isoformat() if expense.voided_at else None,
        "created_by_name": (expense.created_by.full_name or expense.created_by.email) if expense.created_by else None,
        "created_at": expense.created_at.isoformat(),
    }


class ExpenseListCreateView(APIView):
    """GET/POST /expenses — pengeluaran travel (RPT-02); koreksi lewat pembatalan."""

    def get_permissions(self):
        grant = "expenses.write" if self.request.method == "POST" else "expenses.read"
        return [IsAuthenticated(), require_permission(grant)()]

    def get(self, request):
        qs = TravelExpense.objects.filter(environment=resolve_active_environment(request.tenant)).select_related("departure__package", "bank_account", "created_by")
        params = request.query_params
        try:
            if params.get("from"):
                qs = qs.filter(spent_on__gte=date.fromisoformat(params["from"]))
            if params.get("to"):
                qs = qs.filter(spent_on__lte=date.fromisoformat(params["to"]))
            if params.get("departure"):
                qs = qs.filter(departure_id=UUID(params["departure"]))
        except ValueError:
            raise ValidationError({"filter": "Tanggal (YYYY-MM-DD) atau keberangkatan tidak valid."}) from None
        if params.get("category"):
            if params["category"] not in ExpenseCategory.values:
                raise ValidationError({"category": "Kategori tidak dikenal."})
            qs = qs.filter(category=params["category"])
        status_filter = params.get("status", "")
        if status_filter not in {"", "RECORDED", "VOIDED"}:
            raise ValidationError({"status": "Status tidak dikenal."})
        if status_filter:
            qs = qs.filter(voided_at__isnull=status_filter == "RECORDED")
        paginator = ExpensePagination()
        rows = paginator.paginate_queryset(qs.order_by("-spent_on", "-created_at", "id"), request)
        response = paginator.get_paginated_response([expense_payload(row) for row in rows])
        response.data["total_idr"] = qs.filter(voided_at__isnull=True).aggregate(total=Sum("amount_idr"))["total"] or 0
        return response

    @transaction.atomic
    def post(self, request):
        environment = resolve_active_environment(request.tenant)
        assert_environment_writable(request.tenant, environment)
        serializer = ExpenseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["spent_on"] > tenant_today(request.tenant):
            raise ValidationError({"spent_on": "Tanggal pengeluaran tidak boleh di masa depan."})
        departure = None
        if data.get("departure"):
            departure = Departure.objects.filter(pk=data["departure"], environment=environment).select_related("package").first()
            if departure is None:
                raise ValidationError({"departure": "Keberangkatan tidak ditemukan."})
        account = None
        if data.get("bank_account"):
            account = TravelBankAccount.objects.filter(pk=data["bank_account"], active=True).first()
            if account is None:
                raise ValidationError({"bank_account": "Rekening tidak ditemukan atau nonaktif."})
        expense = TravelExpense.objects.create(
            tenant=request.tenant, environment=environment, spent_on=data["spent_on"], category=data["category"],
            amount_idr=data["amount_idr"], departure=departure, bank_account=account,
            description=data["description"].strip(), reference=data.get("reference", "").strip(), created_by=request.user,
        )
        log_event(action="expenses.recorded", request=request, object_type="travel_expense", object_id=expense.pk, changes={"category": expense.category, "amount_idr": expense.amount_idr, "departure": departure.code if departure else None})
        return Response(expense_payload(expense), status=status.HTTP_201_CREATED)


class ExpenseVoidView(APIView):
    permission_classes = [IsAuthenticated, require_permission("expenses.write")]

    @transaction.atomic
    def post(self, request, expense_id):
        expense = TravelExpense.objects.select_for_update(of=("self",)).select_related("departure__package", "bank_account", "created_by").filter(pk=expense_id).first()
        if expense is None:
            raise NotFound("Pengeluaran tidak ditemukan.")
        assert_environment_writable(request.tenant, expense.environment)
        serializer = VoidExpenseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if expense.voided_at is None:
            expense.voided_at, expense.void_reason, expense.voided_by = timezone.now(), serializer.validated_data["reason"].strip(), request.user
            expense.save(update_fields=["voided_at", "void_reason", "voided_by", "updated_at"])
            log_event(action="expenses.voided", request=request, object_type="travel_expense", object_id=expense.pk, changes={"amount_idr": expense.amount_idr, "reason": expense.void_reason})
        return Response(expense_payload(expense))
