"""S01/T05 — model identity: normalisasi email, unik, verifikasi."""
import pytest

from modules.identity.models import User, UserStatus


@pytest.mark.django_db
def test_create_user_normalizes_email(user):
    assert user.email == "owner@example.com"


@pytest.mark.django_db
def test_duplicate_email_rejected(db):
    from django.core.exceptions import ValidationError

    User.objects.create_user(email="dupe@example.com", password="x-pass-123")
    with pytest.raises(ValidationError):
        User.objects.create_user(email="DUPE@example.com", password="y-pass-123")


@pytest.mark.django_db
def test_new_user_is_pending_verification(db):
    user = User.objects.create_user(email="baru@example.com", password="x-pass-123")
    assert user.status == UserStatus.PENDING_VERIFICATION
    assert user.is_email_verified is False


@pytest.mark.django_db
def test_superuser_is_verified_and_staff(db):
    admin = User.objects.create_superuser(email="admin@umrovia.com", password="x-pass-123")
    assert admin.is_staff and admin.is_superuser
    assert admin.is_email_verified is True


@pytest.mark.django_db
def test_password_hashed(db):
    user = User.objects.create_user(email="hash@example.com", password="rahasia-berat-123")
    assert user.check_password("rahasia-berat-123")
    assert not user.password.startswith("rahasia")
