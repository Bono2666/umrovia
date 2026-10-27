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
from modules.tenants.branches import (
    assert_branch_allowed,
    default_branch,
    require_full_scope,
    resolve_branch,
    scope_filter,
)
from modules.tenants.environment import assert_environment_writable, resolve_active_environment
from modules.tenants.rbac import require_permission
from modules.travel_finance import services as cash
from modules.travel_finance.models import (
    CashTransfer,
    ExpenseCategory,
    OpeningBalance,
    TravelBankAccount,
    TravelExpense,
    mask_account_number,
)
from modules.travel_finance.services import cash_rules


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
    payee = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    branch = serializers.UUIDField(required=False, allow_null=True)


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
        "approval_status": expense.approval_status, "approved_by_name": (expense.approved_by.full_name or expense.approved_by.email) if expense.approved_by_id else None,
        "approved_at": expense.approved_at.isoformat() if expense.approved_at else None, "rejection_reason": expense.rejection_reason,
        "payee": expense.payee, "has_evidence": bool(expense.evidence_key),
        "branch": {"id": str(expense.branch_id), "code": expense.branch.code, "name": expense.branch.name} if expense.branch_id else None,
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
        qs = scope_filter(TravelExpense.objects, request).filter(environment=resolve_active_environment(request.tenant)).select_related("departure__package", "bank_account", "created_by", "approved_by", "branch")
        params = request.query_params
        try:
            if params.get("from"):
                qs = qs.filter(spent_on__gte=date.fromisoformat(params["from"]))
            if params.get("to"):
                qs = qs.filter(spent_on__lte=date.fromisoformat(params["to"]))
            if params.get("departure"):
                qs = qs.filter(departure_id=UUID(params["departure"]))
            if params.get("branch"):
                qs = qs.filter(branch_id=UUID(params["branch"]))
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
        approval = params.get("approval", "")
        if approval not in {"", "APPROVED", "PENDING", "REJECTED"}:
            raise ValidationError({"approval": "Status persetujuan tidak dikenal."})
        if approval:
            qs = qs.filter(approval_status=approval)
        paginator = ExpensePagination()
        rows = paginator.paginate_queryset(qs.order_by("-spent_on", "-created_at", "id"), request)
        response = paginator.get_paginated_response([expense_payload(row) for row in rows])
        response.data["total_idr"] = qs.filter(voided_at__isnull=True, approval_status="APPROVED").aggregate(total=Sum("amount_idr"))["total"] or 0
        response.data["pending_count"] = scope_filter(TravelExpense.objects, request).filter(environment=resolve_active_environment(request.tenant), approval_status="PENDING", voided_at__isnull=True).count()
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
        branch = assert_branch_allowed(request, resolve_branch(data["branch"])) if "branch" in data else default_branch(request)
        # Maker-checker kas (MOD-11): pengeluaran menunggu persetujuan staf lain bila diaktifkan.
        pending = cash_rules(request.tenant)["maker_checker"]
        expense = TravelExpense.objects.create(
            tenant=request.tenant, environment=environment, spent_on=data["spent_on"], category=data["category"],
            amount_idr=data["amount_idr"], departure=departure, bank_account=account,
            description=data["description"].strip(), reference=data.get("reference", "").strip(), created_by=request.user,
            payee=data.get("payee", "").strip(), branch=branch, approval_status="PENDING" if pending else "APPROVED",
        )
        log_event(action="expenses.recorded", request=request, object_type="travel_expense", object_id=expense.pk, changes={"category": expense.category, "amount_idr": expense.amount_idr, "departure": departure.code if departure else None})
        return Response(expense_payload(expense), status=status.HTTP_201_CREATED)


class ExpenseVoidView(APIView):
    permission_classes = [IsAuthenticated, require_permission("expenses.write")]

    @transaction.atomic
    def post(self, request, expense_id):
        expense = scope_filter(TravelExpense.objects, request).select_for_update(of=("self",)).select_related("departure__package", "bank_account", "created_by").filter(pk=expense_id).first()
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


class ExpenseDecisionView(APIView):
    """Maker-checker pengeluaran (MOD-11): setujui/tolak oleh staf selain pencatat."""

    permission_classes = [IsAuthenticated, require_permission("expenses.approve")]
    action = "approve"

    def post(self, request, expense_id):
        expense = scope_filter(TravelExpense.objects, request).filter(pk=expense_id).first()
        if expense is None:
            raise NotFound("Pengeluaran tidak ditemukan.")
        assert_environment_writable(request.tenant, expense.environment)
        cash.decide_expense(expense_id=expense.pk, actor=request.user, approve=self.action == "approve", reason=str(request.data.get("reason") or ""))
        return Response(expense_payload(TravelExpense.objects.select_related("departure__package", "bank_account", "created_by", "approved_by", "branch").get(pk=expense.pk)))


