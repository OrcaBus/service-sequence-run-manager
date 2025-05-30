from sequence_run_manager.models.sequence import Sequence
from sequence_run_manager.tests.factories import TestConstant, SequenceFactory
from sequence_run_manager_proc.domain.sequence import SequenceDomain
from sequence_run_manager_proc.services import sequence_srv
from sequence_run_manager_proc.tests.case import logger, SequenceRunProcUnitTestCase

class SequenceRunSrvUnitTests(SequenceRunProcUnitTestCase):
    def setUp(self) -> None:
        super(SequenceRunSrvUnitTests, self).setUp()

    def tearDown(self) -> None:
        super(SequenceRunSrvUnitTests, self).tearDown()

    def test_create_or_update_sequence_from_bssh_event(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_sequence_srv.SequenceRunSrvUnitTests.test_create_or_update_sequence_from_bssh_event
        """
        mock_payload = {
            "id": TestConstant.sequence_run_id.value,
            "name": TestConstant.sequence_run_id.value,
            "instrumentRunId": TestConstant.instrument_run_id.value,
            "dateModified": "2020-05-09T22:17:10.815Z",
            "status": "New",
            "gdsFolderPath": f"/Runs/{TestConstant.instrument_run_id.value}_{TestConstant.sequence_run_id.value}",
            "gdsVolumeName": "bssh.dev",
            "reagentBarcode": "foo",
            "flowcellBarcode": "bar",
            "sampleSheetName": "SampleSheet.csv",
            "apiUrl": f"https://bssh.dev/api/v1/runs/{TestConstant.sequence_run_id.value}",
            'v1pre3Id': '1234567890',
            "acl": [
                "wid:12345678-debe-3f9f-8b92-21244f46822c",
                "tid:Yxmm......"
            ],
            "icaProjectId": "12345678-53ba-47a5-854d-e6b53101adb7",
        }
        seq_domain: SequenceDomain = (
            sequence_srv.create_or_update_sequence_from_bssh_event(mock_payload)
        )
        self.assertIsNotNone(seq_domain)
        logger.info(seq_domain)
        seq_in_db: Sequence = Sequence.objects.get(
            sequence_run_id=TestConstant.sequence_run_id.value
        )
        self.assertEqual(
            seq_domain.sequence.sequence_run_id, seq_in_db.sequence_run_id
        )
        self.assertTrue(
            seq_domain.status_has_changed
        )  # assert Sequence Run Status has changed True
        self.assertTrue(
            seq_domain.state_has_changed
        )  # assert Sequence Run State has changed True

        # assert status value are stored as upper case
        self.assertEqual(seq_in_db.status, "STARTED")

    def test_create_or_update_sequence_from_bssh_event_skip(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_sequence_srv.SequenceRunSrvUnitTests.test_create_or_update_sequence_from_bssh_event_skip
        """
        mock_seq: Sequence = SequenceFactory()
        seq_domain: SequenceDomain = (
            sequence_srv.create_or_update_sequence_from_bssh_event(
                {
                    "id": mock_seq.sequence_run_id,
                    "instrumentRunId": mock_seq.instrument_run_id,
                    "dateModified": mock_seq.start_time,
                    "gdsFolderPath": mock_seq.run_folder_path,
                    "gdsVolumeName": mock_seq.run_volume_name,
                    "status": "New",
                    'apiUrl': 'https://bssh.dev/api/v1/runs/r.ACGTlKjDgEy099ioQOeOWg',
                    'v1pre3Id': '1234567890',
                    "acl": [
                        "wid:12345678-debe-3f9f-8b92-21244f46822c",
                        "tid:Yxmm......"
                    ],
                    "icaProjectId": "12345678-53ba-47a5-854d-e6b53101adb7",
                    'apiUrl': 'https://bssh.dev/api/v1/runs/r.ACGTlKjDgEy099ioQOeOWg',
                    'v1pre3Id': '1234567890',
                    "acl": [
                        "wid:12345678-debe-3f9f-8b92-21244f46822c",
                        "tid:Yxmm......"
                    ],
                    "icaProjectId": "12345678-53ba-47a5-854d-e6b53101adb7",
                }
            )
        )
        self.assertIsNotNone(seq_domain)
        self.assertEqual(1, Sequence.objects.count())
        self.assertFalse(
            seq_domain.status_has_changed
        )  # assert Sequence Run Status has changed False
