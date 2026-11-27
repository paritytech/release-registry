"""
Checks releases-v1.json against releases-v1.schema.json. Just run it in the top level dir in its
stock configuration:

    python scripts/validate.py

It exits with a non-zero status and lists the problems if the file does not match the schema.
"""

import argparse
import json
import sys

from jsonschema import Draft202012Validator
from jsonschema.validators import validator_for

def position(error):
    """Sort key that puts the errors in the order of the file. A path mixes keys and list indices."""
    return [(isinstance(part, str), part) for part in error.absolute_path]

def find_errors(data, schema):
    """Returns one message for each place where `data` does not match `schema`."""
    # The schema does not name its dialect in `$schema`, in which case the newest draft applies.
    validator_class = validator_for(schema, default=Draft202012Validator)
    validator_class.check_schema(schema)
    # Without a format checker `"format": "date"` is not enforced and 2026-13-45 would pass.
    validator = validator_class(schema, format_checker=validator_class.FORMAT_CHECKER)

    messages = []
    for error in sorted(validator.iter_errors(data), key=position):
        message = f"{error.json_path}: {error.message}"
        # A `oneOf` only reports that no alternative matched; add why each of them did not.
        if error.context:
            message += f" ({'; '.join(cause.message for cause in error.context)})"
        messages.append(message)
    return messages

def main():
    parser = argparse.ArgumentParser(description="Check the releases file against its JSON schema")
    parser.add_argument('--file', default='releases-v1.json', help="Path to the JSON file")
    parser.add_argument('--schema', default='releases-v1.schema.json', help="Path to the JSON schema")
    args = parser.parse_args()

    with open(args.file, 'r') as f:
        data = json.load(f)
    with open(args.schema, 'r') as f:
        schema = json.load(f)

    errors = find_errors(data, schema)
    if errors:
        print(f"Error: '{args.file}' does not match '{args.schema}':", file=sys.stderr)
        for message in errors:
            print(f"  {message}", file=sys.stderr)
        sys.exit(1)

    print(f"{args.file} matches {args.schema}.")

if __name__ == "__main__":
    main()