class ExpenseEvidenceView(APIView):
    """Lampiran bukti pengeluaran (PDF/JPG/PNG, privat). Unggah oleh pencatat (`expenses.write`)."""

    def get_permissions(self):
        return [IsAuthenticated(), require_permission("expenses.write" if self.request.method == "POST" else "expenses.read")()]

    def post(self, request, expense_id):
        import uuid

        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        from modules.portal.files import inspect_upload

        expense = scope_filter(TravelExpense.objects, request).filter(pk=expense_id).first()
        if expense is None:
            raise NotFound("Pengeluaran tidak ditemukan.")
        assert_environment_writable(request.tenant, expense.environment)
        if expense.voided_at is not None:
            raise ValidationError({"expense": "Pengeluaran sudah dibatalkan."})
        data, ext = inspect_upload(request.FILES.get("file"))
        key = default_storage.save(f"tenants/{expense.tenant_id}/environments/{expense.environment}/expenses/{expense.pk}/{uuid.uuid4()}.{ext}", ContentFile(data))
        expense.evidence_key = key
        expense.save(update_fields=["evidence_key", "updated_at"])
        log_event(action="expenses.evidence_uploaded", request=request, object_type="travel_expense", object_id=expense.pk, changes={"bytes": len(data)})
        return Response(expense_payload(TravelExpense.objects.select_related("departure__package", "bank_account", "created_by", "approved_by", "branch").get(pk=expense.pk)))

    def get(self, request, expense_id):
        from django.core.files.storage import default_storage
        from django.http import HttpResponse

        from modules.portal.files import CONTENT_TYPES

        expense = scope_filter(TravelExpense.objects, request).filter(pk=expense_id).first()
        if expense is None or not expense.evidence_key:
            raise NotFound("Lampiran tidak ditemukan.")
        with default_storage.open(expense.evidence_key, "rb") as handle:
            data = handle.read()
        ext = expense.evidence_key.rsplit(".", 1)[-1]
        log_event(action="expenses.evidence_downloaded", request=request, object_type="travel_expense", object_id=expense.pk)
        response = HttpResponse(data, content_type=CONTENT_TYPES.get(ext, "application/octet-stream"))
        response["Content-Disposition"] = f'inline; filename="bukti-pengeluaran-{expense.pk}.{ext}"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


# ------------------------------------------------------------- kas & bank --
def _name(user):
    return (user.full_name or user.email) if user else None


def _account_label(account):
    return f"{account.bank_name} {account.account_masked}" if account else "Tunai"


def opening_payload(row):
    return {
        "id": str(row.pk), "bank_account": str(row.bank_account_id) if row.bank_account_id else None, "account": _account_label(row.bank_account),
        "as_of": row.as_of.isoformat(), "amount_idr": row.amount_idr, "reason": row.reason, "status": row.status, "status_label": row.get_status_display(),
        "created_by": _name(row.created_by), "decided_by": _name(row.decided_by), "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "decision_note": row.decision_note, "created_at": row.created_at.isoformat(),
    }


def transfer_payload(row):
    return {
        "id": str(row.pk), "transferred_on": row.transferred_on.isoformat(), "from_account": _account_label(row.from_account), "to_account": _account_label(row.to_account),
        "from_account_id": str(row.from_account_id) if row.from_account_id else None, "to_account_id": str(row.to_account_id) if row.to_account_id else None,
        "amount_idr": row.amount_idr, "description": row.description, "reference": row.reference,
        "branch": {"id": str(row.branch_id), "code": row.branch.code} if row.branch_id else None,
        "status": "VOIDED" if row.voided_at else "RECORDED", "void_reason": row.void_reason, "created_by": _name(row.created_by), "created_at": row.created_at.isoformat(),
    }


class OpeningBalanceSerializer(serializers.Serializer):
    bank_account = serializers.UUIDField(required=False, allow_null=True)
    as_of = serializers.DateField()
    amount_idr = serializers.IntegerField(min_value=-100_000_000_000, max_value=100_000_000_000)
    reason = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")


class TransferSerializer(serializers.Serializer):
    transferred_on = serializers.DateField()
    from_account = serializers.UUIDField(required=False, allow_null=True)
    to_account = serializers.UUIDField(required=False, allow_null=True)
    amount_idr = serializers.IntegerField(min_value=1, max_value=100_000_000_000)
    description = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    branch = serializers.UUIDField(required=False, allow_null=True)


