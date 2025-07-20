from rest_framework import serializers

from sequence_run_manager.models import Sequence
from sequence_run_manager.serializers.base import SerializersBase, OptionalFieldsMixin, OrcabusIdSerializerMetaMixin


class SequenceBaseSerializer(SerializersBase):
    pass


class SequenceRunListParamSerializer(OptionalFieldsMixin, SequenceBaseSerializer):
    class Meta(OrcabusIdSerializerMetaMixin):
        model = Sequence
        fields = "__all__"

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


class SequenceRunGroupByInstrumentRunIdSerializer(serializers.Serializer):
    instrument_run_id = serializers.CharField(help_text="The instrument run ID")
    start_time = serializers.DateTimeField(help_text="Earliest start time of sequences in this group")
    end_time = serializers.DateTimeField(help_text="Latest end time of sequences in this group")
    count = serializers.IntegerField(help_text="Number of sequences in this group")
    items = SequenceRunMinSerializer(many=True)

    class Meta(OrcabusIdSerializerMetaMixin):
        model = Sequence
        fields = ["instrument_run_id", "start_time", "end_time", "count", "items"]

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
