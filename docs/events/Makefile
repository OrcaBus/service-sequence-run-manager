.PHONY: test

install:
	pip install -r requirements.txt

gen-schema:
	@python gen_schema.py SequenceRunStateChange/SequenceRunStateChange.schema.yaml > SequenceRunStateChange/SequenceRunStateChange.schema.json
	@python gen_schema.py SequenceRunSampleSheetChange/SequenceRunSampleSheetChange.schema.yaml > SequenceRunSampleSheetChange/SequenceRunSampleSheetChange.schema.json
	@python gen_schema.py SequenceRunSampleSheetUpdate/SequenceRunSampleSheetUpdate.schema.yaml > SequenceRunSampleSheetUpdate/SequenceRunSampleSheetUpdate.schema.json
	@python gen_schema.py SequenceRunLibraryLinkingChange/SequenceRunLibraryLinkingChange.schema.yaml > SequenceRunLibraryLinkingChange/SequenceRunLibraryLinkingChange.schema.json
	@python gen_schema.py SequenceRunLibraryLinkingUpdate/SequenceRunLibraryLinkingUpdate.schema.yaml > SequenceRunLibraryLinkingUpdate/SequenceRunLibraryLinkingUpdate.schema.json

json:
	@json validate --schema-file=SequenceRunStateChange/SequenceRunStateChange.schema.json --document-file=SequenceRunStateChange/examples/SRSC__started.json
	@json validate --schema-file=SequenceRunStateChange/SequenceRunStateChange.schema.json --document-file=SequenceRunStateChange/examples/SRSC__succeeded.json
	@json validate --schema-file=SequenceRunStateChange/SequenceRunStateChange.schema.json --document-file=SequenceRunStateChange/examples/SRSC__resolved.json
	@json validate --schema-file=SequenceRunStateChange/SequenceRunStateChange.schema.json --document-file=SequenceRunStateChange/examples/SRSC__started__null.json
	@json validate --schema-file=SequenceRunSampleSheetChange/SequenceRunSampleSheetChange.schema.json --document-file=SequenceRunSampleSheetChange/examples/SRSSC.json
	@json validate --schema-file=SequenceRunSampleSheetUpdate/SequenceRunSampleSheetUpdate.schema.json --document-file=SequenceRunSampleSheetUpdate/examples/SRSSU.json
	@json validate --schema-file=SequenceRunSampleSheetUpdate/SequenceRunSampleSheetUpdate.schema.json --document-file=SequenceRunSampleSheetUpdate/examples/SRSSU__new_sequence_run.json
	@json validate --schema-file=SequenceRunLibraryLinkingChange/SequenceRunLibraryLinkingChange.schema.json --document-file=SequenceRunLibraryLinkingChange/examples/SRLLC.json
	@json validate --schema-file=SequenceRunLibraryLinkingUpdate/SequenceRunLibraryLinkingUpdate.schema.json --document-file=SequenceRunLibraryLinkingUpdate/examples/SRLLU.json

test:
	@echo "Testing SequenceRunStateChange"
	@check-jsonschema --schemafile SequenceRunStateChange/SequenceRunStateChange.schema.json SequenceRunStateChange/examples/SRSC__started.json
	@check-jsonschema --schemafile SequenceRunStateChange/SequenceRunStateChange.schema.json SequenceRunStateChange/examples/SRSC__succeeded.json
	@check-jsonschema --schemafile SequenceRunStateChange/SequenceRunStateChange.schema.json SequenceRunStateChange/examples/SRSC__resolved.json
	@check-jsonschema --schemafile SequenceRunStateChange/SequenceRunStateChange.schema.json SequenceRunStateChange/examples/SRSC__started__null.json
	@echo "Testing SequenceRunSampleSheetChange"
	@check-jsonschema --schemafile SequenceRunSampleSheetChange/SequenceRunSampleSheetChange.schema.json SequenceRunSampleSheetChange/examples/SRSSC.json
	@echo "Testing SequenceRunSampleSheetUpdate"
	@check-jsonschema --schemafile SequenceRunSampleSheetUpdate/SequenceRunSampleSheetUpdate.schema.json SequenceRunSampleSheetUpdate/examples/SRSSU.json
	@check-jsonschema --schemafile SequenceRunSampleSheetUpdate/SequenceRunSampleSheetUpdate.schema.json SequenceRunSampleSheetUpdate/examples/SRSSU__new_sequence_run.json
	@echo "Testing SequenceRunLibraryLinkingChange"
	@check-jsonschema --schemafile SequenceRunLibraryLinkingChange/SequenceRunLibraryLinkingChange.schema.json SequenceRunLibraryLinkingChange/examples/SRLLC.json
	@echo "Testing SequenceRunLibraryLinkingUpdate"
	@check-jsonschema --schemafile SequenceRunLibraryLinkingUpdate/SequenceRunLibraryLinkingUpdate.schema.json SequenceRunLibraryLinkingUpdate/examples/SRLLU.json

help:
	@echo "Usage: make <target>"
	@echo "Targets:"
	@echo "  install - Install dependencies"
	@echo "  gen-schema - Generate schema files"
	@echo "  json - Validate JSON examples"
	@echo "  test - Validate JSON examples against schema"
