import os
import logging
import json
from datetime import datetime
from libumccr.aws import libeb
from sequence_run_manager_proc.domain.events.srssc import SequenceRunSampleSheetChange
from sequence_run_manager_proc.domain.events.srllc import SequenceRunLibraryLinkingChange

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
    source = "orcabus.sequencerunmanagerapi"
    supported_event_types = ["SequenceRunSampleSheetChange", "SequenceRunLibraryLinkingChange"]
    event_bus_name = os.environ.get("EVENT_BUS_NAME", None)

    if event_bus_name is None:
        logger.error("EVENT_BUS_NAME is not set")
        return

    event_type = event["eventType"]
    if event_type not in supported_event_types:
        logger.error(f"Unsupported event type: {event_type}")
        return

    source = "orcabus.sequencerunmanagerapi"
    match event_type:
        case "SequenceRunSampleSheetChange":
            detail_type = "SequenceRunSampleSheetChange"
            detail = SequenceRunSampleSheetChange({
                "instrumentRunId": event["instrumentRunId"],
                "sequenceRunId": event["sequenceRunId"],
                "timeStamp": datetime.now(),
                "sampleSheetName": event["sampleSheetName"],
                "samplesheetBase64gz": event["samplesheetBase64gz"],
                "comment": {
                    "comment": event["comment"]["comment"],
                    "created_by": event["comment"]["created_by"],
                    "created_at": event["comment"]["created_at"]
                }
            })

        case "SequenceRunLibraryLinkingChange":
            detail_type = "SequenceRunLibraryLinkingChange"
            detail = SequenceRunLibraryLinkingChange({
                "instrumentRunId": event["instrumentRunId"],
                "sequenceRunId": event["sequenceRunId"],
                "timeStamp": datetime.now(),
                "linkedLibraries": event["linkedLibraries"],

            })

        case _:
            logger.error(f"Unsupported event type: {event['eventType']}")
            return

    # emit event
    response = libeb.emit_event({
        "Source": source,
        "DetailType": detail_type,
        "Detail": json.dumps(detail),
        "EventBusName": event_bus_name,
    })

    logger.info(f"Sent a {event_type} event to event bus {event_bus_name}:")
    logger.info(event)
    logger.info(f"{__name__} done.")
    return response
