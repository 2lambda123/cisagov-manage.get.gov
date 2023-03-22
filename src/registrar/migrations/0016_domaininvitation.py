# Generated by Django 4.1.6 on 2023-03-22 19:55

from django.db import migrations, models
import django.db.models.deletion
import django_fsm


class Migration(migrations.Migration):
    dependencies = [
        ("registrar", "0015_remove_domain_owners_userdomainrole_user_domains_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="DomainInvitation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("email", models.EmailField(max_length=254)),
                (
                    "status",
                    django_fsm.FSMField(
                        choices=[("sent", "sent"), ("retrieved", "retrieved")],
                        default="sent",
                        max_length=50,
                        protected=True,
                    ),
                ),
                (
                    "domain",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="registrar.domain",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
