# Generated by Django 4.2.1 on 2023-10-06 11:50

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("registrar", "0034_domain_dnssec_ds_confirmed_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="domain",
            name="dnssec_ds_confirmed",
        ),
        migrations.RemoveField(
            model_name="domain",
            name="dnssec_enabled",
        ),
        migrations.RemoveField(
            model_name="domain",
            name="dnssec_key_confirmed",
        ),
    ]
