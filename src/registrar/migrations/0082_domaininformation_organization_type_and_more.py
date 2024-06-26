# Generated by Django 4.2.10 on 2024-04-01 15:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0081_create_groups_v10"),
    ]

    operations = [
        migrations.AddField(
            model_name="domaininformation",
            name="organization_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("federal", "Federal"),
                    ("interstate", "Interstate"),
                    ("state_or_territory", "State or territory"),
                    ("tribal", "Tribal"),
                    ("county", "County"),
                    ("city", "City"),
                    ("special_district", "Special district"),
                    ("school_district", "School district"),
                    ("state_or_territory_election", "State or territory - Election"),
                    ("tribal_election", "Tribal - Election"),
                    ("county_election", "County - Election"),
                    ("city_election", "City - Election"),
                    ("special_district_election", "Special district - Election"),
                ],
                help_text="Type of organization - Election office",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="domainrequest",
            name="organization_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("federal", "Federal"),
                    ("interstate", "Interstate"),
                    ("state_or_territory", "State or territory"),
                    ("tribal", "Tribal"),
                    ("county", "County"),
                    ("city", "City"),
                    ("special_district", "Special district"),
                    ("school_district", "School district"),
                    ("state_or_territory_election", "State or territory - Election"),
                    ("tribal_election", "Tribal - Election"),
                    ("county_election", "County - Election"),
                    ("city_election", "City - Election"),
                    ("special_district_election", "Special district - Election"),
                ],
                help_text="Type of organization - Election office",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="domaininformation",
            name="generic_org_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("federal", "Federal"),
                    ("interstate", "Interstate"),
                    ("state_or_territory", "State or territory"),
                    ("tribal", "Tribal"),
                    ("county", "County"),
                    ("city", "City"),
                    ("special_district", "Special district"),
                    ("school_district", "School district"),
                ],
                help_text="Type of organization",
                max_length=255,
                null=True,
            ),
        ),
    ]
