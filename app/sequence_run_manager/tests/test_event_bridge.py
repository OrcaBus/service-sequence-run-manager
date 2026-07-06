import json
import os
from unittest.mock import patch

from django.test import SimpleTestCase
from django.utils import timezone

from sequence_run_manager.aws_event_bridge.event_srv import (
    EventBridgePublishError,
    emit_srsc_api_event,
)


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
