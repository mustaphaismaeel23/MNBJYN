import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()

# Vercel looks for a variable named `app`.
app = application

# On Vercel there is no separate release step, so apply migrations on cold
# start (a quick no-op when the database is already up to date). Set
# AUTO_MIGRATE=0 to disable.
if os.environ.get("VERCEL") and os.environ.get("AUTO_MIGRATE", "1") == "1":
    try:
        from django.core.management import call_command

        call_command("migrate", interactive=False, verbosity=0)
    except Exception as exc:  # never stop the site from booting
        print(f"[ssbyn] auto-migrate failed: {exc}")
