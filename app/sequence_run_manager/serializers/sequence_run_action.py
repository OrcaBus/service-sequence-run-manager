from rest_framework import serializers


class AddSampleSheetSerializer(serializers.Serializer):
    """Multipart body for POST .../sequence_run/action/add_samplesheet/."""

    file = serializers.FileField(help_text="The sample sheet file to upload")
    instrument_run_id = serializers.CharField(
        help_text="The instrument run ID to associate with the sample sheet"
    )
    created_by = serializers.CharField(help_text="The user who is creating this sample sheet")
    comment = serializers.CharField(help_text="Comment about the sample sheet")
