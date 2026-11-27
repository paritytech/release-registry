"""
Unit tests for validate.py and the schema. Run them from the top level dir with:

    just test
"""

import copy
import json
import unittest
from pathlib import Path

import validate

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / 'releases-v1.schema.json').read_text())

REGISTRY = {
    'Polkadot SDK': {
        'recommended': {'release': 'stable2609'},
        'releases': [
            {
                'name': 'stable2609',
                'semver': '1.25.0',
                'cutoff': {'estimated': '2026-08-17'},
                'publish': {'when': '2026-10-12', 'tag': 'polkadot-stable2609'},
                'state': 'released',
                'endOfLife': {'estimated': '2027-10-01'},
                'patches': [
                    {
                        'name': 'stable2609-1',
                        'cutoff': '2026-11-02',
                        'publish': {'when': '2026-11-02', 'tag': 'polkadot-stable2609-1'},
                        'state': 'released',
                        'semver': '1.25.1'
                    }
                ]
            },
            {
                'name': 'stable2701',
                'semver': '1.28.0',
                'cadence': 'monthly',
                'cutoff': {'estimated': '2027-01-25'},
                'publish': {'estimated': '2027-01-28'},
                'state': 'planned',
                'endOfLife': {'estimated': '2027-02-25'}
            }
        ],
        'changelog': 'https://github.com/paritytech/polkadot-sdk/releases/tag/$TAG'
    }
}

class ValidateTest(unittest.TestCase):
    def errors_with(self, change):
        """The validation errors after `change` was applied to the releases of a valid registry."""
        data = copy.deepcopy(REGISTRY)
        change(data['Polkadot SDK']['releases'])
        return validate.find_errors(data, SCHEMA)

    def assert_invalid(self, change, path):
        errors = self.errors_with(change)
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0].startswith(f"$['Polkadot SDK'].releases{path}: "), errors[0])

    def test_valid_registry(self):
        self.assertEqual(validate.find_errors(REGISTRY, SCHEMA), [])

    def test_releases_file_matches_the_schema(self):
        data = json.loads((ROOT / 'releases-v1.json').read_text())
        self.assertEqual(validate.find_errors(data, SCHEMA), [])

    def test_unknown_states_are_rejected(self):
        # States that manage.py used to write, and that consumers of the file do not know
        self.assert_invalid(lambda releases: releases[1].update(state='drafted'), '[1].state')
        self.assert_invalid(lambda releases: releases[0]['patches'][0].update(state='testing'), '[0].patches[0].state')

    def test_dates_are_checked(self):
        self.assert_invalid(lambda releases: releases[1].update(publish={'estimated': '2026-13-45'}), '[1].publish')
        self.assert_invalid(lambda releases: releases[1].update(endOfLife='20270225'), '[1].endOfLife')
        self.assert_invalid(lambda releases: releases[0]['patches'][0].update(cutoff='2026-02-30'), '[0].patches[0].cutoff')

    def test_cadence_and_lts(self):
        self.assertEqual(self.errors_with(lambda releases: releases[1].update(cadence='quarterly', lts=True)), [])
        self.assert_invalid(lambda releases: releases[1].update(cadence='weekly'), '[1].cadence')
        self.assert_invalid(lambda releases: releases[1].update(lts='yes'), '[1].lts')

    def test_release_names(self):
        self.assertEqual(self.errors_with(lambda releases: releases[1].update(name='stable2912')), [])
        self.assert_invalid(lambda releases: releases[1].update(name='stable3001'), '[1].name')
        self.assert_invalid(lambda releases: releases[0]['patches'][0].update(name='stable2609-01'), '[0].patches[0].name')

    def test_semver_must_be_a_string(self):
        self.assert_invalid(lambda releases: releases[1].update(semver=None), '[1].semver')

    def test_unknown_fields_are_rejected(self):
        self.assert_invalid(lambda releases: releases[1].update(crates='2027-01-27'), '[1]')


if __name__ == '__main__':
    unittest.main()
