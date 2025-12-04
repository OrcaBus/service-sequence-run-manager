import os
import logging
from django.utils import timezone
from libumccr.aws import libeb
from sequence_run_manager_proc.domain.samplesheet import SampleSheetDomain
from sequence_run_manager_proc.domain.librarylinking import LibraryLinkingDomain

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def emit_srm_api_event(event):
    """
    Emit events to the event bridge sourced from the sequence run manager API

    so far we only support SRSSC and SRLLC events, examples:
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

    # construct event
    supported_event_types = ["SequenceRunSampleSheetChange", "SequenceRunLibraryLinkingChange"]
    event_bus_name = os.environ.get("EVENT_BUS_NAME", None)

    if event_bus_name is None:
        logger.error("EVENT_BUS_NAME is not set")
        return

    event_type = event["eventType"]
    if event_type not in supported_event_types:
        logger.error(f"Unsupported event type: {event_type}")
        return


    event_entry = None
    match event_type:
        case "SequenceRunSampleSheetChange":
            sample_sheet_domain = SampleSheetDomain(
                instrument_run_id=event["instrumentRunId"],
                sequence_run_id=event["sequenceRunId"],
                sample_sheet=event["sampleSheet"],
                description=event["description"],
            )
            event_entry = sample_sheet_domain.to_put_events_request_entry(
                event_bus_name=event_bus_name,
            )

        case "SequenceRunLibraryLinkingChange":
            library_linking_domain = LibraryLinkingDomain(
                instrument_run_id=event["instrumentRunId"],
                sequence_run_id=event["sequenceRunId"],
                linked_libraries=event["linkedLibraries"],
                timestamp=event["timeStamp"] if "timeStamp" in event else timezone.now(),
            )
            event_entry = library_linking_domain.to_put_events_request_entry(
                event_bus_name=event_bus_name,
            )

        case _:
            logger.error(f"Unsupported event type: {event['eventType']}")
            return

    # emit event
    if event_entry is not None:
        try:
            response = libeb.emit_event(event_entry)
            logger.info(f"Sent a {event_type} event to event bus {event_bus_name}: {event_entry}")
            return response
        except Exception as e:
            logger.error(f"Failed to emit event: {e}")
            return
    else:
        logger.error(f"Failed to construct event entry for {event_type}")
        return
