from django.utils import timezone

from sequence_run_manager.models.state import State
from sequence_run_manager.tests.factories import SequenceFactory
from sequence_run_manager_proc.services.sequence_state_srv import (
    map_sequence_run_new_state_to_srsc,
)
from sequence_run_manager_proc.tests.case import SequenceRunProcUnitTestCase


class SequenceStateSrvUnitTests(SequenceRunProcUnitTestCase):
    def test_map_sequence_run_new_state_uses_empty_strings_for_null_fields(self):
        sequence = SequenceFactory(
            run_volume_name=None,
            run_folder_path=None,
            run_data_uri=None,
            sample_sheet_name=None,
            end_time=None,
        )
        new_state = State(
            sequence=sequence,
            status=None,
            timestamp=timezone.now(),
        )

        event = map_sequence_run_new_state_to_srsc(sequence, new_state).model_dump(
            mode="json"
        )

        for field in (
            "runVolumeName",
            "runFolderPath",
            "runDataUri",
            "sampleSheetName",
            "endTime",
            "status",
        ):
            self.assertEqual(event[field], "")
