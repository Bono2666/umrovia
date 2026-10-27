"""API laporan siap pakai: GET /reports/{operational|finance|saas} (+ `?file=pdf|xlsx|csv`)."""
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.catalog.models import TravelPackage
from modules.departures.models import Departure, DepartureStatus
from modules.manifest.printing import print_meta
from modules.reports import export, services
from modules.tenants.branches import branch_scope, require_full_scope
from modules.tenants.environment import resolve_active_environment
from modules.tenants.rbac import has_permission, permission_list

FORMATS = {
    "pdf": (export.to_pdf, "application/pdf"),
    "xlsx": (export.to_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "csv": (export.to_csv, "text/csv; charset=utf-8"),
}
PARAMS = [
    OpenApiParameter("from", OpenApiTypes.DATE), OpenApiParameter("to", OpenApiTypes.DATE), OpenApiParameter("package", OpenApiTypes.UUID),
    OpenApiParameter("departure", OpenApiTypes.UUID), OpenApiParameter("status", str), OpenApiParameter("agent", OpenApiTypes.UUID), OpenApiParameter("branch", OpenApiTypes.UUID),
    OpenApiParameter("account", str, description="UUID rekening atau CASH"), OpenApiParameter("file", str, enum=list(FORMATS)),
]


def filter_labels(f, environment):
    package = TravelPackage.objects.filter(pk=f["package"], environment=environment).first() if f["package"] else None
    departure = Departure.objects.filter(pk=f["departure"], environment=environment).first() if f["departure"] else None
    if f["package"] and package is None:
        raise ValidationError({"package": "Paket tidak ditemukan."})
    if f["departure"] and departure is None:
        raise ValidationError({"departure": "Keberangkatan tidak ditemukan."})
    from modules.agents.models import Agent
    from modules.travel_finance.models import TravelBankAccount

    agent = Agent.objects.filter(pk=f["agent"], environment=environment).first() if f.get("agent") else None
    if f.get("agent") and agent is None:
        raise ValidationError({"agent": "Agen tidak ditemukan."})
    account = ""
    if f.get("account") == "CASH":
        account = "Tunai"
    elif f.get("account"):
        row = TravelBankAccount.objects.filter(pk=f["account"]).first()
        if row is None:
            raise ValidationError({"account": "Rekening tidak ditemukan."})
        account = f"{row.bank_name} {row.account_masked}"
    from modules.tenants.models import Branch

    branch = Branch.objects.filter(pk=f["branch"]).first() if f.get("branch") else None
    if f.get("branch") and branch is None:
        raise ValidationError({"branch": "Cabang tidak ditemukan."})
    f["branch_obj"] = branch
    return {"package": package.name if package else "", "departure": departure.code if departure else "", "status": dict(DepartureStatus.choices).get(f["status"], ""),
            "agent": agent.name if agent else "", "account": account, "branch": f"{branch.code} · {branch.name}" if branch else ""}


class ReportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=PARAMS, responses=OpenApiTypes.OBJECT, description="Ready-made report computed from source records at request time (`as_of`), with reconciliation checks. `?file=` downloads PDF/XLSX/CSV (audited).")
    def get(self, request, kind):
        if kind not in services.BUILDERS:
            raise NotFound("Laporan tidak dikenal.")
        membership = getattr(request, "membership", None)
        if membership is None or not has_permission(permission_list(membership.role), services.PERMISSIONS[kind]):
            raise PermissionDenied(f"Permission '{services.PERMISSIONS[kind]}' tidak dimiliki role Anda.")
        environment = resolve_active_environment(request.tenant)
        f = services.parse_filters(request.query_params, request.tenant)
        labels = filter_labels(f, environment)
        # TBD-08 opsi C: staf bercakupan cabang hanya melihat cabangnya (+ data tanpa cabang).
        scope = branch_scope(request)
        if scope is not None:
            if kind in {"finance", "saas"}:
                require_full_scope(request, "Laporan ini")
            if f.get("branch") and f["branch"] not in scope:
                raise PermissionDenied("Cabang ini di luar cakupan akses Anda.")
            f["branch_scope"] = scope
        report = services.BUILDERS[kind](request.tenant, environment, f)
        report["filter_labels"] = labels
        file = request.query_params.get("file")
        if not file:
            return Response(report)
        if file not in FORMATS:
            raise ValidationError({"file": "Format ekspor: pdf, xlsx atau csv."})
        render, content_type = FORMATS[file]
        meta = print_meta(title=report["title"], travel=request.tenant.display_name, environment=environment, actor=request.user, zone=report["timezone"])
        data = render(report, meta, labels)
        log_event(action="reports.exported", request=request, object_type="report", object_id=kind, changes={"format": file, "period": report["period"], "filters": report["filters"]})
        response = HttpResponse(data, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{export.filename(report, file)}"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT, description="KPI Ringkasan (MOD-02): blok sesuai izin role, pengingat dan grafik 12 bulan.")
    def get(self, request):
        from modules.reports.dashboard import summary

        if getattr(request, "membership", None) is None:
            raise PermissionDenied("Workspace belum dipilih.")
        return Response(summary(request))
