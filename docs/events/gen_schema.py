import yaml
import json
import argparse
from pathlib import Path

from genson import SchemaBuilder


def to_jsonschema(filename):
    builder = SchemaBuilder()
    with Path(filename).open() as fd:
        data = yaml.safe_load(fd)
        builder.add_schema(data)
    return builder.to_schema()


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter)
    arg_parser.add_argument('filename')
    args = arg_parser.parse_args()

    schema = to_jsonschema(args.filename)
    print(json.dumps(schema, indent=2))
