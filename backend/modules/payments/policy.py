"""Keputusan pengguna: DP verified > Rp0 eligible; minimum hanya target opsional."""
from rest_framework.exceptions import ValidationError

from modules.tenants.models import TenantSettings


def payment_rules(tenant):
    settings = TenantSettings.objects.filter(tenant=tenant).first()
    raw = (settings.rules_json if settings else {}).get("payments") or {}
    if not isinstance(raw, dict):
        raise ValidationError({"payments": "Aturan pembayaran harus berupa objek."})
    return dict(raw)


def validate_payment_rules(value):
    if not isinstance(value, dict):
        raise ValidationError({"payments": "Aturan pembayaran harus berupa objek."})
    if set(value) - {"dp_policy", "dp_minimum_idr", "maker_checker"}:
        raise ValidationError({"payments": "Field aturan pembayaran tidak dikenal."})
    mode = value.get("dp_policy")
    if mode not in (None, "any_positive"):
        raise ValidationError({"dp_policy": "Setiap alokasi terverifikasi di atas Rp0 memenuhi syarat DP."})
    minimum = value.get("dp_minimum_idr")
    if minimum not in (None, "") and (type(minimum) is not int or not 0 <= minimum <= 10_000_000_000):
        raise ValidationError({"dp_minimum_idr": "Target DP opsional harus Rp0–Rp10 miliar."})
    if "maker_checker" in value and type(value["maker_checker"]) is not bool:
        raise ValidationError({"maker_checker": "Harus boolean."})
    return value


def eligibility_policy(tenant):
    rules = validate_payment_rules(payment_rules(tenant))
    return {"dp_policy": "any_positive", "dp_minimum_idr": rules.get("dp_minimum_idr") or 0}


def required_dp(policy):
    return 1
