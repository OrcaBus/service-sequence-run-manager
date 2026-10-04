import base64
import gzip
from unittest.mock import patch

from django.utils import timezone

from sequence_run_manager.models.sequence import Sequence, LibraryAssociation
from sequence_run_manager.models.sample_sheet import SampleSheet
from sequence_run_manager.models.comment import Comment
from sequence_run_manager.tests.factories import TestConstant, SequenceFactory
from sequence_run_manager_proc.domain.librarylinking import SRLLC_SCHEMA_VERSION
from sequence_run_manager_proc.domain.samplesheet import SRSSC_SCHEMA_VERSION
from sequence_run_manager_proc.tests.factories import SequenceRunManagerProcFactory
from sequence_run_manager_proc.lambdas import samplesheet_event
from sequence_run_manager_proc.tests.case import logger, SequenceRunProcUnitTestCase

"""
example event:
1) SRSSU event payload dict
    {
    "version": "0",
    "id": f8c3de3d-1fea-4d7c-a8b0-29f63c4c3454",  # Random UUID
    "detail-type": "SequenceRunSampleSheetUpdate",
    "source": "orcabus.manual",
    "account": "444444444444",
    "time": "2024-11-02T21:58:22Z",
    "region": "ap-southeast-2",
    "resources": [],
    "detail": {
        "id": "<hash of the event data>",  # optional
        "version": "1.0.0",  # optional
        "instrumentRunId": "222222_A01052_1234_BHVJJJJJJ",
        "sequenceRunId": "r.4Wz-ABCDEFGHIJKLMN-A",  # optional
        "timeStamp": "2024-11-02T21:58:13.7451620Z",
        "sampleSheetName": "SampleSheet.V2.134567.csv",
        "samplesheetBase64gz": "base64_encoded_content",
        "comment": {
            "comment": "comment",
            "createdBy": "created_by",
        }
    }
2) WRSC event payload dict
    {
    "version": "0",
    "id": f8c3de3d-1fea-4d7c-a8b0-29f63c4c3454",  # Random UUID
    "detail-type": "WorkflowRunStateChange",
    "source": "orcabus.workflowmanager",
    "account": "000000000000",
    "time": "2025-03-00T00:00:00Z",
    "region": "ap-southeast-2",
    "resources": [],
    "detail": {
        "workflow": {
            "name": "bclconvert",
        },
        "payload": {
            "data": {
                "tags": {
                    "instrumentRunId": "222222_A01052_1234_BHVJJJJJJ",
                    "samplesheetChecksumType": "sha256",
                    ...
                }
                "inputs": {
                    sampleSheetUri: "icav2://222222_A01052_1234_BHVJJJJJJ/sample_sheet.csv",
                    ...
                }
"""

SRSSC = "SequenceRunSampleSheetChange"
SRLLC = "SequenceRunLibraryLinkingChange"

# libraries listed in the sample sheet of `mock_sample_sheet_update_event_message`
SAMPLE_SHEET_LIBRARIES = ["LPRJ250421", "LPRJ250422"]


