"""Auth API — Spec §8.1: register, verify-email, login, logout, me, password reset.

Keputusan: sesi berbasis cookie (bukan JWT) — lihat docs/adr/0002-auth-session.md.
Rate limit memakai DRF scoped throttle + cache (Redis di compose, locmem lokal).
"""
import logging

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.identity import services
from modules.identity.models import AuthTokenKind, User, UserStatus
from modules.identity.serializers import (
    ForgotPasswordSerializer,
    LoginSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    ResetPasswordSerializer,
    VerifyEmailSerializer,
)
from modules.tenants.models import Tenant, TenantState
from modules.tenants.services import ProvisioningError, provision_workspace

logger = logging.getLogger(__name__)

# Status generik anti-enumeration: response register/resend selalu sama
GENERIC_VERIFICATION_STATUS = {
    "status": "verification_sent",
    "message": "Jika email terdaftar, link verifikasi sudah dikirim. Periksa kotak masuk Anda.",
}


def _client_ip(request) -> str | None:
    addr = request.META.get("REMOTE_ADDR")
    return addr if addr else None


class RegisterView(APIView):
    """POST /auth/register — signup travel (§7.1 langkah 1–2). Rate limited."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth-register"

    def post(self, request):
        # Anti-enumeration: cek email dulu — form ulang (email+sama) selalu
        # mendapat respons generik, bahkan bila field lain tidak valid.
        email = str(request.data.get("email", "")).strip().lower()
        if email and User.objects.filter(email=email).exists():
            return Response(GENERIC_VERIFICATION_STATUS, status=status.HTTP_200_OK)

        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        now = timezone.now()
        with transaction.atomic():
            user = User.objects.create_user(
                email=data["email"],
                password=data["password"],
                terms_accepted_at=now,
            )
            Tenant.objects.create(
                slug=data["slug"],
                legal_name=data["travel_name"],
                display_name=data["travel_name"],
                state=TenantState.PENDING_EMAIL,
                created_by=user,
            )
        raw = services.issue_token(user, AuthTokenKind.EMAIL_VERIFY, services.EMAIL_VERIFY_TTL, ip=_client_ip(request))
        url = services.send_verification_email(user, raw)

        payload = dict(GENERIC_VERIFICATION_STATUS)
        if settings.DEBUG:  # bantuan dev lokal: console backend, tampilkan link langsung
            payload["dev_verification_url"] = url
        logger.info("register: user dibuat (menunggu verifikasi)", extra={"user_id": str(user.id)})
        return Response(payload, status=status.HTTP_201_CREATED)


class VerifyEmailView(APIView):
    """POST /auth/verify-email — aktifkan identitas lalu provision workspace (§7.1 langkah 3)."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth-verify"

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = services.consume_token(serializer.validated_data["token"], AuthTokenKind.EMAIL_VERIFY)
        except services.AuthTokenError as exc:
            return Response(
                {"code": exc.code, "detail": exc.detail, "request_id": getattr(request, "request_id", None)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = services.mark_verified(user)
        tenant = Tenant.objects.filter(created_by=user, state="PENDING_EMAIL").first()
        if tenant is not None:
            try:
                tenant = provision_workspace(user, tenant.slug)
            except ProvisioningError:
                logger.exception("verify-email: provisioning gagal", extra={"user_id": str(user.id)})
                return Response(
                    {"code": "provisioning_failed",
                     "detail": "Email terverifikasi, tetapi pembuatan workspace gagal. Hubungi support."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            tenant.state = TenantState.PROVISIONING  # → TRIAL pada S04 ketika trial record dibuat
            tenant.save(update_fields=["state", "updated_at"])
        logger.info("verify-email: sukses", extra={"user_id": str(user.id)})
        return Response(
            {"status": "verified", "email": user.email, "workspace": services.user_payload(user)["memberships"]},
            status=status.HTTP_200_OK,
        )


class ResendVerificationView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth-resend"

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(
            email=serializer.validated_data["email"], status=UserStatus.PENDING_VERIFICATION
        ).first()
        if user is not None:
            raw = services.issue_token(
                user, AuthTokenKind.EMAIL_VERIFY, services.EMAIL_VERIFY_TTL, ip=_client_ip(request)
            )
            services.send_verification_email(user, raw)
        return Response(GENERIC_VERIFICATION_STATUS, status=status.HTTP_200_OK)


class LoginView(APIView):
    """POST /auth/login — mulai sesi cookie (rate limited)."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth-login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = authenticate(request, username=email, password=serializer.validated_data["password"])
        if user is None:
            return Response(
                {"code": "invalid_credentials", "detail": "Email atau password salah."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if user.status == UserStatus.PENDING_VERIFICATION:
            return Response(
                {"code": "email_not_verified", "detail": "Email belum diverifikasi. Cek kotak masuk Anda."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if user.status != UserStatus.ACTIVE:
            return Response(
                {"code": "account_suspended", "detail": "Akun ditangguhkan. Hubungi support."},
                status=status.HTTP_403_FORBIDDEN,
            )
        auth_login(request, user)
        logger.info("login: sukses", extra={"user_id": str(user.id)})
        return Response(services.user_payload(user), status=status.HTTP_200_OK)


class LogoutView(APIView):
    """POST /auth/logout — akhiri sesi (CSRF via SessionAuthentication)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        auth_logout(request)
        return Response({"status": "logged_out"}, status=status.HTTP_200_OK)


class MeView(APIView):
    """GET /me — identitas + membership/workspaces (Spec §8.1)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(services.user_payload(request.user), status=status.HTTP_200_OK)


class ForgotPasswordView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth-forgot"

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(
            email=serializer.validated_data["email"],
            status__in=[UserStatus.ACTIVE, UserStatus.PENDING_VERIFICATION],
        ).first()
        if user is not None:
            raw = services.issue_token(
                user, AuthTokenKind.PASSWORD_RESET, services.PASSWORD_RESET_TTL, ip=_client_ip(request)
            )
            url = services.send_password_reset_email(user, raw)
            payload = {"status": "if_registered"}
            if settings.DEBUG:
                payload["dev_reset_url"] = url
            return Response(payload, status=status.HTTP_200_OK)
        return Response({"status": "if_registered"}, status=status.HTTP_200_OK)


class ResetPasswordView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth-forgot"

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = services.consume_token(serializer.validated_data["token"], AuthTokenKind.PASSWORD_RESET)
        except services.AuthTokenError as exc:
            return Response(
                {"code": exc.code, "detail": exc.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["password", "updated_at"])
        logger.info("reset-password: sukses", extra={"user_id": str(user.id)})
        return Response({"status": "password_updated"}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf_view(request):
    """GET /auth/csrf — ambil cookie CSRF untuk POST terautentikasi (logout, dsb.)."""
    return Response({"csrfToken": get_token(request)})
