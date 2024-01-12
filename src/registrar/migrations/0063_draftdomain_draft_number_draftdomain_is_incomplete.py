# Generated by Django 4.2.7 on 2024-01-12 16:17

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("registrar", "0062_alter_host_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="draftdomain",
            name="draft_number",
            field=models.IntegerField(
                help_text="The draft number in the event a user doesn't save at this stage", null=True
            ),
        ),
        migrations.AddField(
            model_name="draftdomain",
            name="is_incomplete",
            field=models.BooleanField(default=False, help_text="Determines if this Draft is complete or not"),
        ),
    ]