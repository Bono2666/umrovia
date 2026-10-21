"""Auth API — signup/verify/login/logout/refresh (S02, Spec §8.1)."""
from rest_framework.decorators import api_view
from rest_framework.response import Response

app_name = "identity"

urlpatterns: list = []


@api_view(["GET"])
def me(request):
    """GET /api/v1/me — membership/workspaces milik user (implementasi lengkap di S02)."""
    user = request.user
    return Response(
        {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "email_verified": user.is_email_verified,
            "memberships": [],
        }
    )
