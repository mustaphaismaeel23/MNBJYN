"""Default super-user for the MNBJYN site.

Change the password after first sign-in (Admin > Users) or set the
DJANGO_SUPERUSER_USERNAME / DJANGO_SUPERUSER_PASSWORD environment variables
to override these defaults.
"""
import os

from django.core.exceptions import ImproperlyConfigured

DEFAULT_USERNAME = "Devmusteey"


def ensure_superuser(user_model=None):
    if user_model is None:
        from django.contrib.auth import get_user_model
        user_model = get_user_model()
    username = os.environ.get("DJANGO_SUPERUSER_USERNAME", DEFAULT_USERNAME)
    password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
    if not password:
        raise ImproperlyConfigured(
            "Set DJANGO_SUPERUSER_PASSWORD before creating or updating the super-user."
        )
    user, created = user_model.objects.get_or_create(username=username)
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.set_password(password)
    user.save()
    return user, created
