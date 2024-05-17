# Generated by Django 4.2.10 on 2024-05-16 23:08

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0094_create_groups_v12"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="domaininformation",
            name="cisa_representative_email",
        ),
        migrations.RemoveField(
            model_name="domainrequest",
            name="cisa_representative_email",
        ),
        migrations.AddField(
            model_name="domaininformation",
            name="cisa_representative",
            field=models.ForeignKey(
                blank=True,
                help_text='Cisa Representative listed under "additional information" in the request form',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cisa_representative_domain_requests_information",
                to="registrar.contact",
            ),
        ),
        migrations.AddField(
            model_name="domainrequest",
            name="cisa_representative",
            field=models.ForeignKey(
                blank=True,
                help_text='Cisa Representative listed under "additional information" in the request form',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cisa_representative_domain_requests",
                to="registrar.contact",
            ),
        ),
    ]