class SampleSheetEventUnitTests(SequenceRunProcUnitTestCase):
    def setUp(self) -> None:
        super(SampleSheetEventUnitTests, self).setUp()

    def tearDown(self) -> None:
        super(SampleSheetEventUnitTests, self).tearDown()

    def test_event_handler(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_samplesheet_event.SampleSheetEventUnitTests.test_event_handler
        """
        mock_event_message = (
            SequenceRunManagerProcFactory.mock_sample_sheet_update_event_message()
        )

        _ = samplesheet_event.event_handler(mock_event_message, None)

        #  create ghost sequence record
        seq = (
            Sequence.objects.filter(
                instrument_run_id=TestConstant.instrument_run_id.value
            )
            .exclude(sequence_run_id=TestConstant.sequence_run_id.value)
            .first()
        )
        logger.info(f"Found SequenceRun record from db: {seq}")
        self.assertIsNotNone(seq)

        qs_sample_sheet = SampleSheet.objects.filter(sequence=seq)
        logger.info(f"Found SampleSheet record from db: {qs_sample_sheet}")
        self.assertEqual(1, qs_sample_sheet.count())

        qs_libraries = LibraryAssociation.objects.filter(sequence=seq)
        logger.info(f"Found LibraryAssociation record from db: {qs_libraries}")
        self.assertEqual(2, qs_libraries.count())

        qs_comment = Comment.objects.filter(
            target_id=qs_sample_sheet.first().orcabus_id
        )
        logger.info(f"Found Comment record from db: {qs_comment}")
        self.assertEqual(1, qs_comment.count())

        # the stored sample sheet is announced as SRSSC, the new linking as SRLLC
        srssc_events = self.emitted_events(SRSSC)
        self.assertEqual(1, len(srssc_events))
        self.assertEqual(SRSSC_SCHEMA_VERSION, srssc_events[0]["version"])
        self.assertTrue(srssc_events[0]["id"])
        self.assertEqual(seq.sequence_run_id, srssc_events[0]["sequenceRunId"])
        self.assertEqual("SampleSheet.V2.csv", srssc_events[0]["sampleSheetName"])
        self.assertIn(qs_sample_sheet.first().orcabus_id, srssc_events[0]["apiUrl"])
        self.assertIn("Comment: comment", srssc_events[0]["description"])

        srllc_events = self.emitted_events(SRLLC)
        self.assertEqual(1, len(srllc_events))
        self.assertEqual(SRLLC_SCHEMA_VERSION, srllc_events[0]["version"])
        self.assertTrue(srllc_events[0]["id"])
        self.assertEqual(seq.sequence_run_id, srllc_events[0]["sequenceRunId"])
        self.assertEqual(SAMPLE_SHEET_LIBRARIES, srllc_events[0]["linkedLibraries"])

        mock_event_message = (
            SequenceRunManagerProcFactory.mock_workflow_run_update_event_message()
        )
        _ = samplesheet_event.event_handler(mock_event_message, None)

        #  create ghost sequence record
        seq = (
            Sequence.objects.filter(
                instrument_run_id=TestConstant.instrument_run_id.value
            )
            .exclude(sequence_run_id=TestConstant.sequence_run_id.value)
            .first()
        )
        logger.info(f"Found SequenceRun record from db: {seq}")
        self.assertIsNotNone(seq)

        qs_sample_sheet = SampleSheet.objects.filter(sequence=seq)
        logger.info(f"Found SampleSheet record from db: {qs_sample_sheet}")
        self.assertEqual(1, qs_sample_sheet.count())

        # the WRSC event is only validated, nothing more is announced
        self.assertEqual(1, len(self.emitted_events(SRSSC)))
        self.assertEqual(1, len(self.emitted_events(SRLLC)))

    def test_event_handler_for_existing_sequence_run(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_samplesheet_event.SampleSheetEventUnitTests.test_event_handler_for_existing_sequence_run
        """
        seq = SequenceFactory()
        mock_event_message = (
            SequenceRunManagerProcFactory.mock_sample_sheet_update_event_message()
        )
        mock_event_message["detail"]["sequenceRunId"] = seq.sequence_run_id

        _ = samplesheet_event.event_handler(mock_event_message, None)

        # attached to the named sequence run, no ghost sequence run is created
        self.assertEqual(
            1,
            Sequence.objects.filter(
                instrument_run_id=TestConstant.instrument_run_id.value
            ).count(),
        )
        self.assertEqual(1, SampleSheet.objects.filter(sequence=seq).count())

        srssc_events = self.emitted_events(SRSSC)
        self.assertEqual(1, len(srssc_events))
        self.assertEqual(seq.sequence_run_id, srssc_events[0]["sequenceRunId"])
        self.assertEqual(1, len(self.emitted_events(SRLLC)))

    def test_event_handler_skips_srllc_when_linking_unchanged(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_samplesheet_event.SampleSheetEventUnitTests.test_event_handler_skips_srllc_when_linking_unchanged
        """
        seq = SequenceFactory()
        for library_id in SAMPLE_SHEET_LIBRARIES:
            LibraryAssociation.objects.create(
                sequence=seq,
                library_id=library_id,
                association_date=timezone.now(),
                status="ACTIVE",
            )
        mock_event_message = (
            SequenceRunManagerProcFactory.mock_sample_sheet_update_event_message()
        )
        mock_event_message["detail"]["sequenceRunId"] = seq.sequence_run_id

        _ = samplesheet_event.event_handler(mock_event_message, None)

        # the new sample sheet is still announced, the unchanged linking is not
        self.assertEqual(1, len(self.emitted_events(SRSSC)))
        self.assertEqual([], self.emitted_events(SRLLC))

    def test_event_handler_for_unknown_sequence_run(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_samplesheet_event.SampleSheetEventUnitTests.test_event_handler_for_unknown_sequence_run
        """
        mock_event_message = (
            SequenceRunManagerProcFactory.mock_sample_sheet_update_event_message()
        )
        mock_event_message["detail"]["sequenceRunId"] = "r.UNKNOWN"

        _ = samplesheet_event.event_handler(mock_event_message, None)

        self.assertFalse(SampleSheet.objects.exists())
        self.assertEqual([], self.emitted_events(SRSSC))
        self.assertEqual([], self.emitted_events(SRLLC))

    def test_event_handler_without_comment(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_samplesheet_event.SampleSheetEventUnitTests.test_event_handler_without_comment
        """
        mock_event_message = (
            SequenceRunManagerProcFactory.mock_sample_sheet_update_event_message()
        )
        del mock_event_message["detail"]["comment"]

        _ = samplesheet_event.event_handler(mock_event_message, None)

        self.assertEqual(1, SampleSheet.objects.count())
        self.assertFalse(Comment.objects.exists())
        srssc_events = self.emitted_events(SRSSC)
        self.assertEqual(1, len(srssc_events))
        self.assertNotIn("Comment:", srssc_events[0]["description"])

    def test_event_handler_without_libraries(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_samplesheet_event.SampleSheetEventUnitTests.test_event_handler_without_libraries
        """
        sample_sheet_csv = "[Header]\nfileFormatVersion,2\n\n[Reads]\nread1Cycles,151\n"
        mock_event_message = (
            SequenceRunManagerProcFactory.mock_sample_sheet_update_event_message()
        )
        mock_event_message["detail"]["samplesheetBase64gz"] = base64.b64encode(
            gzip.compress(sample_sheet_csv.encode("utf-8"))
        ).decode("utf-8")

        _ = samplesheet_event.event_handler(mock_event_message, None)

        # the sample sheet is announced, there is no linking to announce
        self.assertEqual(1, SampleSheet.objects.count())
        self.assertFalse(LibraryAssociation.objects.exists())
        self.assertEqual(1, len(self.emitted_events(SRSSC)))
        self.assertEqual([], self.emitted_events(SRLLC))

    def test_event_handler_when_linking_update_fails(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_samplesheet_event.SampleSheetEventUnitTests.test_event_handler_when_linking_update_fails
        """
        mock_event_message = (
            SequenceRunManagerProcFactory.mock_sample_sheet_update_event_message()
        )

        with patch(
            "sequence_run_manager_proc.services.sample_sheet_srv.update_sequence_run_libraries_linking",
            side_effect=RuntimeError("database unavailable"),
        ):
            _ = samplesheet_event.event_handler(mock_event_message, None)

        # the stored sample sheet is still announced, the failed linking is not
        self.assertEqual(1, SampleSheet.objects.count())
        self.assertEqual(1, len(self.emitted_events(SRSSC)))
        self.assertEqual([], self.emitted_events(SRLLC))
