from rest_framework import serializers
from rest_framework.settings import api_settings

from sequence_run_manager.models import Sequence, SequenceStatus
from sequence_run_manager.serializers.base import SerializersBase, OptionalFieldsMixin, OrcabusIdSerializerMetaMixin


class SequenceBaseSerializer(SerializersBase):
    pass


class SequenceRunListParamSerializer(OptionalFieldsMixin, SequenceBaseSerializer):
    """
    Model field filters for list / stats / grouped list (exact ``__iexact`` match per query key;
    see ``Sequence.objects.get_by_keyword`` / ``build_keyword_params``).
    """

    class Meta(OrcabusIdSerializerMetaMixin):
        model = Sequence
        fields = [
            "orcabus_id",
            "sequence_run_id",
            "instrument_run_id",
            "sequence_run_name",
            "experiment_name",
            "sample_sheet_name",
            "v1pre3_id",
            "ica_project_id",
            "api_url",
            "run_volume_name",
            "run_folder_path",
            "run_data_uri",
            "reagent_barcode",
            "flowcell_barcode",
        ]


class SequenceRunListQueryParamSerializer(SequenceRunListParamSerializer):
    """
    Full query parameter schema for sequence run list, ``list_by_instrument_run_id``, and stats
    endpoints (OpenAPI / drf-spectacular).

    Includes model field filters from ``SequenceRunListParamSerializer`` plus the filters
    implemented in ``filtered_sequence_runs_queryset`` and ordering in ``SequenceRunViewSet``.

    Search and sort use the DRF query keys from ``REST_FRAMEWORK`` (``SEARCH_PARAM``,
    ``ORDERING_PARAM``), not duplicate aliases.
    """

    start_time = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="ISO 8601 datetime; lower bound on ``Sequence.start_time`` (use with end_time).",
    )
    end_time = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="ISO 8601 datetime; upper bound on ``Sequence.start_time`` (use with start_time).",
    )
    library_id = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Only sequences linked to this library id (via library association).",
    )
    status = serializers.ChoiceField(
        choices=SequenceStatus.choices,
        required=False,
        allow_blank=True,
        help_text=(
            "Filter by ``Sequence.status`` on each row (list and per-sequence stats). "
            "For ``list_by_instrument_run_id`` and instrument-run stats, filters by **group** "
            "status (latest sequence in the group by start_time, then orcabus_id)."
        ),
    )

    # Field names must match REST_FRAMEWORK query keys (defaults: search, ordering).
    locals()[api_settings.SEARCH_PARAM] = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text=(
            "Case-insensitive substring search on orcabus_id, instrument_run_id, sequence_run_id, "
            "sequence_run_name, experiment_name, and sample_sheet_name."
        ),
    )
    locals()[api_settings.ORDERING_PARAM] = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text=(
            "Sort field; must be one of: orcabus_id, instrument_run_id, start_time, end_time, status "
            "(prefix with '-' for descending)."
        ),
    )

    class Meta(SequenceRunListParamSerializer.Meta):
        fields = SequenceRunListParamSerializer.Meta.fields + [
            "start_time",
            "end_time",
            "library_id",
            "status",
            api_settings.SEARCH_PARAM,
            api_settings.ORDERING_PARAM,
        ]

class SequenceRunMinSerializer(SequenceBaseSerializer):
    class Meta(OrcabusIdSerializerMetaMixin):
        model = Sequence
        fields = ["orcabus_id", "instrument_run_id", "sequence_run_id", "experiment_name", "start_time", "end_time", "status"]

class SequenceRunSerializer(SequenceBaseSerializer):
    libraries = serializers.ListField(read_only=True, child=serializers.CharField(), help_text="List of libraries associated with the sequence")

    class Meta(OrcabusIdSerializerMetaMixin):
        model = Sequence
        fields = "__all__"
        include_libraries = True

    def get_libraries(self, obj):
        """
        Get all libraries associated with the sequence
        """
        return obj.libraries()

class SequenceRunCountByStatusSerializer(serializers.Serializer):
    all = serializers.IntegerField()
    started = serializers.IntegerField()
    succeeded = serializers.IntegerField()
    failed = serializers.IntegerField()
    aborted = serializers.IntegerField()
    resolved = serializers.IntegerField()
    deprecated = serializers.IntegerField()


class SequenceRunGroupByInstrumentRunIdSerializer(serializers.Serializer):
    instrument_run_id = serializers.CharField(help_text="The instrument run ID")
    start_time = serializers.DateTimeField(help_text="Earliest start time of sequences in this group")
    end_time = serializers.DateTimeField(help_text="Latest end time of sequences in this group")
    status = serializers.CharField(
        help_text="Group status: latest sequence in the group by start_time (then orcabus_id)",
        required=False,
        allow_null=True,
    )
    count = serializers.IntegerField(help_text="Number of sequences in this group")
    items = SequenceRunMinSerializer(many=True)

    class Meta(OrcabusIdSerializerMetaMixin):
        model = Sequence
        fields = ["instrument_run_id", "start_time", "end_time", "status", "count", "items"]

    def get_schema(self):
        """
        OpenAPI schema for this serializer
        """

        # Return array schema
        return {
            "type": "array",
            "items": self._get_single_item_schema()
        }

    def _get_single_item_schema(self):
        """
        Generate schema for a single item (without array wrapper)
        """
        return {
                        "type": "object",
                        "properties": {
                            "instrumentRunId": {"type": "string"},
                            "startTime": {"type": "string", "format": "date-time"},
                            "endTime": {"type": "string", "format": "date-time"},
                            "status": {"type": "string"},
                            "count": {"type": "integer"},
                            "items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "orcabusId": {"type": "string"},
                                        "instrumentRunId": {"type": "string"},
                                        "sequenceRunId": {"type": "string"},
                                        "experimentName": {"type": "string"},
                                        "startTime": {"type": "string", "format": "date-time"},
                                        "endTime": {"type": "string", "format": "date-time"},
                                        "status": {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
