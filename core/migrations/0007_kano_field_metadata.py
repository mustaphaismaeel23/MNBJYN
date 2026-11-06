from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_kano_election"),
    ]

    operations = [
        migrations.AlterField(
            model_name="registration",
            name="lga",
            field=models.CharField(
                choices=[
                    ("ajingi", "Ajingi"),
                    ("albasu", "Albasu"),
                    ("bagwai", "Bagwai"),
                    ("bebeji", "Bebeji"),
                    ("bichi", "Bichi"),
                    ("bunkure", "Bunkure"),
                    ("dala", "Dala"),
                    ("danbata", "Danbata"),
                    ("dawaki_kudu", "Dawaki Kudu"),
                    ("dawaki_tofa", "Dawaki Tofa"),
                    ("doguwa", "Doguwa"),
                    ("fagge", "Fagge"),
                    ("gabasawa", "Gabasawa"),
                    ("garko", "Garko"),
                    ("garun_malam", "Garun Malam"),
                    ("gaya", "Gaya"),
                    ("gezawa", "Gezawa"),
                    ("gwale", "Gwale"),
                    ("gwarzo", "Gwarzo"),
                    ("kabo", "Kabo"),
                    ("kano_municipal", "Kano Municipal"),
                    ("karaye", "Karaye"),
                    ("kibiya", "Kibiya"),
                    ("kiru", "Kiru"),
                    ("kumbotso", "Kumbotso"),
                    ("kunchi", "Kunchi"),
                    ("kura", "Kura"),
                    ("madobi", "Madobi"),
                    ("makoda", "Makoda"),
                    ("minjibir", "Minjibir"),
                    ("nasarawa", "Nasarawa"),
                    ("rano", "Rano"),
                    ("rimin_gado", "Rimin Gado"),
                    ("rogo", "Rogo"),
                    ("shanono", "Shanono"),
                    ("sumaila", "Sumaila"),
                    ("takai", "Takai"),
                    ("tarauni", "Tarauni"),
                    ("tofa", "Tofa"),
                    ("tsanyawa", "Tsanyawa"),
                    ("tudun_wada", "Tudun Wada"),
                    ("ungogo", "Ungogo"),
                    ("warawa", "Warawa"),
                    ("wudil", "Wudil"),
                    ("other", "Other (outside Kano State)"),
                ],
                max_length=20,
                verbose_name="Local Government Area",
            ),
        ),
        migrations.AlterField(
            model_name="sitesettings",
            name="hero_image",
            field=models.ImageField(
                blank=True,
                help_text="Portrait photo of Malam Nasiru Bala Ja'oji shown on the home page. "
                "A tall/portrait image (about 4:5) works best.",
                upload_to="hero/",
                verbose_name="Hero image",
            ),
        ),
        migrations.AlterField(
            model_name="sitesettings",
            name="hero_caption",
            field=models.CharField(
                blank=True,
                default="MNBJYN Kano State",
                help_text="Short caption displayed under the hero image.",
                max_length=120,
            ),
        ),
        migrations.AlterField(
            model_name="candidate",
            name="short_name",
            field=models.CharField(
                help_text="Short label, e.g. APC, PDP, MNBJ.",
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name="pollingunit",
            name="code",
            field=models.CharField(
                help_text="INEC style code, e.g. 20/21/03/007.",
                max_length=20,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="resultagent",
            name="lga_scope",
            field=models.CharField(
                blank=True,
                help_text="Supervisors only: limit them to one LGA (key, e.g. kano_municipal). "
                "Blank = whole state.",
                max_length=20,
                verbose_name="Supervisor LGA",
            ),
        ),
    ]
