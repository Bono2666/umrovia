from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Payload harus berupa objek.")
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: "Field tidak dikenal." for key in unknown})
        return super().to_internal_value(data)


class TopupCreateSerializer(StrictSerializer):
    amount_idr = serializers.IntegerField(min_value=1, max_value=10_000_000_000)

    def validate_amount_idr(self, value):
        if type(self.initial_data["amount_idr"]) is not int:
            raise serializers.ValidationError("Nominal harus integer rupiah.")
        return value


class TopupSubmitSerializer(StrictSerializer):
    payment_reference = serializers.CharField(max_length=120)
    evidence_ref = serializers.CharField(max_length=512)


class TopupSettleSerializer(TopupCreateSerializer):
    provider_txn_id = serializers.CharField(max_length=160)
    decision = serializers.ChoiceField(choices=["PAID", "REJECTED"], default="PAID")
    reason = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


def topup_payload(topup):
    return {
        "id": str(topup.pk), "number": f"TOP-{topup.pk}", "provider": topup.provider,
        "amount_idr": topup.amount_idr, "status": topup.status,
        "instructions": topup.instructions_json, "payment_reference": topup.payment_reference,
        "evidence_ref": topup.evidence_ref, "provider_txn_id": topup.provider_txn_id,
        "expires_at": topup.expires_at.isoformat(), "created_at": topup.created_at.isoformat(),
        "paid_at": topup.paid_at.isoformat() if topup.paid_at else None,
        "ledger_entry_id": str(topup.ledger_entry_id) if topup.ledger_entry_id else None,
        "reason": topup.reason,
    }


def ledger_payload(row):
    return {
        "id": str(row.pk), "sequence": row.sequence, "kind": row.kind,
        "signed_amount_idr": row.signed_amount_idr, "balance_after_idr": row.balance_after_idr,
        "reference_type": row.reference_type, "reference_id": str(row.reference_id),
        "description": row.description, "created_at": row.created_at.isoformat(),
    }
