"""API notifikasi: log pengiriman + kirim ulang + template (staf, UI-14) dan inbox portal (NTF-02)."""
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.notifications import services
from modules.notifications.catalog import TEMPLATES
from modules.notifications.models import Channel, DeliveryStatus, Notification, NotificationTemplate, RecipientType
from modules.portal.services import active_accesses, scoped_access
from modules.portal.views import ActivePortalUser
from modules.tenants.environment import resolve_active_environment
from modules.tenants.rbac import require_permission
from modules.wallet.services import platform_tenant_context

LIST_PARAMS = [
    OpenApiParameter("status", str, enum=[c for c, _ in DeliveryStatus.choices]), OpenApiParameter("channel", str, enum=[c for c, _ in Channel.choices]),
    OpenApiParameter("template", str), OpenApiParameter("q", str), OpenApiParameter("page", int),
]


class TemplateSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=240, allow_blank=True, trim_whitespace=False)
    body = serializers.CharField(max_length=8000, allow_blank=True, trim_whitespace=False)


class NotificationPagination(PageNumberPagination):
    page_size = 50


def mask_email(email):
    if not email:
        return ""
    name, _, domain = email.partition("@")
    return f"{name[:2]}{'•' * max(len(name) - 2, 1)}@{domain}"


def delivery_payload(row, *, detail=False):
    data = {
        "id": str(row.pk), "created_at": row.created_at.isoformat(), "event_type": row.event_type,
        "template_key": row.template_key, "template_label": TEMPLATES[row.template_key].label if row.template_key in TEMPLATES else row.template_key,
        "template_version": row.template_version, "channel": row.channel, "recipient_type": row.recipient_type,
        "recipient_name": row.recipient_name, "recipient_email": mask_email(row.recipient_email), "subject": row.subject,
        "status": row.status, "attempts": row.attempts, "resend_count": row.resend_count, "last_error": row.last_error,
        "next_attempt_at": row.next_attempt_at.isoformat() if row.next_attempt_at else None,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None, "read_at": row.read_at.isoformat() if row.read_at else None,
    }
    if detail:
        data["body"] = row.body
    return data


def template_payload(definition):
    current = services.effective_template(definition.key)
    return {
        "key": definition.key, "label": definition.label, "audience": definition.audience, "editable": definition.editable,
        "subject": current["subject"], "body": current["body"], "version": current["version"], "customized": current["customized"],
        "default_subject": definition.subject, "default_body": definition.body,
        "variables": [{"name": name, "label": label, "required": name in definition.required} for name, label in definition.variables.items()],
    }


def _template(key, *, editable=False):
    definition = TEMPLATES.get(key)
    if definition is None or (editable and not definition.editable):
        raise NotFound("Template tidak ditemukan atau tidak dapat diubah.")
    return definition


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated, require_permission("notifications.read")]

    @extend_schema(parameters=LIST_PARAMS, responses=OpenApiTypes.OBJECT, description="Delivery log (newest first) with per-status counts for the active environment.")
    def get(self, request):
        base = Notification.objects.filter(environment=resolve_active_environment(request.tenant))
        qs = base
        params = request.query_params
        for field, choices, value in [("status", DeliveryStatus, params.get("status")), ("channel", Channel, params.get("channel"))]:
            if value:
                if value not in choices.values:
                    raise ValidationError({field: "Nilai filter tidak dikenal."})
                qs = qs.filter(**{field: value})
        if params.get("template"):
            qs = qs.filter(template_key=params["template"])
        if params.get("q"):
            qs = qs.filter(Q(recipient_name__icontains=params["q"].strip()) | Q(subject__icontains=params["q"].strip()))
        paginator = NotificationPagination()
        rows = paginator.paginate_queryset(qs.order_by("-created_at", "id"), request)
        response = paginator.get_paginated_response([delivery_payload(row) for row in rows])
        counts = dict(base.filter(channel=Channel.EMAIL).order_by().values_list("status").annotate(n=Count("id")))
        response.data["summary"] = {status: counts.get(status, 0) for status in DeliveryStatus.values}
        return response


class NotificationDetailView(APIView):
    permission_classes = [IsAuthenticated, require_permission("notifications.read")]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, notification_id):
        row = Notification.objects.filter(pk=notification_id).first()
        if row is None:
            raise NotFound("Notifikasi tidak ditemukan.")
        return Response(delivery_payload(row, detail=True))


class NotificationResendView(APIView):
    permission_classes = [IsAuthenticated, require_permission("notifications.manage")]

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT, description="Queue the same stored email again (same content, no new message).")
    @transaction.atomic
    def post(self, request, notification_id):
        row = Notification.objects.select_for_update().filter(pk=notification_id).first()
        if row is None:
            raise NotFound("Notifikasi tidak ditemukan.")
        return Response(delivery_payload(services.resend(row, request.user)))


