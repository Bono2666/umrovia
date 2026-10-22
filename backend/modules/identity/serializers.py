"""Serializer auth (Spec §8.1). Validasi register mengikuti §7.1: email, password,
nama travel, slug, persetujuan T&C."""
import re

from rest_framework import serializers

from modules.identity.models import User, UserStatus
from modules.tenants.constants import RESERVED_SLUGS
from modules.tenants.models import Tenant

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8, max_length=128)
    travel_name = serializers.CharField(max_length=160)
    slug = serializers.CharField(max_length=63)
    agree_terms = serializers.BooleanField()

    def validate_email(self, value: str) -> str:
        return value.strip().lower()

    def validate_slug(self, value: str) -> str:
        value = value.strip().lower()
        if not SLUG_RE.match(value):
            raise serializers.ValidationError(
                "Slug hanya boleh huruf kecil, angka, dan tanda minus."
            )
        if value in RESERVED_SLUGS:
            raise serializers.ValidationError(f"Slug '{value}' terreserve.")
        if Tenant.objects.filter(slug=value).exists():
            raise serializers.ValidationError("Slug sudah dipakai travel lain.")
        return value

    def validate_agree_terms(self, value: bool) -> bool:
        if not value:
            raise serializers.ValidationError("Persetujuan Syarat Layanan & Privasi wajib.")
        return value


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class VerifyEmailSerializer(serializers.Serializer):
    token = serializers.CharField()


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8, max_length=128)


def ensure_not_deleted(user: User) -> None:
    if user.status == UserStatus.DELETED:
        raise serializers.ValidationError({"email": ["Akun tidak ditemukan."]})
