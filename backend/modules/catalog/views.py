"""Paket — Spec §8.3 (GET/POST /packages, GET/PATCH /packages/{id}; UI-04).

Environment write di-resolve server-side (trial → demo; pasca-konversi →
production; demo READ_ONLY ditolak — §2.2, pola S07). Audit tiap create/
update; `published` = tombol publish/unpublish (guard: hanya dari ACTIVE).
"""
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.catalog.models import TravelPackage, generate_package_code
from modules.catalog.serializers import PackageWriteSerializer, package_payload
from modules.tenants.environment import assert_environment_writable, resolve_active_environment
from modules.tenants.rbac import require_permission


def _get_package(package_id) -> TravelPackage:
    try:
        return TravelPackage.objects.get(pk=package_id)
    except (TravelPackage.DoesNotExist, ValueError, ValidationError):
        raise NotFound("Paket tidak ditemukan.") from None


class PackageListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), require_permission("packages.write")()]
        return [IsAuthenticated(), require_permission("packages.read")()]

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
        rows = qs.order_by("name", "code")[:200]
        return Response({"results": [package_payload(p) for p in rows]})

    def post(self, request):
        serializer = PackageWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
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

    def get(self, request, package_id):
        return Response(package_payload(_get_package(package_id)))

    def patch(self, request, package_id):
        pkg = _get_package(package_id)
        assert_environment_writable(request.tenant, pkg.environment)
        before = {"status": pkg.status, "published": pkg.published}
        serializer = PackageWriteSerializer(pkg, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(pkg, field, value)
        pkg.save()

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
