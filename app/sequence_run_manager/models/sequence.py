import logging

from django.db import models
from django.db.models import QuerySet

from sequence_run_manager.models.base import OrcaBusBaseModel, OrcaBusBaseManager
from sequence_run_manager.fields import OrcaBusIdField

logger = logging.getLogger(__name__)


class SequenceStatus(models.TextChoices):
    # Convention: status values are to be stored as upper cases
    STARTED = "STARTED"
    FAILED = "FAILED"
    SUCCEEDED = "SUCCEEDED"
    ABORTED = "ABORTED"

    # custom status,  resolve issue: https://github.com/umccr/orcabus/issues/879
    RESOLVED = "RESOLVED"

    @classmethod
    def from_value(cls, value):
        if value == cls.STARTED.value:
            return cls.STARTED
        elif value == cls.SUCCEEDED.value:
            return cls.SUCCEEDED
        elif value == cls.FAILED.value:
            return cls.FAILED
        elif value == cls.RESOLVED.value:
            return cls.RESOLVED
        else:
            raise ValueError(f"No matching SequenceStatus found for value: {value}")

    @classmethod
    def from_seq_run_status(cls, value):
        """
        See Run Status
        https://help.basespace.illumina.com/automate/statuses
        https://support.illumina.com/help/BaseSpace_Sequence_Hub/Source/Informatics/BS/Statuses_swBS.htm (deprecated)

        Note that we don't necessary support all these statuses. In the following check, those values come
        from observed values from our BSSH run events.

        See https://github.com/umccr-illumina/stratus/issues/95

        :param value:
        :return:
        """
        value = str(value).lower()
        if value in ["uploading", "running", "new"]:
            return cls.STARTED
        elif value in ["complete", "analyzing", "pendinganalysis"]:
            return cls.SUCCEEDED
        elif value in ["failed", "needsattention", "timedout", "failedupload"]:
            return cls.FAILED
        elif value in ["stopped"]:
            return cls.ABORTED
        else:
            raise ValueError(f"No matching SequenceStatus found for value: {value}")

    @classmethod
    def is_terminal(cls, value):
        """
        Check if the status is terminal (i.e. SUCCEEDED, FAILED, ABORTED)
        """
        return value in [cls.SUCCEEDED.value, cls.FAILED.value, cls.ABORTED.value]


class SequenceManager(OrcaBusBaseManager):
    def get_by_keyword(self, **kwargs) -> QuerySet:
        qs: QuerySet = super().get_queryset()
        return self.get_model_fields_query(qs, **kwargs)


class Sequence(OrcaBusBaseModel):
    # must have (run_folder_path) or (v1pre3_id and ica_project_id and api_url)
    # NOTE: we use this to retrieve further details for icav2 bssh event
    # for reference: https://github.com/umccr/orcabus/pull/748#issuecomment-2516246960
    class Meta:

        # remove this constraint as we don't have run_folder_path for fake sequence runs
        # constraints = [
        #     models.CheckConstraint(check=models.Q(run_folder_path__isnull=False) | models.Q(v1pre3_id__isnull=False,
        #                                                                                     ica_project_id__isnull=False,
        #                                                                                     api_url__isnull=False),
        #                            name='check_run_folder_path_or_bssh_keys_not_null')
        # ]
        pass

    orcabus_id = OrcaBusIdField(primary_key=True, prefix='seq')

    # mandatory non-nullable base fields
    sequence_run_id = models.CharField(max_length=255, null=False, blank=False)  # unique key, legacy `run_id`
    sample_sheet_name = models.CharField(max_length=255, null=False, blank=False)

    # nullable base fields only for fake sequence runs (refer: https://github.com/umccr/orcabus/issues/947)
    status = models.CharField(choices=SequenceStatus.choices, max_length=255, null=True, blank=True)
    start_time = models.DateTimeField(null=True, blank=True)

    # nullable base fields for sequence runs info from bssh events
    v1pre3_id = models.CharField(max_length=255, null=True, blank=True)
    ica_project_id = models.CharField(max_length=255, null=True, blank=True)
    api_url = models.TextField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    run_volume_name = models.TextField(null=True, blank=True)  # legacy `gds_volume_name`
    run_folder_path = models.TextField(null=True, blank=True)  # legacy `gds_folder_path`, nullable as ICAv2 event upgrade
    run_data_uri = models.TextField(null=True, blank=True)  # must be absolute path, including URI scheme/protocol

    # optional fields -- business look up keys
    instrument_run_id = models.CharField(max_length=255, null=True, blank=True)
    reagent_barcode = models.CharField(max_length=255, null=True, blank=True)
    flowcell_barcode = models.CharField(max_length=255, null=True, blank=True)
    sequence_run_name = models.CharField(max_length=255, null=True, blank=True)  # legacy `name`
    experiment_name = models.CharField(max_length=255, null=True, blank=True)

    # run_config = models.JSONField(null=True, blank=True)  # TODO could be it's own model
    # sample_sheet_config = models.JSONField(null=True, blank=True)  # TODO could be it's own model

    objects = SequenceManager()

    def __str__(self):
        return (
            f"ID '{self.orcabus_id}', "
            f"Sequence Run ID '{self.sequence_run_id}', "
            f"Sequence Run Name '{self.sequence_run_name}', "
            f"Run Data URI '{self.run_data_uri}', "
            f"Status '{self.status}'"
        )

    def libraries(self) -> list[str]:
        """
        Get all libraries associated with the sequence
        """
        return list(LibraryAssociation.objects.filter(sequence=self).values_list('library_id', flat=True))

    def get_latest_state(self):
        """
        Get the latest state for the sequence
        """
        return self.states.order_by('-timestamp').first()


class LibraryAssociationManager(OrcaBusBaseManager):
    pass


class LibraryAssociation(OrcaBusBaseModel):
    orcabus_id = OrcaBusIdField(primary_key=True)
    sequence = models.ForeignKey(Sequence, on_delete=models.CASCADE)
    library_id = models.CharField(max_length=255)
    association_date = models.DateTimeField()
    status = models.CharField(max_length=255, default="active")

    objects = LibraryAssociationManager()

    def __str__(self):
        return f"ID: {self.orcabus_id}, sequence: {self.sequence}, library_id: {self.library_id}, status: {self.status}"
