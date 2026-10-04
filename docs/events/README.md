# Event schemas

This is the location of the events defined by the Sequence Run Manager.
Each event is contained in its own directory and accompanied by examples.

## Events

| Event                             | Abbr. | Emitted by                                                   | Consumed by          |
| --------------------------------- | ----- | ------------------------------------------------------------ | -------------------- |
| `SequenceRunStateChange`          | SRSC  | Sequence Run Manager (`orcabus.sequencerunmanager`)          | downstream services  |
| `SequenceRunSampleSheetChange`    | SRSSC | Sequence Run Manager (`orcabus.sequencerunmanager`)          | downstream services  |
| `SequenceRunLibraryLinkingChange` | SRLLC | Sequence Run Manager (`orcabus.sequencerunmanager`)          | downstream services  |
| `SequenceRunSampleSheetUpdate`    | SRSSU | other services (any source but `orcabus.sequencerunmanager`) | Sequence Run Manager |
| `SequenceRunLibraryLinkingUpdate` | SRLLU | other services (any source but `orcabus.sequencerunmanager`) | Sequence Run Manager |

Like the Workflow Manager's `WorkflowRunUpdate` / `WorkflowRunStateChange` pair, `*Update` events are
requests from other services and `*Change` events are announcements by the Sequence Run Manager:

- **SRSSU → SRSSC**: the Sequence Run Manager stores the sample sheet carried by an SRSSU (on the named
  sequence run, or on a new (ghost) sequence run when `sequenceRunId` is omitted) and announces it as an
  SRSSC. When the sample sheet changes the library linking, an SRLLC follows.
- **SRLLU → SRLLC**: the Sequence Run Manager applies the library linking carried by an SRLLU and, when
  the linking changed, announces it as an SRLLC.

So a `*Change` event always comes from the Sequence Run Manager, regardless of whether the change
originated from BSSH, the API or an `*Update` event.

## JSON schema generation

The JSON schema for each event is generated from an annotated YAML file.


Set up Python environment

```bash
# create and activate a virtual env
uv venv  --python 3.12
source .venv/bin/activate
# install dependencies
uv pip install -r requirements.txt
```

Modify the schema YAML file in the corresponding event directory if required.

Run the JSON schema generation script:

```bash
# generate the JSON schema from the annotated YAML file
python gen_schema.py <event name>/<event name>.schema.yaml > <event name>/<event name>.schema.json
# e.g.:
python gen_schema.py SequenceRunStateChange/SequenceRunStateChange.schema.yaml > SequenceRunStateChange/SequenceRunStateChange.schema.json
python gen_schema.py SequenceRunSampleSheetChange/SequenceRunSampleSheetChange.schema.yaml > SequenceRunSampleSheetChange/SequenceRunSampleSheetChange.schema.json
python gen_schema.py SequenceRunSampleSheetUpdate/SequenceRunSampleSheetUpdate.schema.yaml > SequenceRunSampleSheetUpdate/SequenceRunSampleSheetUpdate.schema.json
python gen_schema.py SequenceRunLibraryLinkingChange/SequenceRunLibraryLinkingChange.schema.yaml > SequenceRunLibraryLinkingChange/SequenceRunLibraryLinkingChange.schema.json
python gen_schema.py SequenceRunLibraryLinkingUpdate/SequenceRunLibraryLinkingUpdate.schema.yaml > SequenceRunLibraryLinkingUpdate/SequenceRunLibraryLinkingUpdate.schema.json

```

The pydantic models in `app/sequence_run_manager_proc/domain/events` are generated from these JSON schemas
with `make schema-gen` in `app`.


## JSON validation

Example events can be validated against their respective JSON schema

```bash
# Example
# If the file is not valid this should produce an exception (non-zero return code)
json validate --schema-file=SequenceRunStateChange/SequenceRunStateChange.schema.json --document-file=SequenceRunStateChange/examples/SRSC__started.json
```

## Schema versioning

Event details carry their own `version` (semver), independent of the AWS
EventBridge envelope `version`.

### SequenceRunStateChange (SRSC)

| Version | Change                                                                                                                                                                                                                                                                                             |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1.1.0   | Added `version`, `orcabusId` and the optional `stateCreatedBy`. `detail.id` is now a content hash of the event (useful for deduplication) instead of the Sequence OrcaBus id — **consumers that read the sequence id from `detail.id` must move to `detail.orcabusId`**.                             |
| 1.0.0   | Initial schema. `detail.id` held the Sequence OrcaBus id and no `version` field was emitted.                                                                                                                                                                                                        |

`stateCreatedBy` is the normalized email of the user who created a custom state
(`RESOLVED`, `DEPRECATED`) through the API. System-generated states — those
driven by BSSH events — have no author and omit the field entirely rather than
sending a null.

The hash covers the schema version, `orcabusId`, `instrumentRunId`, `status` and
`stateCreatedBy`; timestamps are deliberately excluded so re-announcing an
unchanged state yields the same id (see
`app/sequence_run_manager_proc/services/sequence_state_srv.py`).

### SequenceRunSampleSheetChange (SRSSC)

| Version | Change                                                                            |
| ------- | --------------------------------------------------------------------------------- |
| 1.1.0   | Added `version` and `id`, a content hash of the event (useful for deduplication). |
| 1.0.0   | Initial schema, without `id` or `version`.                                        |

The hash covers the schema version, `instrumentRunId`, `sequenceRunId`, `sampleSheetName`, `apiUrl`
(which carries the OrcaBus id of the sample sheet record), `checksum` and `checksumType`; `timeStamp` and
the free-text `description` are deliberately excluded so re-announcing the same sample sheet yields the
same id (see `app/sequence_run_manager_proc/domain/samplesheet.py`).

### SequenceRunLibraryLinkingChange (SRLLC)

| Version | Change                                                                            |
| ------- | --------------------------------------------------------------------------------- |
| 1.1.0   | Added `version` and `id`, a content hash of the event (useful for deduplication). |
| 1.0.0   | Initial schema, without `id` or `version`.                                        |

The hash covers the schema version, `instrumentRunId`, `sequenceRunId` and `linkedLibraries` as a sorted
set (the order of the libraries does not matter); `timeStamp` is deliberately excluded so re-announcing an
unchanged linking yields the same id (see `app/sequence_run_manager_proc/domain/librarylinking.py`).

### SequenceRunSampleSheetUpdate (SRSSU)

| Version | Change                                                                                                |
| ------- | ----------------------------------------------------------------------------------------------------- |
| 1.0.0   | Initial schema. Replaces the `SequenceRunSampleSheetChange` events previously sent by other services. |

### SequenceRunLibraryLinkingUpdate (SRLLU)

| Version | Change                                                                                                   |
| ------- | -------------------------------------------------------------------------------------------------------- |
| 1.0.0   | Initial schema. Replaces the `SequenceRunLibraryLinkingChange` events previously sent by other services. |

For both `*Update` events, `id` and `version` are optional and owned by the emitting service: `id` should be
a hash of the event data (only changing when the data changes) and `version` the `*Update` schema version
the event was built against. The Sequence Run Manager does not derive anything from them; it stamps its own
`id` and `version` on the `*Change` events it emits.
