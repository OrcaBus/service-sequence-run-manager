from sequence_run_manager.models.sequence import Sequence, LibraryAssociation
from sequence_run_manager.models.sample_sheet import SampleSheet
from sequence_run_manager.tests.factories import TestConstant
from sequence_run_manager_proc.domain.librarylinking import SRLLC_SCHEMA_VERSION
from sequence_run_manager_proc.tests.factories import SequenceRunManagerProcFactory
from sequence_run_manager_proc.lambdas import librarylinking_event, samplesheet_event
from sequence_run_manager_proc.tests.case import logger, SequenceRunProcUnitTestCase

"""
example event:
    {
    "version": "0",
    "id": f8c3de3d-1fea-4d7c-a8b0-29f63c4c3454",  # Random UUID
    "detail-type": "SequenceRunLibraryLinkingUpdate",
    "source": "orcabus.manual",
    "account": "444444444444",
    "time": "2024-11-02T21:58:22Z",
    "region": "ap-southeast-2",
    "resources": [],
    "detail": {
        "id": "<hash of the event data>",  # optional
        "version": "1.0.0",  # optional
        "instrumentRunId": "222222_A01052_1234_BHVJJJJJJ",
        "sequenceRunId": "r.4Wz-ABCDEFGHIJKLMN-A",
        "timeStamp": "2024-11-02T21:58:13.7451620Z",
        "linkedLibraries": ["L06789ABCD", "L01234ABCD", "L01234ABCDG"]
    }
"""

SRLLC = "SequenceRunLibraryLinkingChange"


class LibraryLinkingEventUnitTests(SequenceRunProcUnitTestCase):
    def setUp(self) -> None:
        super(LibraryLinkingEventUnitTests, self).setUp()

    def tearDown(self) -> None:
        super(LibraryLinkingEventUnitTests, self).tearDown()

    def test_event_handler(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_librarylinking_event.LibraryLinkingEventUnitTests.test_event_handler
        """
        mock_samplesheet_event_message = (
            SequenceRunManagerProcFactory.mock_sample_sheet_update_event_message()
        )
        _ = samplesheet_event.event_handler(mock_samplesheet_event_message, None)

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

        qs_libraries = LibraryAssociation.objects.filter(sequence=seq)
        logger.info(f"Found LibraryAssociation record from db: {qs_libraries}")
        self.assertEqual(2, qs_libraries.count())
        # the linking created from the sample sheet is announced once
        self.assertEqual(1, len(self.emitted_events(SRLLC)))

        #  create library linking event
        mock_library_linking_event_message = (
            SequenceRunManagerProcFactory.mock_library_linking_update_event_message(
                seq.sequence_run_id
            )
        )
        _ = librarylinking_event.event_handler(mock_library_linking_event_message, None)

        qs_libraries = LibraryAssociation.objects.filter(sequence=seq)
        logger.info(f"Found LibraryAssociation record from db: {qs_libraries}")
        self.assertEqual(3, qs_libraries.count())

        # the changed linking is announced as SRLLC
        srllc_events = self.emitted_events(SRLLC)
        self.assertEqual(2, len(srllc_events))
        srllc = srllc_events[-1]
        self.assertEqual(SRLLC_SCHEMA_VERSION, srllc["version"])
        self.assertTrue(srllc["id"])
        self.assertEqual(seq.sequence_run_id, srllc["sequenceRunId"])
        self.assertEqual(seq.instrument_run_id, srllc["instrumentRunId"])
        self.assertEqual(
            mock_library_linking_event_message["detail"]["linkedLibraries"],
            srllc["linkedLibraries"],
        )

        # replaying the same update changes nothing, so nothing more is announced
        _ = librarylinking_event.event_handler(mock_library_linking_event_message, None)
        self.assertEqual(3, LibraryAssociation.objects.filter(sequence=seq).count())
        self.assertEqual(2, len(self.emitted_events(SRLLC)))

    def test_event_handler_for_unknown_sequence_run(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_librarylinking_event.LibraryLinkingEventUnitTests.test_event_handler_for_unknown_sequence_run
        """
        mock_library_linking_event_message = (
            SequenceRunManagerProcFactory.mock_library_linking_update_event_message(
                "r.UNKNOWN"
            )
        )
        _ = librarylinking_event.event_handler(mock_library_linking_event_message, None)

        self.assertFalse(LibraryAssociation.objects.exists())
        self.assertEqual([], self.emitted_events(SRLLC))

    def test_event_handler_ignores_other_detail_types(self):
        """
        python manage.py test sequence_run_manager_proc.tests.test_librarylinking_event.LibraryLinkingEventUnitTests.test_event_handler_ignores_other_detail_types
        """
        mock_library_linking_event_message = (
            SequenceRunManagerProcFactory.mock_library_linking_update_event_message(
                "r.UNKNOWN"
            )
        )
        mock_library_linking_event_message["detail-type"] = SRLLC

        result = librarylinking_event.event_handler(
            mock_library_linking_event_message, None
        )

        self.assertIn("Invalid event detail type", result["message"])
        self.assertEqual([], self.emitted_events(SRLLC))
