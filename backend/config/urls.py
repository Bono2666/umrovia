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
    path("api/v1/", include("modules.travel_finance.urls", namespace="travel_finance")),
    path("api/v1/", include("modules.pilgrims.urls", namespace="pilgrims")),
    path("api/v1/", include("modules.catalog.urls", namespace="catalog")),
    path("api/v1/", include("modules.departures.urls", namespace="departures")),
    path("api/v1/", include("modules.booking.urls", namespace="booking")),
    path("api/v1/", include("modules.manifest.urls", namespace="manifest")),
    path("api/v1/", include("modules.payments.urls", namespace="payments")),
    path("api/v1/", include("modules.wallet.urls", namespace="wallet")),
    path("api/v1/", include("modules.billing.urls", namespace="billing")),
    path("api/v1/", include("modules.trial.urls", namespace="trial")),
]
