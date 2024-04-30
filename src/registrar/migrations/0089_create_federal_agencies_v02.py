# Generated by Django 4.2.10 on 2024-03-22 22:18
# Removes U.S. China Economic and Security Review Commission from Federal Agency options

from django.db import migrations, models
from registrar.models import FederalAgency
from typing import Any


# For linting: RunPython expects a function reference.
def create_federal_agencies(apps, schema_editor) -> Any:
    FederalAgency.create_federal_agencies(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0088_domaininformation_cisa_representative_email_and_more"),
    ]

    operations = [
        migrations.RunPython(
            create_federal_agencies,
            reverse_code=migrations.RunPython.noop,
            atomic=True,
        ),
    ]