"""URL configuration — semua endpoint di bawah /api/v1 (Spec §8)."""
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("api/v1/", include("modules.platform.urls", namespace="platform")),
    # OpenAPI: schema + UI stub (diperkaya per modul saat endpoint ditambahkan)
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/v1/", include("modules.identity.urls", namespace="identity")),
    path("api/v1/", include("modules.tenants.urls", namespace="tenants")),
]
