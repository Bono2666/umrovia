from rest_framework import serializers

from modules.payments.models import TravelInvoice
from modules.travel_finance.models import TravelBankAccount


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: "Field tidak dikenal." for key in unknown})
        return super().to_internal_value(data)


class IssueInvoiceSerializer(StrictSerializer):
    due_at = serializers.DateField(required=False)
    buyer_name = serializers.CharField(required=False, allow_blank=True, max_length=160)


class AllocationSerializer(StrictSerializer):
    booking_participant_id = serializers.UUIDField()
    amount_idr = serializers.IntegerField(min_value=1, max_value=10_000_000_000_000)


class PaymentCreateSerializer(StrictSerializer):
    invoice = serializers.PrimaryKeyRelatedField(queryset=TravelInvoice.objects)
    amount_idr = serializers.IntegerField(min_value=1, max_value=10_000_000_000_000)
    kind = serializers.ChoiceField(choices=["DP", "INSTALLMENT", "BALANCE"])
    method = serializers.ChoiceField(choices=["TRANSFER", "CASH"])
    received_at = serializers.DateTimeField()
    bank_account = serializers.PrimaryKeyRelatedField(queryset=TravelBankAccount.objects, required=False, allow_null=True)
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    evidence_ref = serializers.CharField(max_length=512, required=False, allow_blank=True)
    allocations = AllocationSerializer(many=True, allow_empty=False)
    simulate = serializers.BooleanField(default=False)
    submit = serializers.BooleanField(default=True)


class PaymentActionSerializer(StrictSerializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    verification_note = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    allocations = AllocationSerializer(many=True, required=False)
    verified_received_at = serializers.DateTimeField(required=False)
    evidence_ref = serializers.CharField(required=False, allow_blank=True, max_length=512)


class PaymentEvidenceSerializer(StrictSerializer):
    reference = serializers.CharField(required=False, allow_blank=True, max_length=120)
    evidence_ref = serializers.CharField(required=False, allow_blank=True, max_length=512)


class PaymentRulesSerializer(StrictSerializer):
    dp_policy = serializers.ChoiceField(choices=["any_positive"], required=False)
    dp_minimum_idr = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=10_000_000_000)
    maker_checker = serializers.BooleanField(required=False)


def receipt_payload(receipt):
    return {"id": str(receipt.pk), "receipt_no": receipt.receipt_no, "status": receipt.status, "checksum": receipt.checksum, "issued_at": receipt.issued_at.isoformat()}


def invoice_payload(invoice):
    from modules.payments.dates import tenant_today

    return {
        "id": str(invoice.pk), "environment": invoice.environment, "booking_id": str(invoice.booking_id),
        "booking_code": invoice.booking.code, "invoice_number": invoice.invoice_number,
        "status": invoice.status, "issue_at": invoice.issue_at.isoformat(), "due_at": invoice.due_at.isoformat(),
        "total_idr": invoice.total_idr, "balance_idr": invoice.balance_idr, "paid_idr": invoice.total_idr - invoice.balance_idr,
        "overdue": invoice.due_at < tenant_today(invoice.tenant) and invoice.balance_idr > 0 and invoice.status != "VOIDED",
        "checksum": invoice.checksum, "lines": invoice.snapshot_json["lines"],
        "buyer_name": invoice.snapshot_json["buyer_name"], "dp_policy": invoice.snapshot_json["dp_policy"],
    }


def payment_payload(payment):
    receipt = getattr(payment, "receipt", None)
    return {
        "id": str(payment.pk), "environment": payment.environment, "booking_id": str(payment.booking_id),
        "booking_code": payment.booking.code, "invoice_id": str(payment.invoice_id),
        "invoice_number": payment.invoice.invoice_number, "amount_idr": payment.amount_idr,
        "status": payment.status, "kind": payment.kind, "method": payment.method,
        "received_at": payment.received_at.isoformat(), "reference": payment.reference, "evidence_ref": payment.evidence_ref,
        "simulated": payment.simulated, "reason": payment.reason,
        "verified_at": payment.verified_at.isoformat() if payment.verified_at else None,
        "verified_by_name": (payment.verified_by.full_name or payment.verified_by.email) if payment.verified_by_id else None,
        "receipt": receipt_payload(receipt) if receipt else None,
        "allocations": [{"booking_participant_id": str(a.participant_id), "pilgrim_name": a.participant.pilgrim.name, "amount_idr": a.amount_idr} for a in payment.allocations.select_related("participant__pilgrim")],
        "participants": [{"id": str(p.pk), "status": p.participant_status, "saas_charge_state": p.saas_charge_state, "dp_eligible_at": p.dp_eligible_at.isoformat() if p.dp_eligible_at else None} for p in payment.booking.participants.all()],
    }
