"""Paket — Spec §8.3 (GET/POST /packages, GET/PATCH /packages/{id}; UI-04).

Environment write di-resolve server-side (trial → demo; pasca-konversi →
production; demo READ_ONLY ditolak — §2.2, pola S07). Audit tiap create/
update; `published` = tombol publish/unpublish (guard: hanya dari ACTIVE).
"""
from django.db import IntegrityError, transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.catalog.models import PackageRoomPrice, TravelPackage, generate_package_code
from modules.catalog.serializers import PackageWriteSerializer, package_payload
from modules.tenants.environment import assert_environment_writable, resolve_active_environment
from modules.tenants.rbac import require_permission


def _get_package(package_id) -> TravelPackage:
    try:
        return TravelPackage.objects.get(pk=package_id)
    except (TravelPackage.DoesNotExist, ValueError, ValidationError):
        raise NotFound("Paket tidak ditemukan.") from None


def _set_room_prices(package, prices):
    package.room_prices.all().delete()
    for row in prices:
        PackageRoomPrice.objects.create(tenant=package.tenant, environment=package.environment, package=package, **row)
    if prices:
        package.price_idr = min(row["price_idr"] for row in prices)
        package.save(update_fields=["price_idr", "updated_at"])


class PackageListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), require_permission("packages.write")()]
        return [IsAuthenticated(), require_permission("packages.read")()]

    @extend_schema(operation_id="packages_list", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        qs = TravelPackage.objects.all()
        env = request.query_params.get("environment", "").strip()
        if env:
            from modules.tenants.models import Environment

            if env not in Environment.values:
                raise ValidationError({"environment": "Nilai tidak dikenal (demo/production)."})
            qs = qs.filter(environment=env)
        status_filter = request.query_params.get("status", "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)
        q = request.query_params.get("q", "").strip()
        if q:
            from django.db.models import Q

            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        rows = qs.prefetch_related("room_prices").order_by("name", "code")[:200]
        return Response({"results": [package_payload(p) for p in rows]})

    @extend_schema(request=PackageWriteSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        serializer = PackageWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        room_prices = serializer.validated_data.pop("room_prices", [])
        environment = resolve_active_environment(request.tenant)
        assert_environment_writable(request.tenant, environment)

        pkg = TravelPackage(tenant=request.tenant, environment=environment)
        for _attempt in range(3):
            pkg.code = generate_package_code()
            for field, value in serializer.validated_data.items():
                setattr(pkg, field, value)
            try:
                with transaction.atomic():
                    pkg.save()
            except IntegrityError:
                continue  # tabrakan kode random → coba lagi
            break
        else:
            raise ValidationError({"code": "Gagal membuat kode paket unik, coba lagi."})

        _set_room_prices(pkg, room_prices)
        log_event(
            action="packages.created",
            request=request,
            object_type="package",
            object_id=pkg.pk,
            changes={"code": pkg.code, "name": pkg.name, "price_idr": pkg.price_idr},
        )
        return Response(package_payload(pkg), status=status.HTTP_201_CREATED)


class PackageDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsAuthenticated(), require_permission("packages.write")()]
        return [IsAuthenticated(), require_permission("packages.read")()]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, package_id):
        return Response(package_payload(_get_package(package_id)))

    @extend_schema(request=PackageWriteSerializer, responses=OpenApiTypes.OBJECT)
    def patch(self, request, package_id):
        pkg = TravelPackage.objects.select_for_update().filter(pk=package_id).first()
        if pkg is None:
            raise NotFound("Paket tidak ditemukan.")
        assert_environment_writable(request.tenant, pkg.environment)
        before = {"status": pkg.status, "published": pkg.published}
        serializer = PackageWriteSerializer(pkg, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        room_prices = serializer.validated_data.pop("room_prices", None)
        for field, value in serializer.validated_data.items():
            setattr(pkg, field, value)
        pkg.save()
        if room_prices is not None:
            _set_room_prices(pkg, room_prices)

        changes = {"code": pkg.code, "fields": sorted(set(request.data.keys()))}
        if pkg.status != before["status"]:
            changes["status"] = [before["status"], pkg.status]
        if pkg.published != before["published"]:
            changes["published"] = pkg.published
        log_event(
            action="packages.updated",
            request=request,
            object_type="package",
            object_id=pkg.pk,
            changes=changes,
        )
        return Response(package_payload(pkg))
