from django.utils import timezone
from django.utils.timezone import now

from sequence_run_manager.models.state import State
from sequence_run_manager.tests.factories import SequenceFactory
from sequence_run_manager_proc.domain.events.srsc import SequenceRunStateChange
from sequence_run_manager_proc.services.sequence_state_srv import (
    SRSC_SCHEMA_VERSION,
    get_srsc_hash,
    map_sequence_run_new_state_to_srsc,
    srsc_event_detail,
    srsc_event_detail_json,
)
from sequence_run_manager_proc.tests.case import SequenceRunProcUnitTestCase


class SequenceStateSrvUnitTests(SequenceRunProcUnitTestCase):
    def test_map_sequence_run_new_state_uses_schema_compatible_null_values(self):
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

        for field in ("runVolumeName", "runFolderPath", "runDataUri", "status"):
            self.assertEqual(event[field], "")

        self.assertIsNone(event["sampleSheetName"])
        self.assertIsNone(event["endTime"])


class SrscHashUnitTests(SequenceRunProcUnitTestCase):
    """Content hashing of SequenceRunStateChange events (schema 1.1.0)."""

    def build_srsc(self, **overrides) -> SequenceRunStateChange:
        fields = {
            "id": "",
            "version": SRSC_SCHEMA_VERSION,
            "orcabusId": "seq.01J5M2JFE1JPYV62RYQEG99SEQ",
            "instrumentRunId": "250328_A01052_0258_AHFGM7DSXF",
            "runVolumeName": "bssh.example",
            "runFolderPath": "/Runs/250328_A01052_0258_AHFGM7DSXF",
            "runDataUri": "gds://bssh.example/Runs/250328_A01052_0258_AHFGM7DSXF",
            "sampleSheetName": "SampleSheet.csv",
            "startTime": now(),
            "endTime": None,
            "status": "RESOLVED",
            "stateCreatedBy": None,
        }
        fields.update(overrides)
        return SequenceRunStateChange(**fields)

    def test_hash_is_stable_and_idempotent(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_sequence_state_srv.SrscHashUnitTests.test_hash_is_stable_and_idempotent
        """
        first = get_srsc_hash(self.build_srsc())
        # A later timestamp must not change the hash: only content does.
        second = get_srsc_hash(self.build_srsc(startTime=now()))
        self.assertEqual(first, second)

        # An event that already carries an id keeps it.
        self.assertEqual(get_srsc_hash(self.build_srsc(id=first)), first)

    def test_hash_differs_by_status_and_state_created_by(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_sequence_state_srv.SrscHashUnitTests.test_hash_differs_by_status_and_state_created_by
        """
        unauthored = get_srsc_hash(self.build_srsc())
        deprecated = get_srsc_hash(self.build_srsc(status="DEPRECATED"))
        authored = get_srsc_hash(self.build_srsc(stateCreatedBy="jane@example.org"))
        other_author = get_srsc_hash(self.build_srsc(stateCreatedBy="joe@example.org"))

        self.assertNotEqual(unauthored, deprecated)
        self.assertNotEqual(unauthored, authored)
        self.assertNotEqual(authored, other_author)

    def test_detail_omits_state_created_by_when_unauthored(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_sequence_state_srv.SrscHashUnitTests.test_detail_omits_state_created_by_when_unauthored
        """
        unauthored = self.build_srsc()
        unauthored.id = get_srsc_hash(unauthored)
        self.assertNotIn("stateCreatedBy", srsc_event_detail(unauthored))
        self.assertNotIn("stateCreatedBy", srsc_event_detail_json(unauthored))

        authored = self.build_srsc(stateCreatedBy="jane@example.org")
        authored.id = get_srsc_hash(authored)
        self.assertEqual(
            srsc_event_detail(authored)["stateCreatedBy"], "jane@example.org"
        )
