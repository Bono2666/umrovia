"""Auth API — signup/verify/login/logout/reset (S02, Spec §8.1)."""
from django.urls import path

from modules.identity import views

app_name = "identity"

urlpatterns = [
    path("auth/register", views.RegisterView.as_view(), name="register"),
    path("auth/verify-email", views.VerifyEmailView.as_view(), name="verify-email"),
    path("auth/resend-verification", views.ResendVerificationView.as_view(), name="resend-verification"),
    path("auth/login", views.LoginView.as_view(), name="login"),
    path("auth/logout", views.LogoutView.as_view(), name="logout"),
    path("auth/csrf", views.csrf_view, name="csrf"),
    path("auth/password/forgot", views.ForgotPasswordView.as_view(), name="password-forgot"),
    path("auth/password/reset", views.ResetPasswordView.as_view(), name="password-reset"),
    path("me", views.MeView.as_view(), name="me"),
]
