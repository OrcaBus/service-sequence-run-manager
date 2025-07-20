from sequence_run_manager.models.sequence import Sequence, LibraryAssociation
from sequence_run_manager.models.sample_sheet import SampleSheet
from sequence_run_manager.tests.factories import TestConstant
from sequence_run_manager_proc.tests.factories import SequenceRunManagerProcFactory
from sequence_run_manager_proc.lambdas import librarylinking_event, samplesheet_event
from sequence_run_manager_proc.tests.case import logger, SequenceRunProcUnitTestCase

"""
example event:
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
"""

class LibraryLinkingEventUnitTests(SequenceRunProcUnitTestCase):
    def setUp(self) -> None:
        super(LibraryLinkingEventUnitTests, self).setUp()

    def tearDown(self) -> None:
        super(LibraryLinkingEventUnitTests, self).tearDown()

    def test_event_handler(self):
        mock_samplesheet_event_message = SequenceRunManagerProcFactory.mock_sample_sheet_change_event_message()
        _ = samplesheet_event.event_handler(mock_samplesheet_event_message, None)

        #  create ghost sequence record
        seq = Sequence.objects.filter(instrument_run_id=TestConstant.instrument_run_id.value).exclude(sequence_run_id=TestConstant.sequence_run_id.value).first()
        logger.info(f"Found SequenceRun record from db: {seq}")
        self.assertIsNotNone(seq)

        qs_libraries = LibraryAssociation.objects.filter(sequence=seq)
        logger.info(f"Found LibraryAssociation record from db: {qs_libraries}")
        self.assertEqual(2, qs_libraries.count())

        #  create library linking event
        mock_library_linking_event_message = SequenceRunManagerProcFactory.mock_library_linking_change_event_message(seq.sequence_run_id)
        _ = librarylinking_event.event_handler(mock_library_linking_event_message, None)

        qs_libraries = LibraryAssociation.objects.filter(sequence=seq)
        logger.info(f"Found LibraryAssociation record from db: {qs_libraries}")
        self.assertEqual(3, qs_libraries.count())