class TemplateListView(APIView):
    permission_classes = [IsAuthenticated, require_permission("notifications.read")]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response({"results": [template_payload(d) for d in TEMPLATES.values()]})


class TemplateDetailView(APIView):
    permission_classes = [IsAuthenticated, require_permission("notifications.manage")]

    @extend_schema(request=TemplateSerializer, responses=OpenApiTypes.OBJECT, description="Save the travel's text; required variables must stay. Version increments.")
    @transaction.atomic
    def put(self, request, key):
        definition = _template(key, editable=True)
        serializer = TemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subject, body = services.validate_template(definition, serializer.validated_data["subject"], serializer.validated_data["body"])
        row, created = NotificationTemplate.objects.select_for_update().get_or_create(tenant=request.tenant, key=key, defaults={"subject": subject, "body": body, "version": 2, "updated_by": request.user})
        if not created:
            if (row.subject, row.body) == (subject, body):
                return Response(template_payload(definition))
            row.subject, row.body, row.version, row.updated_by = subject, body, row.version + 1, request.user
            row.save(update_fields=["subject", "body", "version", "updated_by", "updated_at"])
        log_event(action="notifications.template.updated", request=request, object_type="notification_template", object_id=row.pk, changes={"key": key, "version": row.version})
        return Response(template_payload(definition))

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Return to the default text (as a new version).")
    @transaction.atomic
    def delete(self, request, key):
        definition = _template(key, editable=True)
        row = NotificationTemplate.objects.select_for_update().filter(key=key).first()
        if row and row.subject:
            row.subject, row.body, row.version, row.updated_by = "", "", row.version + 1, request.user
            row.save(update_fields=["subject", "body", "version", "updated_by", "updated_at"])
            log_event(action="notifications.template.reset", request=request, object_type="notification_template", object_id=row.pk, changes={"key": key, "version": row.version})
        return Response(template_payload(definition))


class TemplatePreviewView(APIView):
    permission_classes = [IsAuthenticated, require_permission("notifications.read")]

    @extend_schema(request=TemplateSerializer, responses=OpenApiTypes.OBJECT, description="Render a draft with sample values; validates like save.")
    def post(self, request, key):
        definition = _template(key)
        serializer = TemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subject, body = services.validate_template(definition, serializer.validated_data["subject"], serializer.validated_data["body"])
        environment = resolve_active_environment(request.tenant)
        rendered_subject, rendered_body, _ = services.compose(request.tenant, environment, key, services.sample_values(definition, request.tenant), {"subject": subject, "body": body, "version": 0})
        return Response({"subject": rendered_subject, "body": rendered_body})


# ------------------------------------------------------------------ portal --


def inbox_payload(row, access):
    return {
        "id": str(row.pk), "access_id": str(access.pk), "travel": access.tenant.display_name, "event_type": row.event_type,
        "subject": row.subject, "body": row.body, "created_at": row.created_at.isoformat(),
        "read_at": row.read_at.isoformat() if row.read_at else None,
    }


def _inbox(access):
    return Notification.objects.filter(channel=Channel.IN_APP, recipient_type=RecipientType.PILGRIM, recipient_id=access.pilgrim_id, environment=access.environment)


class PortalInboxView(APIView):
    permission_classes = [ActivePortalUser]

    @extend_schema(responses=OpenApiTypes.OBJECT, description="In-app notifications across the user's active grants, newest first.")
    @transaction.atomic
    def get(self, request):
        results, unread = [], 0
        for access in active_accesses(request.user):
            with platform_tenant_context(access.tenant_id):
                rows = _inbox(access)
                unread += rows.filter(read_at__isnull=True).count()
                results += [inbox_payload(row, access) for row in rows.order_by("-created_at")[:50]]
        results.sort(key=lambda item: item["created_at"], reverse=True)
        return Response({"results": results[:100], "unread": unread})


class PortalInboxReadView(APIView):
    permission_classes = [ActivePortalUser]

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @transaction.atomic
    def post(self, request, access_id, notification_id):
        with scoped_access(request.user, access_id) as (access, _):
            row = _inbox(access).filter(pk=notification_id).first()
            if row is None:
                raise NotFound("Notifikasi tidak ditemukan.")
            if row.read_at is None:
                row.read_at = timezone.now()
                row.save(update_fields=["read_at", "updated_at"])
            return Response(inbox_payload(row, access))


class PortalInboxReadAllView(APIView):
    permission_classes = [ActivePortalUser]

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @transaction.atomic
    def post(self, request):
        updated = 0
        for access in active_accesses(request.user):
            with platform_tenant_context(access.tenant_id):
                updated += _inbox(access).filter(read_at__isnull=True).update(read_at=timezone.now(), updated_at=timezone.now())
        return Response({"updated": updated})
