from django.db import migrations


def create_kano_election(apps, schema_editor):
    Election = apps.get_model("core", "Election")
    Candidate = apps.get_model("core", "Candidate")
    SiteSettings = apps.get_model("core", "SiteSettings")
    GalleryImage = apps.get_model("core", "GalleryImage")
    PollingUnit = apps.get_model("core", "PollingUnit")

    Election.objects.filter(is_current=True).update(is_current=False)
    election, _ = Election.objects.get_or_create(
        slug="kano-gov-2027",
        defaults={"name": "2027 Governorship – Kano State", "is_current": True},
    )
    if not election.is_current:
        election.is_current = True
        election.save(update_fields=["is_current"])

    for order, (name, short, color) in enumerate([
        ("Malam Nasiru Bala Ja'oji", "MNBJ", "#14B8A6"),
        ("Candidate B", "B", "#FFFFFF"),
        ("Candidate C", "C", "#99F6E4"),
        ("Others", "OTH", "#6F86A6"),
    ]):
        Candidate.objects.get_or_create(
            election=election,
            short_name=short,
            defaults={"name": name, "color": color, "order": order},
        )

    # Do not keep displaying the previous campaign's portrait for the new candidate.
    SiteSettings.objects.filter(pk=1).update(hero_image="", hero_caption="")
    GalleryImage.objects.filter(is_published=True).update(is_published=False)
    PollingUnit.objects.exclude(lga__in=[
        "ajingi", "albasu", "bagwai", "bebeji", "bichi", "bunkure", "dala",
        "danbata", "dawaki_kudu", "dawaki_tofa", "doguwa", "fagge", "gabasawa",
        "garko", "garun_malam", "gaya", "gezawa", "gwale", "gwarzo", "kabo",
        "kano_municipal", "karaye", "kibiya", "kiru", "kumbotso", "kunchi",
        "kura", "madobi", "makoda", "minjibir", "nasarawa", "rano", "rimin_gado",
        "rogo", "shanono", "sumaila", "takai", "tarauni", "tofa", "tsanyawa",
        "tudun_wada", "ungogo", "warawa", "wudil",
    ]).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_election_results"),
    ]

    operations = [
        migrations.RunPython(create_kano_election, migrations.RunPython.noop),
    ]
