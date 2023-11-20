# Generated by Django 4.2.7 on 2023-11-09 19:58

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("registrar", "0045_transitiondomain_federal_agency_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="transitiondomain",
            name="email",
            field=models.TextField(blank=True, help_text="Email", null=True),
        ),
        migrations.AddField(
            model_name="transitiondomain",
            name="first_name",
            field=models.TextField(
                blank=True,
                db_index=True,
                help_text="First name",
                null=True,
                verbose_name="first name / given name",
            ),
        ),
        migrations.AddField(
            model_name="transitiondomain",
            name="last_name",
            field=models.TextField(blank=True, help_text="Last name", null=True),
        ),
        migrations.AddField(
            model_name="transitiondomain",
            name="middle_name",
            field=models.TextField(blank=True, help_text="Middle name", null=True),
        ),
        migrations.AddField(
            model_name="transitiondomain",
            name="phone",
            field=models.TextField(blank=True, help_text="Phone", null=True),
        ),
        migrations.AddField(
            model_name="transitiondomain",
            name="title",
            field=models.TextField(blank=True, help_text="Title", null=True),
        ),
    ]
