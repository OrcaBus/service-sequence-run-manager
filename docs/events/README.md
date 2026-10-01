# Event schemas

This is the location of the events defined by the Workflow Manager.
Each event is contained in its own directory and accompanied by examples.

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
python gen_schema.py <event name>/<event name>.schemal.yaml > <event name>/<event name>.schema.json
# e.g.:
python gen_schema.py SequenceRunStateChange/SequenceRunStateChange.schema.yaml > SequenceRunStateChange/SequenceRunStateChange.schema.json
python gen_schema.py SequenceRunSampleSheetChange/SequenceRunSampleSheetChange.schema.yaml > SequenceRunSampleSheetChange/SequenceRunSampleSheetChange.schema.json
python gen_schema.py SequenceRunLibraryLinkingChange/SequenceRunLibraryLinkingChange.schema.yaml > SequenceRunLibraryLinkingChange/SequenceRunLibraryLinkingChange.schema.json

```


## JSON validation

Example events can be validated against their respective JSON schema

```bash
# Example
# If the file is not valid this should produce an exception (non-zero return code)
json validate --schema-file=ASequenceRunStateChange/SequenceRunStateChange.schema.json --document-file=SequenceRunStateChange/examples/SRSC__started.json
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
