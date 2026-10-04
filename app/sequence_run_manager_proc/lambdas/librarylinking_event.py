import os

import django

django.setup()

# --- keep ^^^ at top of the module

import logging

from sequence_run_manager_proc.domain.events import srllu
from sequence_run_manager_proc.services import sequence_library_srv
from libumccr import libjson
from libumccr.aws import libeb

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def event_handler(event, context):
    """
    This lambda function is used to handle the library linking event from the event bus

    SRLLU event payload dict (sent by other services, i.e. any source but orcabus.sequencerunmanager)
    {
    "version": "0",
    "id": "12345678-90ab-cdef-1234-567890abcdef",
    "detail-type": "SequenceRunLibraryLinkingUpdate",
    "source": "orcabus.manual",
    "account": "000000000000",
    "time": "2025-03-00T00:00:00Z",
    "region": "ap-southeast-2",
    "resources": [],
    "detail": {
        "id": "<hash of the event data>", // optional
        "version": "1.0.0", // optional, the SRLLU schema version
        "instrumentRunId": "250328_A01052_0258_AHFGM7DSXF",
        "sequenceRunId": "r.1234567890abcdefghijklmn", // fake sequence run id
        "timeStamp": "2025-03-01T00:00:00.000000+00:00",
        "linkedLibraries": [
                "L2000000",
                "L2000001",
                "L2000002"
            ]
        }
    }
    When the linking changed, it is announced as a SequenceRunLibraryLinkingChange (SRLLC) event.
    """
    logger.info(f"Received event: {event}")
    logger.info(f"Received context: {context}")
    logger.info(libjson.dumps(event))
    logger.info("Start processing library linking event ....")

    if event["detail-type"] != srllu.SequenceRunLibraryLinkingUpdate.__name__:
        logger.error(f"Invalid event detail type: {event['detail-type']}")
        return {
            "message": f"Invalid event detail type: {event['detail-type']}",
        }

    srllu_event = srllu.AWSEvent.model_validate(event)
    library_linking_domain = (
        sequence_library_srv.update_sequence_run_libraries_linking_from_srllu_event(
            srllu_event.detail
        )
    )

    # Detect SequenceRunLibraryLinkingChange and emit event
    if library_linking_domain and library_linking_domain.library_linking_has_changed:
        srllc_entry = library_linking_domain.to_put_events_request_entry(
            event_bus_name=os.environ["EVENT_BUS_NAME"],
        )
        libeb.emit_event(srllc_entry)
        logger.info(f"Emitted SequenceRunLibraryLinkingChange event: {srllc_entry}")

    return {
        "message": "Library linking event processed successfully",
    }
