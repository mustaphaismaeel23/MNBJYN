from .models import SiteSettings


def site(request):
    from . import content
    from .lga_data import KANO_LGAS, STATE_NAME

    if request.path.startswith("/admin"):
        return {}
    return {
        "site_settings": SiteSettings.load(),
        "ORG_NAME": content.ORG_NAME,
        "ORG_SHORT": content.ORG_SHORT,
        "STATE_NAME": STATE_NAME,
        "LGA_COUNT": len(KANO_LGAS),
    }
