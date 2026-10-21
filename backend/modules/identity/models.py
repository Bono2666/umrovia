"""Model identity global (Spec §5.1 — users).

User adalah akun lintas-tenant: satu user bisa memiliki membership di beberapa travel.
Email = identifier unik (dinormalisasi huruf kecil). PII minimal di sini; data jamaah
berada di modul pilgrims dengan isolasi tenant.
"""
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from common.models import BaseAppModel


class UserStatus(models.TextChoices):
    PENDING_VERIFICATION = "PENDING_VERIFICATION", "Menunggu verifikasi email"
    ACTIVE = "ACTIVE", "Aktif"
    SUSPENDED = "SUSPENDED", "Ditangguhkan"
    DELETED = "DELETED", "Dihapus"


class UserManager(models.Manager):
    def _normalize(self, email: str) -> str:
        return (email or "").strip().lower()

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email wajib diisi")
        extra_fields.setdefault("status", UserStatus.PENDING_VERIFICATION)
        user = self.model(email=self._normalize(email), **extra_fields)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("status", UserStatus.ACTIVE)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("email_verified_at", timezone.now())
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser harus memiliki is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser harus memiliki is_superuser=True")
        return self.create_user(email, password, **extra_fields)


class User(BaseAppModel, AbstractBaseUser, PermissionsMixin):
    """Akun global Umrovia. Bukan superuser atas PII jamaah tenant (Spec §3)."""

    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=150, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    mfa_enabled = models.BooleanField(default=False)
    status = models.CharField(max_length=24, choices=UserStatus.choices, default=UserStatus.PENDING_VERIFICATION)
    is_staff = models.BooleanField(default=False)  # akses Django admin platform (operasional)
    is_active = models.BooleanField(default=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        constraints = [
            # Spec §5.1: UNIQUE lower(email) — email sudah dinormalisasi saat save
            models.UniqueConstraint(fields=["email"], name="uq_identity_user_email"),
        ]

    def __str__(self) -> str:
        return self.email

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None
