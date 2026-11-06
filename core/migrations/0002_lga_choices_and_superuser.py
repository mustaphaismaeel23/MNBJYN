from django.db import migrations, models


def create_superuser(apps, schema_editor):
    from django.contrib.auth.hashers import make_password
    from core.accounts import DEFAULT_USERNAME
    import os

    password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
    if not password:
        return
    User = apps.get_model("auth", "User")
    username = os.environ.get("DJANGO_SUPERUSER_USERNAME", DEFAULT_USERNAME)
    user, _ = User.objects.get_or_create(username=username)
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.password = make_password(password)
    user.save()


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_superuser, migrations.RunPython.noop),
    ]
