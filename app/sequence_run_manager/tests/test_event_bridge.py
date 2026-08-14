import json
import os
from unittest.mock import patch

from django.test import SimpleTestCase
from django.utils import timezone

from sequence_run_manager.aws_event_bridge.event_srv import (
    EventBridgePublishError,
    emit_srllc_api_event,
    emit_srsc_api_event,
    emit_srssc_api_event,
)
from sequence_run_manager.models.sample_sheet import SampleSheet


class SrscApiEventTestCase(SimpleTestCase):
    def build_event(self):
        return {
            "id": "seq.01J5M2JFE1JPYV62RYQEG99SEQ",
            "instrumentRunId": "250328_A01052_0258_AHFGM7DSXF",
            "runVolumeName": "bssh.example",
            "runFolderPath": "/Runs/250328_A01052_0258_AHFGM7DSXF",
            "runDataUri": "gds://bssh.example/Runs/250328_A01052_0258_AHFGM7DSXF",
            "sampleSheetName": None,
            "startTime": timezone.now().isoformat(),
            "endTime": None,
            "status": "RESOLVED",
        }

    @patch.dict(os.environ, {"EVENT_BUS_NAME": "test-event-bus"})
    @patch("sequence_run_manager.aws_event_bridge.event_srv.libeb.emit_event")
    def test_emit_srsc_api_event_emits_sequence_run_state_change(
        self, mock_emit_event
    ):
        mock_emit_event.return_value = {"FailedEntryCount": 0, "Entries": [{}]}

        emit_srsc_api_event(self.build_event(), attempt_count=2)

        entry = mock_emit_event.call_args.args[0]
        self.assertEqual(entry["Source"], "orcabus.sequencerunmanager")
        self.assertEqual(entry["DetailType"], "SequenceRunStateChange")
        self.assertEqual(entry["EventBusName"], "test-event-bus")
        detail = json.loads(entry["Detail"])
        self.assertEqual(detail["status"], "RESOLVED")
        self.assertIn("sampleSheetName", detail)
        self.assertIsNone(detail["sampleSheetName"])

    @patch.dict(os.environ, {"EVENT_BUS_NAME": "test-event-bus"})
    @patch("sequence_run_manager.aws_event_bridge.event_srv.libeb.emit_event")
    def test_emit_srsc_api_event_raises_and_logs_partial_failure(
        self, mock_emit_event
    ):
        mock_emit_event.return_value = {
            "FailedEntryCount": 1,
            "Entries": [
                {
                    "ErrorCode": "InternalFailure",
                    "ErrorMessage": "EventBridge failed",
                }
            ],
        }

        with self.assertLogs(
            "sequence_run_manager.aws_event_bridge.event_srv", level="ERROR"
        ) as logs:
            with self.assertRaises(EventBridgePublishError):
                emit_srsc_api_event(self.build_event())

        logged = " ".join(logs.output)
        self.assertIn("seq.01J5M2JFE1JPYV62RYQEG99SEQ", logged)
        self.assertIn("InternalFailure", logged)

    @patch.dict(os.environ, {"EVENT_BUS_NAME": "test-event-bus"})
    @patch("sequence_run_manager.aws_event_bridge.event_srv.libeb.emit_event")
    def test_emit_srsc_api_event_reraises_sdk_exception(self, mock_emit_event):
        mock_emit_event.side_effect = RuntimeError("network unavailable")

        with self.assertLogs(
            "sequence_run_manager.aws_event_bridge.event_srv", level="ERROR"
        ) as logs:
            with self.assertRaisesRegex(RuntimeError, "network unavailable"):
                emit_srsc_api_event(self.build_event(), attempt_count=3)

        logged = " ".join(logs.output)
        self.assertIn("seq.01J5M2JFE1JPYV62RYQEG99SEQ", logged)
        self.assertIn("attempt=3", logged)

    @patch.dict(os.environ, {}, clear=True)
    def test_emit_srsc_api_event_raises_when_event_bus_is_missing(self):
        with self.assertLogs(
            "sequence_run_manager.aws_event_bridge.event_srv", level="ERROR"
        ) as logs:
            with self.assertRaisesRegex(ValueError, "EVENT_BUS_NAME"):
                emit_srsc_api_event(self.build_event())

        logged = " ".join(logs.output)
        self.assertIn("seq.01J5M2JFE1JPYV62RYQEG99SEQ", logged)


