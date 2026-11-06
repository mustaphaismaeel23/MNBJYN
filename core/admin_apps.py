from django.contrib.admin.apps import AdminConfig


class SSBYNAdminConfig(AdminConfig):
    """Swap in our branded admin site (with a dashboard) for the default one."""

    default_site = "core.admin_site.SSBYNAdminSite"
