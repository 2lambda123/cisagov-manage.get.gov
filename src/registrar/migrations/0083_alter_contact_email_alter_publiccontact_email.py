# Generated by Django 4.2.10 on 2024-04-09 16:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0082_domaininformation_organization_type_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contact",
            name="email",
            field=models.EmailField(blank=True, db_index=True, max_length=320, null=True),
        ),
        migrations.AlterField(
            model_name="publiccontact",
            name="email",
            field=models.EmailField(help_text="Contact's email address", max_length=320),
        ),
    ]