class SrsscApiEventTestCase(SimpleTestCase):
    def build_event(self, event_type="SequenceRunSampleSheetChange"):
        sample_sheet = SampleSheet(
            orcabus_id="ss.01J5M2JFE1JPYV62RYQEG99SS",
            sample_sheet_name="SampleSheet.csv",
            sample_sheet_content_original="sample,sheet\n",
            association_timestamp=timezone.now(),
        )
        return {
            "eventType": event_type,
            "instrumentRunId": "250328_A01052_0258_AHFGM7DSXF",
            "sequenceRunId": "r.01J5M2JFE1JPYV62RYQEG99RUN",
            "sampleSheet": sample_sheet,
            "description": "Manual sample sheet update",
        }

    @patch.dict(
        os.environ,
        {
            "EVENT_BUS_NAME": "test-event-bus",
            "SEQUENCE_RUN_MANAGER_BASE_API_URL": "https://srm.example",
        },
    )
    @patch("sequence_run_manager.aws_event_bridge.event_srv.libeb.emit_event")
    def test_emit_srssc_api_event_emits_sample_sheet_change(self, mock_emit_event):
        mock_emit_event.return_value = {"FailedEntryCount": 0, "Entries": [{}]}

        response = emit_srssc_api_event(self.build_event())

        self.assertEqual(response, {"FailedEntryCount": 0, "Entries": [{}]})
        entry = mock_emit_event.call_args.args[0]
        self.assertEqual(entry["DetailType"], "SequenceRunSampleSheetChange")
        self.assertEqual(entry["EventBusName"], "test-event-bus")
        detail = json.loads(entry["Detail"])
        self.assertEqual(detail["instrumentRunId"], "250328_A01052_0258_AHFGM7DSXF")
        self.assertEqual(detail["sampleSheetName"], "SampleSheet.csv")

    @patch.dict(os.environ, {}, clear=True)
    @patch("sequence_run_manager.aws_event_bridge.event_srv.libeb.emit_event")
    def test_emit_srssc_api_event_returns_when_event_bus_is_missing(
        self, mock_emit_event
    ):
        with self.assertLogs(
            "sequence_run_manager.aws_event_bridge.event_srv", level="ERROR"
        ) as logs:
            response = emit_srssc_api_event(self.build_event())

        self.assertIsNone(response)
        mock_emit_event.assert_not_called()
        self.assertIn("EVENT_BUS_NAME is not set", " ".join(logs.output))

    @patch.dict(os.environ, {"EVENT_BUS_NAME": "test-event-bus"})
    @patch("sequence_run_manager.aws_event_bridge.event_srv.libeb.emit_event")
    def test_emit_srssc_api_event_returns_for_wrong_event_type(
        self, mock_emit_event
    ):
        with self.assertLogs(
            "sequence_run_manager.aws_event_bridge.event_srv", level="ERROR"
        ) as logs:
            response = emit_srssc_api_event(
                self.build_event(event_type="SequenceRunLibraryLinkingChange")
            )

        self.assertIsNone(response)
        mock_emit_event.assert_not_called()
        self.assertIn("Unsupported event type", " ".join(logs.output))

    @patch.dict(
        os.environ,
        {
            "EVENT_BUS_NAME": "test-event-bus",
            "SEQUENCE_RUN_MANAGER_BASE_API_URL": "https://srm.example",
        },
    )
    @patch("sequence_run_manager.aws_event_bridge.event_srv.libeb.emit_event")
    def test_emit_srssc_api_event_logs_and_returns_on_emit_exception(
        self, mock_emit_event
    ):
        mock_emit_event.side_effect = RuntimeError("event bus unavailable")

        with self.assertLogs(
            "sequence_run_manager.aws_event_bridge.event_srv", level="ERROR"
        ) as logs:
            response = emit_srssc_api_event(self.build_event())

        self.assertIsNone(response)
        self.assertIn(
            "Failed to emit SequenceRunSampleSheetChange", " ".join(logs.output)
        )


class SrllcApiEventTestCase(SimpleTestCase):
    def build_event(self, event_type="SequenceRunLibraryLinkingChange"):
        return {
            "eventType": event_type,
            "instrumentRunId": "250328_A01052_0258_AHFGM7DSXF",
            "sequenceRunId": "r.01J5M2JFE1JPYV62RYQEG99RUN",
            "linkedLibraries": ["L2000001", "L2000002"],
        }

    @patch.dict(os.environ, {"EVENT_BUS_NAME": "test-event-bus"})
    @patch("sequence_run_manager.aws_event_bridge.event_srv.libeb.emit_event")
    def test_emit_srllc_api_event_emits_library_linking_change(
        self, mock_emit_event
    ):
        mock_emit_event.return_value = {"FailedEntryCount": 0, "Entries": [{}]}

        response = emit_srllc_api_event(self.build_event())

        self.assertEqual(response, {"FailedEntryCount": 0, "Entries": [{}]})
        entry = mock_emit_event.call_args.args[0]
        self.assertEqual(entry["DetailType"], "SequenceRunLibraryLinkingChange")
        self.assertEqual(entry["EventBusName"], "test-event-bus")
        detail = json.loads(entry["Detail"])
        self.assertEqual(detail["instrumentRunId"], "250328_A01052_0258_AHFGM7DSXF")
        self.assertEqual(detail["linkedLibraries"], ["L2000001", "L2000002"])

    @patch.dict(os.environ, {}, clear=True)
    @patch("sequence_run_manager.aws_event_bridge.event_srv.libeb.emit_event")
    def test_emit_srllc_api_event_returns_when_event_bus_is_missing(
        self, mock_emit_event
    ):
        with self.assertLogs(
            "sequence_run_manager.aws_event_bridge.event_srv", level="ERROR"
        ) as logs:
            response = emit_srllc_api_event(self.build_event())

        self.assertIsNone(response)
        mock_emit_event.assert_not_called()
        self.assertIn("EVENT_BUS_NAME is not set", " ".join(logs.output))

    @patch.dict(os.environ, {"EVENT_BUS_NAME": "test-event-bus"})
    @patch("sequence_run_manager.aws_event_bridge.event_srv.libeb.emit_event")
    def test_emit_srllc_api_event_returns_for_wrong_event_type(
        self, mock_emit_event
    ):
        with self.assertLogs(
            "sequence_run_manager.aws_event_bridge.event_srv", level="ERROR"
        ) as logs:
            response = emit_srllc_api_event(
                self.build_event(event_type="SequenceRunSampleSheetChange")
            )

        self.assertIsNone(response)
        mock_emit_event.assert_not_called()
        self.assertIn("Unsupported event type", " ".join(logs.output))
