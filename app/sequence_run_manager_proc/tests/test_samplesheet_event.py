from sequence_run_manager.models.sequence import Sequence, LibraryAssociation
from sequence_run_manager.models.sample_sheet import SampleSheet
from sequence_run_manager.models.comment import Comment
from sequence_run_manager.tests.factories import TestConstant
from sequence_run_manager_proc.tests.factories import SequenceRunManagerProcFactory
from sequence_run_manager_proc.lambdas import samplesheet_event
from sequence_run_manager_proc.tests.case import logger, SequenceRunProcUnitTestCase

"""
example event:
1) SRSSC event payload dict
    {
    "version": "0",
    "id": f8c3de3d-1fea-4d7c-a8b0-29f63c4c3454",  # Random UUID
    "detail-type": "SequenceRunSampleSheetChange",
    "source": "Pipe IcaEventPipeConstru-xxxxxxxx",
    "account": "444444444444",
    "time": "2024-11-02T21:58:22Z",
    "region": "ap-southeast-2",
    "resources": [],
    "detail": {
        "instrumentRunId": "222222_A01052_1234_BHVJJJJJJ",
        "sequenceRunId": "r.4Wz-ABCDEFGHIJKLMN-A",
        "timeStamp": "2024-11-02T21:58:13.7451620Z",
        "sampleSheetName": "SampleSheet.V2.134567.csv",
        "samplesheetbase64gz": "base64_encoded_content",
        "comment": {
            "comment": "comment",
            "createdBy": "created_by",
        }
    }
2) WRU event payload dict
    {
    "version": "0",
    "id": f8c3de3d-1fea-4d7c-a8b0-29f63c4c3454",  # Random UUID
    "detail-type": "WorkflowRunUpdate",
    "source": "orcabus.bclconvert",
    "account": "000000000000",
    "time": "2025-03-00T00:00:00Z",
    "region": "ap-southeast-2",
    "resources": [],
    "detail": {
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

class SampleSheetEventUnitTests(SequenceRunProcUnitTestCase):
    def setUp(self) -> None:
        super(SampleSheetEventUnitTests, self).setUp()

    def tearDown(self) -> None:
        super(SampleSheetEventUnitTests, self).tearDown()

    def test_event_handler(self):
        mock_event_message = SequenceRunManagerProcFactory.mock_sample_sheet_change_event_message()

        _ = samplesheet_event.event_handler(mock_event_message, None)

        #  create ghost sequence record
        seq = Sequence.objects.filter(instrument_run_id=TestConstant.instrument_run_id.value).exclude(sequence_run_id=TestConstant.sequence_run_id.value).first()
        logger.info(f"Found SequenceRun record from db: {seq}")
        self.assertIsNotNone(seq)

        qs_sample_sheet = SampleSheet.objects.filter(sequence=seq)
        logger.info(f"Found SampleSheet record from db: {qs_sample_sheet}")
        self.assertEqual(1, qs_sample_sheet.count())

        qs_libraries = LibraryAssociation.objects.filter(sequence=seq)
        logger.info(f"Found LibraryAssociation record from db: {qs_libraries}")
        self.assertEqual(2, qs_libraries.count())

        qs_comment = Comment.objects.filter(target_id=qs_sample_sheet.first().orcabus_id)
        logger.info(f"Found Comment record from db: {qs_comment}")
        self.assertEqual(1, qs_comment.count())

        mock_event_message = SequenceRunManagerProcFactory.mock_workflow_run_update_event_message()
        _ = samplesheet_event.event_handler(mock_event_message, None)

        #  create ghost sequence record
        seq = Sequence.objects.filter(instrument_run_id=TestConstant.instrument_run_id.value).exclude(sequence_run_id=TestConstant.sequence_run_id.value).first()
        logger.info(f"Found SequenceRun record from db: {seq}")
        self.assertIsNotNone(seq)

        qs_sample_sheet = SampleSheet.objects.filter(sequence=seq)
        logger.info(f"Found SampleSheet record from db: {qs_sample_sheet}")
        self.assertEqual(1, qs_sample_sheet.count())
