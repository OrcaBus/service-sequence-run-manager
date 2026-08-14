import os
import logging
from django.utils import timezone
from libumccr.aws import libeb
from sequence_run_manager_proc.domain.samplesheet import SampleSheetDomain
from sequence_run_manager_proc.domain.librarylinking import LibraryLinkingDomain
from sequence_run_manager_proc.domain.events.srsc import SequenceRunStateChange

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SRSC_EVENT_TYPE = SequenceRunStateChange.__name__
SRSSC_EVENT_TYPE = "SequenceRunSampleSheetChange"
SRLLC_EVENT_TYPE = "SequenceRunLibraryLinkingChange"
SRM_SOURCE = "orcabus.sequencerunmanager"


class EventBridgePublishError(RuntimeError):
    """Raised when EventBridge accepts a request but rejects its event entry."""

    def __init__(self, message: str, failed_entries: list[dict] | None = None):
        super().__init__(message)
        self.failed_entries = failed_entries or []


def _get_event_bus_name():
    event_bus_name = os.environ.get("EVENT_BUS_NAME", None)
    if event_bus_name is None:
        logger.error("EVENT_BUS_NAME is not set")
    return event_bus_name


def _event_type_is_valid(event: dict, expected_event_type: str) -> bool:
    event_type = event.get("eventType")
    if event_type != expected_event_type:
        logger.error(f"Unsupported event type: {event_type}")
        return False
    return True


def _emit_api_event(event_type: str, event_entry: dict, event_bus_name: str):
    try:
        response = libeb.emit_event(event_entry)
        logger.info(
            f"Sent a {event_type} event to event bus {event_bus_name}: {event_entry}"
        )
        return response
    except Exception as e:
        logger.error(f"Failed to emit {event_type} event: {e}")
        return


def emit_srsc_api_event(event: dict, attempt_count: int = 1):
    """Validate and emit a SequenceRunStateChange created through the API."""
    event_id = event.get("id", "unknown")
    instrument_run_id = event.get("instrumentRunId", "unknown")
    event_status = event.get("status", "unknown")

    try:
        event_bus_name = os.environ.get("EVENT_BUS_NAME", None)
        if event_bus_name is None:
            raise ValueError("EVENT_BUS_NAME environment variable is not set.")

        validated = SequenceRunStateChange.model_validate(event)
        detail_json = validated.model_dump_json()
        event_id = validated.id
        instrument_run_id = validated.instrumentRunId
        event_status = validated.status

        logger.info(
            "Emitting SRSC event: event_id=%s instrument_run_id=%s status=%s attempt=%s",
            event_id,
            instrument_run_id,
            event_status,
            attempt_count,
        )
        response = libeb.emit_event(
            {
                "Source": SRM_SOURCE,
                "DetailType": SRSC_EVENT_TYPE,
                "Detail": detail_json,
                "EventBusName": event_bus_name,
            }
        )

        failed_entry_count = response.get("FailedEntryCount", 0)
        if failed_entry_count:
            failed_entries = [
                {
                    "error_code": entry.get("ErrorCode"),
                    "error_message": entry.get("ErrorMessage"),
                }
                for entry in response.get("Entries", [])
                if entry.get("ErrorCode") or entry.get("ErrorMessage")
            ]
            logger.error(
                "EventBridge rejected SRSC event entry: event_id=%s instrument_run_id=%s status=%s attempt=%s failed_entry_count=%s failed_entries=%s",
                event_id,
                instrument_run_id,
                event_status,
                attempt_count,
                failed_entry_count,
                failed_entries,
            )
            raise EventBridgePublishError(
                f"EventBridge rejected {failed_entry_count} SRSC event entry: {failed_entries}",
                failed_entries=failed_entries,
            )

        logger.info(
            "SRSC event emitted: event_id=%s instrument_run_id=%s status=%s attempt=%s",
            event_id,
            instrument_run_id,
            event_status,
            attempt_count,
        )
        return response
    except Exception:
        logger.exception(
            "Failed to emit SRSC event: event_id=%s instrument_run_id=%s status=%s attempt=%s",
            event_id,
            instrument_run_id,
            event_status,
            attempt_count,
        )
        raise


def emit_srssc_api_event(event):
    """
    Emit SRSSC events to the event bridge sourced from the sequence run manager API.

    Example:
    {
    "version": "0",
    "id": "12345678-90ab-cdef-1234-567890abcdef",
    "detail-type": "SequenceRunSampleSheetChange",
    "source": "orcabus.sequencerunmanager",
    "account": "000000000000",
    "time": "2025-03-00T00:00:00Z",
    "region": "ap-southeast-2",
    "resources": [],
    "detail": {
        "instrumentRunId": "250328_A01052_0258_AHFGM7DSXF",
        "sequenceRunId": "r.1234567890abcdefghijklmn", // fake sequence run id (if empty, a new ghost sequence run is created)
        "timeStamp": "2025-03-01T00:00:00.000000+00:00",
        "sampleSheetName": "sampleSheet_v2.csv",
        "samplesheetBase64gz": "base64_encoded_samplesheet........",
        "comment":{
            "comment": "comment",
            "created_by": "user",
            "created_at": "2025-03-01T00:00:00.000000+00:00"
        }
        }
    }
    """

    event_bus_name = _get_event_bus_name()
    if event_bus_name is None:
        return

    if not _event_type_is_valid(event, SRSSC_EVENT_TYPE):
        return

    sample_sheet_domain = SampleSheetDomain(
        instrument_run_id=event["instrumentRunId"],
        sequence_run_id=event["sequenceRunId"],
        sample_sheet=event["sampleSheet"],
        description=event["description"],
    )
    event_entry = sample_sheet_domain.to_put_events_request_entry(
        event_bus_name=event_bus_name,
    )

    return _emit_api_event(SRSSC_EVENT_TYPE, event_entry, event_bus_name)


def emit_srllc_api_event(event):
    """
    Emit SRLLC events to the event bridge sourced from the sequence run manager API.

    Example:
    {
    "version": "0",
    "id": "12345678-90ab-cdef-1234-567890abcdef",
    "detail-type": "SequenceRunLibraryLinkingChange",
    "source": "orcabus.sequencerunmanager",
    "account": "000000000000",
    "time": "2025-03-00T00:00:00Z",
    "region": "ap-southeast-2",
    "resources": [],
    "detail": {
        "instrumentRunId": "250328_A01052_0258_AHFGM7DSXF",
        "sequenceRunId": "r.1234567890abcdefghijklmn", // fake sequence run id (required as sequence run is necessary for library linking)
        "timeStamp": "2025-03-01T00:00:00.000000+00:00",
        "linkedLibraries": [
                "L2000000",
                "L2000001",
                "L2000002"
            ],
        }
    }
    """

    event_bus_name = _get_event_bus_name()
    if event_bus_name is None:
        return

    if not _event_type_is_valid(event, SRLLC_EVENT_TYPE):
        return

    library_linking_domain = LibraryLinkingDomain(
        instrument_run_id=event["instrumentRunId"],
        sequence_run_id=event["sequenceRunId"],
        linked_libraries=event["linkedLibraries"],
        timestamp=(event["timeStamp"] if "timeStamp" in event else timezone.now()),
    )
    event_entry = library_linking_domain.to_put_events_request_entry(
        event_bus_name=event_bus_name,
    )

    return _emit_api_event(SRLLC_EVENT_TYPE, event_entry, event_bus_name)