class CashBookView(APIView):
    """GET /cash/book?from=&to=&branch= — saldo awal, mutasi dan saldo akhir per rekening/kas."""

    permission_classes = [IsAuthenticated, require_permission("bank_accounts.read")]

    def get(self, request):
        require_full_scope(request, "Buku kas")
        today = tenant_today(request.tenant)
        try:
            start = date.fromisoformat(request.query_params["from"]) if request.query_params.get("from") else today.replace(day=1)
            end = date.fromisoformat(request.query_params["to"]) if request.query_params.get("to") else today
            branch = resolve_branch(UUID(request.query_params["branch"])) if request.query_params.get("branch") else None
        except ValueError:
            raise ValidationError({"filter": "Tanggal (YYYY-MM-DD) atau cabang tidak valid."}) from None
        if start > end:
            raise ValidationError({"to": "Tanggal akhir tidak boleh sebelum tanggal awal."})
        rows = cash.ledger(request.tenant, resolve_active_environment(request.tenant), start, end, branch=branch)
        totals = {key: sum(row[key] for row in rows) for key in (*cash.BUCKETS, "closing_idr")}
        return Response({"from": start.isoformat(), "to": end.isoformat(), "rows": rows, "totals": totals, "rules": cash_rules(request.tenant)})


class CashSettingsView(APIView):
    def get_permissions(self):
        return [IsAuthenticated(), require_permission("bank_accounts.approve" if self.request.method == "PATCH" else "bank_accounts.read")()]

    def get(self, request):
        return Response(cash_rules(request.tenant))

    def patch(self, request):
        value = request.data.get("maker_checker")
        if type(value) is not bool:
            raise ValidationError({"maker_checker": "Harus boolean."})
        result = cash.set_cash_rules(request.tenant, maker_checker=value)
        log_event(action="cash.settings_updated", request=request, object_type="tenant_settings", object_id=request.tenant.pk, changes=result)
        return Response(result)


class OpeningBalanceListCreateView(APIView):
    def get_permissions(self):
        return [IsAuthenticated(), require_permission("bank_accounts.write" if self.request.method == "POST" else "bank_accounts.read")()]

    def get(self, request):
        require_full_scope(request, "Saldo awal")
        rows = OpeningBalance.objects.filter(environment=resolve_active_environment(request.tenant)).select_related("bank_account", "created_by", "decided_by")[:200]
        return Response({"results": [opening_payload(r) for r in rows]})

    @transaction.atomic
    def post(self, request):
        environment = resolve_active_environment(request.tenant)
        assert_environment_writable(request.tenant, environment)
        require_full_scope(request, "Saldo awal")
        serializer = OpeningBalanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        row = cash.request_opening_balance(tenant=request.tenant, environment=environment, bank_account_id=data.get("bank_account"), as_of=data["as_of"], amount_idr=data["amount_idr"], reason=data["reason"], actor=request.user)
        return Response(opening_payload(row), status=status.HTTP_201_CREATED)


class OpeningBalanceDecisionView(APIView):
    permission_classes = [IsAuthenticated, require_permission("bank_accounts.approve")]
    action = "approve"

    def post(self, request, balance_id):
        row = OpeningBalance.objects.filter(pk=balance_id, environment=resolve_active_environment(request.tenant)).first()
        if row is None:
            raise NotFound("Saldo awal tidak ditemukan.")
        assert_environment_writable(request.tenant, row.environment)
        row = cash.decide_opening_balance(tenant=request.tenant, balance_id=row.pk, actor=request.user, approve=self.action == "approve", note=str(request.data.get("note") or ""))
        return Response(opening_payload(row))


class TransferListCreateView(APIView):
    def get_permissions(self):
        return [IsAuthenticated(), require_permission("bank_accounts.write" if self.request.method == "POST" else "bank_accounts.read")()]

    def get(self, request):
        rows = scope_filter(CashTransfer.objects, request).filter(environment=resolve_active_environment(request.tenant)).select_related("from_account", "to_account", "branch", "created_by")[:200]
        return Response({"results": [transfer_payload(r) for r in rows]})

    @transaction.atomic
    def post(self, request):
        environment = resolve_active_environment(request.tenant)
        assert_environment_writable(request.tenant, environment)
        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        branch = assert_branch_allowed(request, resolve_branch(data["branch"])) if "branch" in data else default_branch(request)
        row = cash.record_transfer(tenant=request.tenant, environment=environment, data=data, actor=request.user, branch=branch)
        return Response(transfer_payload(row), status=status.HTTP_201_CREATED)


class TransferVoidView(APIView):
    permission_classes = [IsAuthenticated, require_permission("bank_accounts.write")]

    def post(self, request, transfer_id):
        row = scope_filter(CashTransfer.objects, request).filter(pk=transfer_id, environment=resolve_active_environment(request.tenant)).first()
        if row is None:
            raise NotFound("Transfer tidak ditemukan.")
        assert_environment_writable(request.tenant, row.environment)
        serializer = VoidExpenseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = cash.void_transfer(transfer_id=row.pk, actor=request.user, reason=serializer.validated_data["reason"])
        return Response(transfer_payload(row))
