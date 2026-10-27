"""S18: grup peran platform (Spec §3). Izin dibuat eksplisit karena post_migrate belum berjalan."""
from django.contrib.auth.management import create_permissions
from django.db import migrations

ROLES = {
    "Platform Super Admin": ["platform.console_view", "platform.tenant_manage", "platform.pricing_manage", "platform.audit_view", "platform.support_manage"],
    "Platform Billing": ["platform.console_view", "wallet.settle_topup", "billing.approve_adjustment"],
    "Platform Support": ["platform.console_view", "platform.support_manage"],
}


def create_roles(apps, schema_editor):
    for label in ("platform", "wallet", "billing"):
        config = apps.get_app_config(label)
        config.models_module = True
        create_permissions(config, apps=apps, verbosity=0)
        config.models_module = None
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for name, perms in ROLES.items():
        group, _ = Group.objects.get_or_create(name=name)
        for perm in perms:
            app_label, codename = perm.split(".")
            group.permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))


class Migration(migrations.Migration):
    dependencies = [
        ("platform", "0002_control_plane"),
        ("wallet", "0001_initial"),
        ("billing", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]
    operations = [migrations.RunPython(create_roles, migrations.RunPython.noop)]
