# Generated by Django 5.1.4 on 2025-02-25 02:54

import django.db.models.deletion
import sequence_run_manager.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sequence_run_manager", "0004_alter_comment_association_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="sequence",
            name="experiment_name",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.CreateModel(
            name="LibraryAssociation",
            fields=[
                (
                    "orcabus_id",
                    sequence_run_manager.fields.OrcaBusIdField(
                        primary_key=True, serialize=False
                    ),
                ),
                ("library_id", models.CharField(max_length=255)),
                ("association_date", models.DateTimeField()),
                ("status", models.CharField(default="active", max_length=255)),
                (
                    "sequence",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="sequence_run_manager.sequence",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
