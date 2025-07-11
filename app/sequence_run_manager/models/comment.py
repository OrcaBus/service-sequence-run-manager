from django.db import models

from sequence_run_manager.models.base import OrcaBusBaseModel, OrcaBusBaseManager
from sequence_run_manager.fields import OrcaBusIdField


class TargetType(models.TextChoices):
    SEQUENCE = "sequence"
    SAMPLE_SHEET = "sample_sheet"

class CommentManager(OrcaBusBaseManager):
    pass


class Comment(OrcaBusBaseModel):
    orcabus_id = OrcaBusIdField(primary_key=True, prefix='cmt')
    comment = models.TextField(null=False, blank=False)
    target_id = OrcaBusIdField(prefix='')  # comment association object id
    target_type = models.CharField(max_length=255, null=False, blank=False, choices=TargetType.choices, default=TargetType.SEQUENCE)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=255, null=False, blank=False)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    objects = CommentManager()

    def __str__(self):
        return f"ID: {self.orcabus_id}, comment: {self.comment}, from {self.created_by}, for {self.target_id}"
