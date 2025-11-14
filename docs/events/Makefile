.PHONY: test

install:
	pip install -r requirements.txt

gen-schema:
	@python gen_schema.py SequenceRunStateChange/SequenceRunStateChange.schema.yaml > SequenceRunStateChange/SequenceRunStateChange.schema.json
	@python gen_schema.py SequenceRunSampleSheetChange/SequenceRunSampleSheetChange.schema.yaml > SequenceRunSampleSheetChange/SequenceRunSampleSheetChange.schema.json
	@python gen_schema.py SequenceRunLibraryLinkingChange/SequenceRunLibraryLinkingChange.schema.yaml > SequenceRunLibraryLinkingChange/SequenceRunLibraryLinkingChange.schema.json

json:
	@json validate --schema-file=SequenceRunStateChange/SequenceRunStateChange.schema.json --document-file=SequenceRunStateChange/examples/SRSC__started.json
	@json validate --schema-file=SequenceRunStateChange/SequenceRunStateChange.schema.json --document-file=SequenceRunStateChange/examples/SRSC__succeeded.json
	@json validate --schema-file=SequenceRunSampleSheetChange/SequenceRunSampleSheetChange.schema.json --document-file=SequenceRunSampleSheetChange/examples/SRSSC.json
	@json validate --schema-file=SequenceRunLibraryLinkingChange/SequenceRunLibraryLinkingChange.schema.json --document-file=SequenceRunLibraryLinkingChange/examples/SRLLC.json

test:
	@echo "Testing SequenceRunStateChange"
	@check-jsonschema --schemafile SequenceRunStateChange/SequenceRunStateChange.schema.json SequenceRunStateChange/examples/SRSC__started.json
	@check-jsonschema --schemafile SequenceRunStateChange/SequenceRunStateChange.schema.json SequenceRunStateChange/examples/SRSC__succeeded.json
	@echo "Testing SequenceRunSampleSheetChange"
	@check-jsonschema --schemafile SequenceRunSampleSheetChange/SequenceRunSampleSheetChange.schema.json SequenceRunSampleSheetChange/examples/SRSSC.json
	@echo "Testing SequenceRunLibraryLinkingChange"
	@check-jsonschema --schemafile SequenceRunLibraryLinkingChange/SequenceRunLibraryLinkingChange.schema.json SequenceRunLibraryLinkingChange/examples/SRLLC.json
