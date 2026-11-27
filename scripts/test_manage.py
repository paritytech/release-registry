"""
Unit tests for manage.py. Run them from the top level dir with:

    just test

Every test works on its own small registry file in a temporary directory and drives manage.py
through its command line, the same way the Justfile and the workflows do.
"""

import contextlib
import io
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import manage
import validate

SCHEMA = json.loads((Path(__file__).resolve().parent.parent / 'releases-v1.schema.json').read_text())

# The dates the week rule gives: release -> (cutoff Monday, publish Thursday)
RELEASE_WEEKS = {
    'stable2611': ('2026-11-23', '2026-11-26'),
    'stable2612': ('2026-12-21', '2026-12-24'),
    'stable2701': ('2027-01-25', '2027-01-28'),
    'stable2702': ('2027-02-22', '2027-02-25'),
    'stable2703': ('2027-03-22', '2027-03-25'),
    'stable2704': ('2027-04-26', '2027-04-29'),
    'stable2705': ('2027-05-24', '2027-05-27'),
    'stable2706': ('2027-06-21', '2027-06-24'),
    'stable2707': ('2027-07-26', '2027-07-29'),
    'stable2708': ('2027-08-23', '2027-08-26'),
    'stable2709': ('2027-09-20', '2027-09-23'),
    'stable2710': ('2027-10-25', '2027-10-28'),
    'stable2711': ('2027-11-22', '2027-11-25'),
    'stable2712': ('2027-12-27', '2027-12-30'),
    'stable2801': ('2028-01-24', '2028-01-27'),
}

def legacy_registry():
    """A registry as it looks before the first monthly release: two quarterly releases."""
    return {
        'Polkadot SDK': {
            'recommended': {'release': 'stable2609'},
            'releases': [
                {
                    'name': 'stable2606',
                    'semver': '1.24.0',
                    'cutoff': {'estimated': '2026-05-18'},
                    'publish': {'when': '2026-07-06', 'tag': 'polkadot-stable2606'},
                    'state': 'released',
                    'endOfLife': {'estimated': '2027-07-02'},
                    'patches': [
                        {
                            'name': 'stable2606-1',
                            'cutoff': '2026-08-03',
                            'publish': {'when': '2026-08-06', 'tag': 'polkadot-stable2606-1'},
                            'state': 'released',
                            'semver': '1.24.1'
                        },
                        {
                            'name': 'stable2606-2',
                            'cutoff': {'estimated': '2026-12-07'},
                            'publish': {'estimated': '2026-12-10'},
                            'state': 'planned',
                            'semver': '1.24.2'
                        }
                    ]
                },
                {
                    'name': 'stable2609',
                    'semver': '1.25.0',
                    'cutoff': {'estimated': '2026-08-17'},
                    'publish': {'when': '2026-10-12', 'tag': 'polkadot-stable2609'},
                    'state': 'released',
                    'endOfLife': {'estimated': '2027-10-01'}
                }
            ],
            'changelog': 'https://github.com/paritytech/polkadot-sdk/releases/tag/$TAG'
        }
    }

class RegistryTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'releases-v1.json'
        self.path.write_text(json.dumps(legacy_registry(), indent=2))
        # Whatever a test leaves in the file has to match the schema.
        self.addCleanup(self.assert_matches_schema)

    def assert_matches_schema(self):
        self.assertEqual(validate.find_errors(self.data(), SCHEMA), [])

    def cli(self, *arguments):
        """Runs manage.py on the test file and returns what it printed."""
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            manage.main(['--file', str(self.path), *arguments])
        return output.getvalue()

    def assert_rejected(self, *arguments, message):
        """Checks that manage.py fails with `message` and leaves the file as it was."""
        before = self.path.read_bytes()
        output = io.StringIO()
        with self.assertRaises(SystemExit) as failure:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                manage.main(['--file', str(self.path), *arguments])
        self.assertEqual(failure.exception.code, 1)
        self.assertIn(message, output.getvalue())
        self.assertEqual(self.path.read_bytes(), before, "a rejected command must not change the file")

    def data(self):
        return json.loads(self.path.read_text())

    def project(self):
        return self.data()['Polkadot SDK']

    def release(self, name):
        return next(release for release in self.project()['releases'] if release['name'] == name)

    def patch(self, name):
        return next(patch for patch in self.release(name.split('-')[0])['patches'] if patch['name'] == name)

    def edit(self, name, **fields):
        """Changes fields of a release by hand, for states that no command produces."""
        data = self.data()
        release = next(release for release in data['Polkadot SDK']['releases'] if release['name'] == name)
        release.update(fields)
        self.path.write_text(json.dumps(data, indent=2))

    def monthly(self):
        """{name: semver} of the planned monthly releases, in the order of the file."""
        return {release['name']: release['semver'] for release in self.project()['releases']
                if release.get('cadence') == 'monthly' and release['state'] == 'planned'}

    def start_monthly(self, publish=True):
        """Plans stable2611 and the releases after it, and by default publishes stable2611."""
        self.cli('release', 'plan', 'stable2611', '2026-11-23', '1.26.0')
        self.cli('plan-ahead')
        if publish:
            self.cli('release', 'publish', 'stable2611', '2026-11-26')


class WeekRuleTest(unittest.TestCase):
    def test_release_weeks(self):
        for name, (cutoff, publish) in RELEASE_WEEKS.items():
            with self.subTest(name):
                self.assertEqual(manage.release_week(name), (date.fromisoformat(cutoff), date.fromisoformat(publish)))

    def test_cutoff_is_the_last_monday_whose_friday_is_in_the_month(self):
        for year in range(2024, 2031):
            for month in range(1, 13):
                with self.subTest(year=year, month=month):
                    monday = manage.last_full_week_monday(year, month)
                    friday = monday + timedelta(days=4)
                    self.assertEqual(monday.weekday(), 0)
                    self.assertEqual((friday.year, friday.month), (year, month))
                    self.assertNotEqual((friday + timedelta(days=7)).month, month)

    def test_next_release_name(self):
        self.assertEqual(manage.next_release_name('stable2611'), 'stable2612')
        self.assertEqual(manage.next_release_name('stable2612'), 'stable2701')
        self.assertEqual(manage.next_release_name('stable2709'), 'stable2710')

    def test_next_minor(self):
        self.assertEqual(manage.next_minor('1.26.0'), '1.27.0')
        self.assertEqual(manage.next_minor('1.9.3'), '1.10.0')
        self.assertEqual(manage.next_minor('2.0.0'), '2.1.0')


class InputValidationTest(unittest.TestCase):
    def test_version(self):
        for version in ['stable2407', 'stable2611', 'stable2912', 'stable2611-1', 'stable2503-14']:
            with self.subTest(version):
                manage.validate_version(version)

        for version in ['stable2600', 'stable2613', 'stable3001', 'stable2611-', 'stable2611-0', 'stable2611-01',
                        'stable2611-rc1', 'stable2611\n', 'stable26111', 'polkadot-stable2611', '--file']:
            with self.subTest(version):
                with self.assertRaises(ValueError):
                    manage.validate_version(version)

    def test_semver(self):
        manage.validate_semver('1.26.0')
        for semver in ['1.26', '1.26.0-rc1', 'v1.26.0', '1.26.0\n', '1.x.0', '']:
            with self.subTest(semver):
                with self.assertRaises(ValueError):
                    manage.validate_semver(semver)

    def test_date(self):
        self.assertEqual(manage.validate_date('2026-11-23'), '2026-11-23')
        for value in ['2026-13-45', '23.11.2026', '2026-11-31', '']:
            with self.subTest(value):
                with self.assertRaises(ValueError):
                    manage.validate_date(value)


class PlanTest(RegistryTestCase):
    def test_first_monthly_release(self):
        self.cli('release', 'plan', 'stable2611', '2026-11-23', '1.26.0')

        release = self.release('stable2611')
        self.assertEqual(release, {
            'name': 'stable2611',
            'semver': '1.26.0',
            'cadence': 'monthly',
            'cutoff': {'estimated': '2026-11-23'},
            'publish': {'estimated': '2026-11-26'},
            'state': 'planned',
            # Until stable2612 is planned, the end of life is the day the week rule gives it.
            'endOfLife': {'estimated': '2026-12-24'}
        })
        self.assertEqual(list(release), ['name', 'semver', 'cadence', 'cutoff', 'publish', 'state', 'endOfLife'])

    def test_first_monthly_release_needs_a_semver(self):
        self.assert_rejected('release', 'plan', 'stable2611', '2026-11-23',
                             message="stable2611 has no earlier monthly release to take its semver from")

    def test_cutoff_must_be_a_monday(self):
        self.assert_rejected('release', 'plan', 'stable2611', '2026-11-24', '1.26.0',
                             message="must be a Monday, 2026-11-24 is a Tuesday")
        self.start_monthly(publish=False)
        self.assert_rejected('release', 'plan', 'stable2703', '2027-03-23',
                             message="must be a Monday, 2027-03-23 is a Tuesday")

    def test_plan_ahead(self):
        self.start_monthly(publish=False)

        self.assertEqual(self.monthly(), {
            'stable2611': '1.26.0', 'stable2612': '1.27.0', 'stable2701': '1.28.0',
            'stable2702': '1.29.0', 'stable2703': '1.30.0', 'stable2704': '1.31.0',
        })
        for name in self.monthly():
            with self.subTest(name):
                release = self.release(name)
                cutoff, publish = RELEASE_WEEKS[name]
                self.assertEqual(release['cutoff'], {'estimated': cutoff})
                self.assertEqual(release['publish'], {'estimated': publish})
                # Supported until the next monthly release is published
                self.assertEqual(release['endOfLife'], {'estimated': RELEASE_WEEKS[manage.next_release_name(name)][1]})

    def test_plan_ahead_changes_nothing_when_enough_are_planned(self):
        self.start_monthly(publish=False)
        before = self.path.read_bytes()
        self.assertIn("Nothing to plan", self.cli('plan-ahead'))
        self.assertEqual(self.path.read_bytes(), before)

    def test_plan_ahead_count(self):
        self.start_monthly(publish=False)
        self.cli('plan-ahead', '--count', '8')
        self.assertEqual(list(self.monthly())[-2:], ['stable2705', 'stable2706'])
        self.assert_rejected('plan-ahead', '--count', '0', message="--count must be at least 1")
        # Names beyond stable2912 are not valid release names
        self.assert_rejected('plan-ahead', '--count', '50', message="Invalid version format")

    def test_plan_ahead_needs_a_monthly_release(self):
        self.assert_rejected('plan-ahead', message="There is no monthly release to plan ahead from")

    def test_plan_ahead_fills_a_gap(self):
        self.start_monthly(publish=False)
        self.cli('remove', 'stable2702')
        self.assertEqual(len(self.monthly()), 5)
        self.cli('plan-ahead')
        self.assertEqual(list(self.monthly()), ['stable2611', 'stable2612', 'stable2701', 'stable2702', 'stable2703', 'stable2704'])

    def test_moving_a_release_moves_the_end_of_life_before_it(self):
        self.start_monthly(publish=False)
        self.cli('release', 'plan', 'stable2612', '2026-12-14')

        self.assertEqual(self.release('stable2612')['cutoff'], {'estimated': '2026-12-14'})
        self.assertEqual(self.release('stable2612')['publish'], {'estimated': '2026-12-17'})
        self.assertEqual(self.release('stable2612')['semver'], '1.27.0')
        self.assertEqual(self.release('stable2611')['endOfLife'], {'estimated': '2026-12-17'})
        self.assertEqual(self.release('stable2612')['endOfLife'], {'estimated': '2027-01-28'})

    def test_semver_on_plan_must_agree_with_the_derived_one(self):
        self.start_monthly(publish=False)
        self.assert_rejected('release', 'plan', 'stable2703', '2027-03-22', '9.9.9',
                             message="Semver 9.9.9 does not match 1.30.0")
        self.cli('release', 'plan', 'stable2703', '2027-03-22', '1.30.0')
        self.assertEqual(self.release('stable2703')['semver'], '1.30.0')

    def test_semver_of_the_first_monthly_release_can_be_changed(self):
        self.start_monthly(publish=False)
        self.cli('release', 'plan', 'stable2611', '2026-11-23', '1.30.0')
        self.assertEqual(list(self.monthly().values()), ['1.30.0', '1.31.0', '1.32.0', '1.33.0', '1.34.0', '1.35.0'])

    def test_releases_stay_sorted(self):
        self.cli('release', 'plan', 'stable2611', '2026-11-23', '1.26.0')
        self.cli('release', 'plan', 'stable2701', '2027-01-25')
        self.cli('release', 'plan', 'stable2612', '2026-12-21')

        names = [release['name'] for release in self.project()['releases']]
        self.assertEqual(names, ['stable2606', 'stable2609', 'stable2611', 'stable2612', 'stable2701'])
        self.assertEqual(self.monthly(), {'stable2611': '1.26.0', 'stable2612': '1.27.0', 'stable2701': '1.28.0'})

    def test_patch_of_an_unknown_release_is_not_created(self):
        self.assert_rejected('release', 'plan', 'stable2801-1', '2028-01-24',
                             message="Release or patch stable2801-1 not found")

    def test_cadence_option(self):
        self.start_monthly(publish=False)
        self.assert_rejected('release', 'plan', 'stable2612', '2026-12-21', '--cadence', 'quarterly',
                             message="stable2612 exists as a monthly release")
        self.assert_rejected('release', 'plan', 'stable2609', '2026-08-17', '--cadence', 'monthly',
                             message="stable2609 exists as a quarterly release")
        self.assert_rejected('release', 'publish', 'stable2611', '2026-11-26', '--cadence', 'monthly',
                             message="--cadence can only be used when planning a release")
        self.assert_rejected('release', 'plan', 'stable2611-1', '2026-12-01', '--cadence', 'monthly',
                             message="--cadence can only be used when planning a release")


class PublishTest(RegistryTestCase):
    def test_publish_from_planned(self):
        self.start_monthly()

        release = self.release('stable2611')
        self.assertEqual(release['state'], 'released')
        self.assertEqual(release['publish'], {'when': '2026-11-26', 'tag': 'polkadot-stable2611'})
        self.assertEqual(release['cutoff'], {'estimated': '2026-11-23'})
        self.assertEqual(release['endOfLife'], {'estimated': '2026-12-24'})
        # Six releases stay planned
        self.assertEqual(self.monthly(), {
            'stable2612': '1.27.0', 'stable2701': '1.28.0', 'stable2702': '1.29.0',
            'stable2703': '1.30.0', 'stable2704': '1.31.0', 'stable2705': '1.32.0',
        })

    def test_publish_after_cutoff(self):
        self.start_monthly(publish=False)
        self.cli('release', 'cutoff', 'stable2611', '2026-11-23')

        release = self.release('stable2611')
        self.assertEqual(release['state'], 'staging')
        self.assertEqual(release['cutoff'], {'when': '2026-11-23', 'tag': 'polkadot-stable2611-rc1'})
        self.assertEqual(release['semver'], '1.26.0')

        self.cli('release', 'publish', 'stable2611', '2026-11-26')
        self.assertEqual(self.release('stable2611')['state'], 'released')
        self.assertEqual(list(self.monthly()), ['stable2612', 'stable2701', 'stable2702', 'stable2703', 'stable2704', 'stable2705'])

    def test_publish_deprecates_the_previous_monthly_release(self):
        self.start_monthly()
        self.cli('release', 'publish', 'stable2611-1', '2026-12-03')
        self.cli('release', 'plan', 'stable2611-2', '2026-12-28')
        self.cli('release', 'publish', 'stable2612', '2026-12-24')

        deprecated = {'deprecated': {'since': '2026-12-24', 'useInstead': 'stable2612'}}
        self.assertEqual(self.release('stable2611')['state'], deprecated)
        self.assertEqual(self.release('stable2611')['endOfLife'], '2026-12-24')
        self.assertEqual(self.patch('stable2611-1')['state'], deprecated)
        self.assertEqual(self.patch('stable2611-2')['state'], 'skipped')

        self.assertEqual(self.release('stable2612')['state'], 'released')
        self.assertEqual(self.release('stable2612')['endOfLife'], {'estimated': '2027-01-28'})
        self.assertEqual(self.monthly(), {
            'stable2701': '1.28.0', 'stable2702': '1.29.0', 'stable2703': '1.30.0',
            'stable2704': '1.31.0', 'stable2705': '1.32.0', 'stable2706': '1.33.0',
        })

    def test_publish_leaves_quarterly_releases_alone(self):
        self.start_monthly()
        self.cli('release', 'publish', 'stable2612', '2026-12-24')

        self.assertEqual(self.project()['releases'][:2], legacy_registry()['Polkadot SDK']['releases'])
        self.assertEqual(self.project()['recommended'], {'release': 'stable2609'})

    def test_publish_is_refused_while_an_earlier_release_is_not_released(self):
        self.start_monthly(publish=False)
        self.assert_rejected('release', 'publish', 'stable2612', '2026-12-24',
                             message="Cannot publish stable2612: stable2611 is not released yet")

        self.cli('release', 'cutoff', 'stable2611', '2026-11-23')
        self.assert_rejected('release', 'publish', 'stable2612', '2026-12-24',
                             message="Cannot publish stable2612: stable2611 is not released yet")

        self.cli('skip', 'stable2611')
        self.cli('release', 'publish', 'stable2612', '2026-12-24')
        self.assertEqual(self.release('stable2612')['state'], 'released')

    def test_semver_given_on_publish_is_followed_by_the_planned_releases(self):
        self.start_monthly()
        self.cli('release', 'publish', 'stable2612', '2026-12-24', '2.0.0')

        self.assertEqual(self.release('stable2612')['semver'], '2.0.0')
        self.assertEqual(self.release('stable2611')['semver'], '1.26.0')
        self.assertEqual(list(self.monthly().values()), ['2.1.0', '2.2.0', '2.3.0', '2.4.0', '2.5.0', '2.6.0'])

    def test_semver_is_not_accepted_at_cutoff(self):
        self.start_monthly(publish=False)
        self.assert_rejected('release', 'cutoff', 'stable2611', '2026-11-23', '2.0.0',
                             message="A semver cannot be set at cutoff")

    def test_recommended_follows_a_replaced_monthly_release(self):
        self.start_monthly()
        self.cli('release', 'publish', 'stable2611-1', '2026-12-03')
        self.cli('recommend', 'stable2611', '1')
        self.assertEqual(self.project()['recommended'], {'release': 'stable2611', 'patch': '1'})

        self.cli('release', 'publish', 'stable2612', '2026-12-24')
        self.assertEqual(self.project()['recommended'], {'release': 'stable2612'})

    def test_publishing_again_corrects_the_date(self):
        self.start_monthly()
        self.cli('release', 'publish', 'stable2611-1', '2026-12-03')
        self.cli('release', 'publish', 'stable2612', '2026-12-24')
        self.cli('release', 'publish', 'stable2612', '2026-12-23')

        deprecated = {'deprecated': {'since': '2026-12-23', 'useInstead': 'stable2612'}}
        self.assertEqual(self.release('stable2612')['publish'], {'when': '2026-12-23', 'tag': 'polkadot-stable2612'})
        self.assertEqual(self.release('stable2611')['state'], deprecated)
        self.assertEqual(self.release('stable2611')['endOfLife'], '2026-12-23')
        self.assertEqual(self.patch('stable2611-1')['state'], deprecated)
        self.assertEqual(len(self.monthly()), 6)

    def test_publish_keeps_a_deprecation_made_by_hand(self):
        self.start_monthly()
        self.cli('deprecate', 'stable2611', '2026-12-01', 'stable2612')
        self.cli('release', 'publish', 'stable2612', '2026-12-24')

        self.assertEqual(self.release('stable2611')['state'],
                         {'deprecated': {'since': '2026-12-01', 'useInstead': 'stable2612'}})
        self.assertEqual(self.release('stable2611')['endOfLife'], {'estimated': '2026-12-24'})

    def test_lts_release_is_not_deprecated(self):
        self.start_monthly()
        self.edit('stable2611', lts=True, endOfLife={'estimated': '2027-11-26'})
        self.cli('release', 'publish', 'stable2612', '2026-12-24')

        release = self.release('stable2611')
        self.assertEqual(release['state'], 'released')
        self.assertEqual(release['endOfLife'], {'estimated': '2027-11-26'})
        self.assertEqual(list(release), ['name', 'semver', 'cadence', 'lts', 'cutoff', 'publish', 'state', 'endOfLife'])

    def test_actions_that_no_longer_apply_are_refused(self):
        self.start_monthly()
        self.cli('release', 'publish', 'stable2612', '2026-12-24')
        self.cli('skip', 'stable2701')

        # stable2611 is deprecated, stable2612 is released, stable2701 is skipped
        self.assert_rejected('release', 'publish', 'stable2611', '2026-11-27', message="Cannot publish stable2611: its state is 'deprecated'.")
        self.assert_rejected('release', 'plan', 'stable2611', '2026-11-23', message="Cannot plan stable2611: its state is 'deprecated'.")
        self.assert_rejected('release', 'plan', 'stable2612', '2026-12-21', message="Cannot plan stable2612: its state is 'released'.")
        self.assert_rejected('release', 'cutoff', 'stable2612', '2026-12-21', message="Cannot cutoff stable2612: its state is 'released'.")
        self.assert_rejected('skip', 'stable2612', message="Cannot skip stable2612: its state is 'released'.")
        self.assert_rejected('release', 'publish', 'stable2701', '2027-01-28',
                             message="Cannot publish stable2701: its state is 'skipped'. Plan it again first.")
        self.assert_rejected('release', 'cutoff', 'stable2701', '2027-01-25',
                             message="Cannot cutoff stable2701: its state is 'skipped'. Plan it again first.")

    def test_release_that_is_cut_off_cannot_be_planned(self):
        self.start_monthly(publish=False)
        self.cli('release', 'cutoff', 'stable2611', '2026-11-23')
        # Planning would replace the recorded cutoff date and tag with an estimate
        self.assert_rejected('release', 'plan', 'stable2611', '2026-11-30', message="Cannot plan stable2611: its state is 'staging'.")

        # The cutoff date can still be corrected, and the release skipped
        self.cli('release', 'cutoff', 'stable2611', '2026-11-24')
        self.assertEqual(self.release('stable2611')['cutoff'], {'when': '2026-11-24', 'tag': 'polkadot-stable2611-rc1'})
        self.cli('skip', 'stable2611')
        self.assertEqual(self.release('stable2611')['state'], 'skipped')

    def test_release_cannot_be_planned_behind_one_that_is_out(self):
        self.start_monthly()
        self.cli('skip', 'stable2612')
        self.cli('release', 'publish', 'stable2701', '2027-01-28')
        self.assertEqual(self.release('stable2701')['semver'], '1.27.0')

        # stable2612 would get 1.27.0 as well, and could be published after stable2701
        self.assert_rejected('release', 'plan', 'stable2612', '2026-12-14',
                             message="Cannot plan stable2612: the later release stable2701 is already cut off or released.")
        # The same goes for a release that does not exist yet
        self.assert_rejected('release', 'plan', 'stable2610', '2026-10-19', '1.25.0',
                             message="Cannot plan stable2610: the later release stable2611 is already cut off or released.")

    def test_release_cannot_be_planned_behind_one_that_is_cut_off(self):
        self.start_monthly(publish=False)
        self.cli('skip', 'stable2611')
        self.cli('release', 'cutoff', 'stable2612', '2026-12-14')
        self.assert_rejected('release', 'plan', 'stable2611', '2026-11-23',
                             message="Cannot plan stable2611: the later release stable2612 is already cut off or released.")

    def test_planned_release_can_be_moved_while_a_later_one_is_cut_off(self):
        self.start_monthly(publish=False)
        self.cli('release', 'cutoff', 'stable2612', '2026-12-14')
        self.cli('release', 'plan', 'stable2611', '2026-11-30')
        self.assertEqual(self.release('stable2611')['publish'], {'estimated': '2026-12-03'})
        self.assertEqual(self.release('stable2611')['semver'], '1.26.0')
        self.assertEqual(self.release('stable2612')['semver'], '1.27.0')


class SkipTest(RegistryTestCase):
    def test_skipped_release_does_not_use_up_a_version_number(self):
        self.start_monthly()
        self.cli('skip', 'stable2701')

        skipped = self.release('stable2701')
        self.assertEqual(skipped['state'], 'skipped')
        self.assertNotIn('semver', skipped)
        self.assertEqual(self.monthly(), {
            'stable2612': '1.27.0', 'stable2702': '1.28.0', 'stable2703': '1.29.0',
            'stable2704': '1.30.0', 'stable2705': '1.31.0',
        })
        # stable2612 is now supported until stable2702 is published
        self.assertEqual(self.release('stable2612')['endOfLife'], {'estimated': '2027-02-25'})

    def test_plan_ahead_tops_up_after_a_skip(self):
        self.start_monthly()
        self.cli('skip', 'stable2701')
        self.assertIn("Successfully planned stable2706", self.cli('plan-ahead'))
        self.assertEqual(self.release('stable2706')['semver'], '1.32.0')

    def test_skipping_the_first_release_hands_its_semver_to_the_next(self):
        self.start_monthly(publish=False)
        self.cli('skip', 'stable2611')

        self.assertNotIn('semver', self.release('stable2611'))
        self.assertEqual(self.monthly(), {
            'stable2612': '1.26.0', 'stable2701': '1.27.0', 'stable2702': '1.28.0',
            'stable2703': '1.29.0', 'stable2704': '1.30.0',
        })

    def test_skipping_the_last_planned_release(self):
        self.start_monthly()
        self.cli('skip', 'stable2705')
        # No release is planned after stable2704 any more: the week rule gives the date, for stable2706
        self.assertEqual(self.release('stable2704')['endOfLife'], {'estimated': '2027-06-24'})

    def test_skipped_release_can_be_planned_again(self):
        self.start_monthly()
        self.cli('skip', 'stable2701')
        self.cli('release', 'plan', 'stable2701', '2027-01-18')

        self.assertEqual(self.release('stable2701')['state'], 'planned')
        self.assertEqual(self.release('stable2701')['publish'], {'estimated': '2027-01-21'})
        self.assertEqual(self.monthly(), {
            'stable2612': '1.27.0', 'stable2701': '1.28.0', 'stable2702': '1.29.0',
            'stable2703': '1.30.0', 'stable2704': '1.31.0', 'stable2705': '1.32.0',
        })
        self.assertEqual(self.release('stable2612')['endOfLife'], {'estimated': '2027-01-21'})
        self.assertEqual(list(self.release('stable2701')), ['name', 'semver', 'cadence', 'cutoff', 'publish', 'state', 'endOfLife'])

    def test_skipping_twice_changes_nothing(self):
        self.start_monthly()
        self.cli('skip', 'stable2701')
        before = self.path.read_bytes()
        self.cli('skip', 'stable2701')
        self.assertEqual(self.path.read_bytes(), before)


class PatchTest(RegistryTestCase):
    def test_patch_published_right_away(self):
        self.start_monthly()
        self.cli('release', 'publish', 'stable2611-1', '2026-12-03')

        self.assertEqual(self.patch('stable2611-1'), {
            'name': 'stable2611-1',
            'cutoff': '2026-12-03',
            'publish': {'when': '2026-12-03', 'tag': 'polkadot-stable2611-1'},
            'state': 'released',
            'semver': '1.26.1'
        })
        self.assertEqual(list(self.release('stable2611'))[-1], 'patches')

    def test_patch_planned_cut_off_and_published(self):
        self.start_monthly()

        self.cli('release', 'plan', 'stable2611-1', '2026-12-03')
        self.assertEqual(self.patch('stable2611-1'), {
            'name': 'stable2611-1',
            'cutoff': {'estimated': '2026-12-03'},
            'publish': {'estimated': '2026-12-03'},
            'state': 'planned',
            'semver': '1.26.1'
        })

        self.cli('release', 'cutoff', 'stable2611-1', '2026-12-02')
        self.assertEqual(self.patch('stable2611-1')['state'], 'staging')
        self.assertEqual(self.patch('stable2611-1')['cutoff'], '2026-12-02')

        self.cli('release', 'publish', 'stable2611-1', '2026-12-04')
        self.assertEqual(self.patch('stable2611-1')['state'], 'released')
        self.assertEqual(self.patch('stable2611-1')['cutoff'], '2026-12-02')
        self.assertEqual(self.patch('stable2611-1')['publish'], {'when': '2026-12-04', 'tag': 'polkadot-stable2611-1'})

    def test_patch_cut_off_right_away(self):
        self.cli('release', 'cutoff', 'stable2609-1', '2026-11-02')
        self.assertEqual(self.patch('stable2609-1'), {
            'name': 'stable2609-1',
            'cutoff': '2026-11-02',
            'publish': {'estimated': '2026-11-02'},
            'state': 'staging',
            'semver': '1.25.1'
        })

    def test_patch_semver_follows_the_semver_of_its_release(self):
        self.start_monthly()
        self.cli('release', 'plan', 'stable2611-1', '2026-12-03')
        self.cli('release', 'plan', 'stable2612-1', '2027-01-05')
        self.cli('release', 'plan', 'stable2701-1', '2027-02-02')
        self.assertEqual(self.patch('stable2611-1')['semver'], '1.26.1')
        self.assertEqual(self.patch('stable2612-1')['semver'], '1.27.1')

        # The release gets another semver when it is published again: its patch and the planned releases follow
        self.cli('release', 'publish', 'stable2611', '2026-11-26', '2.0.0')
        self.assertEqual(self.patch('stable2611-1')['semver'], '2.0.1')
        self.assertEqual(self.patch('stable2612-1')['semver'], '2.1.1')
        self.cli('release', 'publish', 'stable2611-1', '2026-12-03', '2.0.1')
        self.assertEqual(self.patch('stable2611-1')['semver'], '2.0.1')
        self.assertEqual(list(self.patch('stable2611-1')), ['name', 'cutoff', 'publish', 'state', 'semver'])

        # A skipped release has no semver, and so has its patch
        self.cli('skip', 'stable2701')
        self.assertNotIn('semver', self.patch('stable2701-1'))
        self.cli('release', 'plan', 'stable2701', '2027-01-25')
        self.assertEqual(self.patch('stable2701-1')['semver'], '2.2.1')

    def test_patch_that_is_cut_off_is_skipped_when_its_release_is_deprecated(self):
        self.start_monthly()
        self.cli('release', 'plan', 'stable2611-1', '2026-12-10')
        self.cli('release', 'cutoff', 'stable2611-1', '2026-12-14')
        self.assertEqual(self.patch('stable2611-1')['state'], 'staging')

        self.cli('release', 'publish', 'stable2612', '2026-12-17')
        self.assertEqual(self.patch('stable2611-1')['state'], 'skipped')

    def test_patch_needs_a_release_that_is_out(self):
        self.start_monthly()
        self.assert_rejected('release', 'publish', 'stable2612-1', '2026-12-20',
                             message="Cannot publish stable2612-1: stable2612 is not released, its state is 'planned'.")
        self.assert_rejected('release', 'cutoff', 'stable2612-1', '2026-12-20',
                             message="Cannot cutoff stable2612-1: stable2612 is not released, its state is 'planned'.")

        # A patch can be announced for a planned release, but not be published before it
        self.cli('release', 'plan', 'stable2612-1', '2027-01-05')
        self.assertEqual(self.patch('stable2612-1')['state'], 'planned')
        self.assert_rejected('release', 'publish', 'stable2612-1', '2027-01-05',
                             message="Cannot publish stable2612-1: stable2612 is not released, its state is 'planned'.")

        self.cli('skip', 'stable2701')
        self.assert_rejected('release', 'publish', 'stable2701-1', '2027-02-02',
                             message="Cannot publish stable2701-1: stable2701 is not released, its state is 'skipped'.")

        # A patch of a release that is deprecated by now can still be recorded
        self.cli('release', 'publish', 'stable2612', '2026-12-17')
        self.cli('release', 'publish', 'stable2611-1', '2026-12-18')
        self.assertEqual(self.patch('stable2611-1')['state'], 'released')
        self.cli('release', 'publish', 'stable2612-1', '2027-01-05')
        self.assertEqual(self.patch('stable2612-1')['state'], 'released')

    def test_semver_of_a_patch_must_agree_with_its_release(self):
        self.start_monthly()
        self.assert_rejected('release', 'publish', 'stable2611-1', '2026-12-03', '1.27.1',
                             message="Semver 1.27.1 does not match 1.26.1, which follows from stable2611")
        self.cli('release', 'publish', 'stable2611-1', '2026-12-03', '1.26.1')
        self.assertEqual(self.patch('stable2611-1')['semver'], '1.26.1')


class QuarterlyTest(RegistryTestCase):
    def test_plan(self):
        self.cli('release', 'plan', 'stable2703', '2027-01-04', '1.27.0', '--cadence', 'quarterly')
        self.assertEqual(self.release('stable2703'), {
            'name': 'stable2703',
            'semver': '1.27.0',
            'cutoff': {'estimated': '2027-01-04'},
            # 45 days after the cutoff, and one year of support
            'publish': {'estimated': '2027-02-18'},
            'state': 'planned',
            'endOfLife': {'estimated': '2028-02-18'}
        })

    def test_plan_without_semver_on_a_weekend(self):
        self.cli('release', 'plan', 'stable2703', '2027-01-06', '--cadence', 'quarterly')
        self.assertEqual(self.release('stable2703'), {
            'name': 'stable2703',
            'cutoff': {'estimated': '2027-01-06'},
            # 45 days later is a Saturday, so the Monday after it
            'publish': {'estimated': '2027-02-22'},
            'state': 'planned',
            'endOfLife': {'estimated': '2028-02-22'}
        })

    def test_plan_again(self):
        self.cli('release', 'plan', 'stable2703', '2027-01-04', '1.27.0', '--cadence', 'quarterly')
        self.cli('release', 'plan', 'stable2703', '2027-01-11')

        release = self.release('stable2703')
        self.assertEqual(release['cutoff'], {'estimated': '2027-01-11'})
        self.assertEqual(release['publish'], {'estimated': '2027-02-25'})
        self.assertEqual(release['state'], 'planned')
        # The end of life stays the one of the first plan
        self.assertEqual(release['endOfLife'], {'estimated': '2028-02-18'})
        self.assertNotIn('cadence', release)

    def test_cutoff_and_publish(self):
        self.cli('release', 'plan', 'stable2703', '2027-01-04', '1.27.0', '--cadence', 'quarterly')
        self.cli('release', 'cutoff', 'stable2703', '2027-01-04')
        self.assertEqual(self.release('stable2703')['state'], 'staging')
        self.assertEqual(self.release('stable2703')['cutoff'], {'when': '2027-01-04', 'tag': 'polkadot-stable2703-rc1'})

        self.cli('release', 'publish', 'stable2703', '2027-02-18')
        self.assertEqual(self.release('stable2703')['state'], 'released')
        self.assertEqual(self.release('stable2703')['publish'], {'when': '2027-02-18', 'tag': 'polkadot-stable2703'})
        # A quarterly release is not part of the monthly chain: nothing else changes
        self.assertEqual(self.project()['releases'][:2], legacy_registry()['Polkadot SDK']['releases'])

    def test_release_that_is_out_keeps_its_state(self):
        before = self.release('stable2609')
        self.assert_rejected('release', 'plan', 'stable2609', '2026-12-14', message="Cannot plan stable2609: its state is 'released'.")
        self.assert_rejected('release', 'cutoff', 'stable2609', '2026-08-17', message="Cannot cutoff stable2609: its state is 'released'.")
        self.assert_rejected('skip', 'stable2609', message="Cannot skip stable2609: its state is 'released'.")

        # Publishing it again corrects the date
        self.cli('release', 'publish', 'stable2609', '2026-10-13')
        self.assertEqual(self.release('stable2609'), {**before, 'publish': {'when': '2026-10-13', 'tag': 'polkadot-stable2609'}})

        self.cli('deprecate', 'stable2606', '2027-07-02', 'stable2609')
        self.assert_rejected('release', 'publish', 'stable2606', '2026-07-07', message="Cannot publish stable2606: its state is 'deprecated'.")
        self.assert_rejected('release', 'plan', 'stable2606', '2026-05-18', message="Cannot plan stable2606: its state is 'deprecated'.")
        self.assert_rejected('skip', 'stable2606', message="Cannot skip stable2606: its state is 'deprecated'.")

    def test_backfill(self):
        self.cli('backfill-patches', 'stable2609', '--start-date', '2026-12-14')

        patches = self.release('stable2609')['patches']
        self.assertEqual(len(patches), 13)
        # Cut off on the second Monday of each month and published on the Thursday after it
        self.assertEqual(patches[0], {
            'name': 'stable2609-1',
            'cutoff': {'estimated': '2026-12-14'},
            'publish': {'estimated': '2026-12-17'},
            'state': 'planned',
            'semver': '1.25.1'
        })
        self.assertEqual(patches[1]['cutoff'], {'estimated': '2027-01-11'})
        self.assertEqual(patches[12], {
            'name': 'stable2609-13',
            'cutoff': {'estimated': '2027-12-13'},
            'publish': {'estimated': '2027-12-16'},
            'state': 'planned',
            'semver': '1.25.13'
        })

    def test_backfill_needs_a_monday(self):
        self.assert_rejected('backfill-patches', 'stable2609', '--start-date', '2026-12-15',
                             message="Start date must be a Monday")

    def test_backfill_is_not_for_monthly_releases(self):
        self.start_monthly()
        self.assert_rejected('backfill-patches', 'stable2611', '--start-date', '2026-12-14',
                             message="stable2611 is a monthly release and has no patch schedule")

        # Without a release name, the quarterly releases are backfilled and the monthly ones left alone
        self.cli('backfill-patches', '--start-date', '2026-12-14')
        self.assertEqual(len(self.release('stable2609')['patches']), 13)
        self.assertNotIn('patches', self.release('stable2611'))
        self.assertNotIn('patches', self.release('stable2612'))

    def test_deprecate(self):
        self.cli('deprecate', 'stable2606', '2027-07-02', 'stable2609')
        deprecated = {'deprecated': {'since': '2027-07-02', 'useInstead': 'stable2609'}}
        self.assertEqual(self.release('stable2606')['state'], deprecated)
        self.assertEqual(self.patch('stable2606-1')['state'], deprecated)
        self.assertEqual(self.patch('stable2606-2')['state'], 'skipped')
        self.assertEqual(self.release('stable2606')['endOfLife'], {'estimated': '2027-07-02'})

    def test_deprecate_skips_a_patch_that_is_cut_off(self):
        self.cli('release', 'cutoff', 'stable2606-2', '2026-12-07')
        self.cli('deprecate', 'stable2606', '2027-07-02', 'stable2609')
        self.assertEqual(self.patch('stable2606-2')['state'], 'skipped')

    def test_deprecate_a_release_without_patches(self):
        self.cli('deprecate', 'stable2609', '2027-10-01', 'stable2611')
        self.assertEqual(self.release('stable2609')['state'],
                         {'deprecated': {'since': '2027-10-01', 'useInstead': 'stable2611'}})

    def test_skip(self):
        self.cli('skip', 'stable2606-2')
        self.assertEqual(self.patch('stable2606-2')['state'], 'skipped')

        self.cli('release', 'plan', 'stable2703', '2027-01-04', '1.27.0', '--cadence', 'quarterly')
        self.cli('skip', 'stable2703')
        self.assertEqual(self.release('stable2703')['state'], 'skipped')
        self.assertEqual(self.release('stable2703')['semver'], '1.27.0')

    def test_remove_patches(self):
        self.cli('remove-patches', 'stable2606')
        self.assertEqual([patch['name'] for patch in self.release('stable2606')['patches']], ['stable2606-1'])

        # A release without patches is left as it is
        before = self.path.read_bytes()
        self.assertIn("No planned patches found for stable2609", self.cli('remove-patches', 'stable2609'))
        self.assertEqual(self.path.read_bytes(), before)

    def test_remove(self):
        self.cli('remove', 'stable2609')
        self.assertEqual([release['name'] for release in self.project()['releases']], ['stable2606'])

    def test_saving_keeps_the_format_of_the_file(self):
        # stable2609 has no planned patches, so this saves the file without changing the data
        self.edit('stable2609', patches=[])
        before = self.path.read_bytes()
        self.cli('remove-patches', 'stable2609')
        self.assertEqual(self.path.read_bytes(), before)


class WrongNameTest(RegistryTestCase):
    def test_unknown_release_or_patch_is_an_error(self):
        for arguments, message in [
            (['release', 'publish', 'stable2710', '2027-10-28'], "Release or patch stable2710 not found"),
            (['release', 'cutoff', 'stable2710', '2027-10-25'], "Release or patch stable2710 not found"),
            (['release', 'publish', 'stable2710-1', '2027-11-04'], "Release or patch stable2710-1 not found"),
            (['skip', 'stable2710'], "Release or patch stable2710 not found"),
            (['skip', 'stable2606-9'], "Release or patch stable2606-9 not found"),
            (['deprecate', 'stable2710', '2027-11-25', 'stable2711'], "Release stable2710 not found"),
            (['recommend', 'stable2710'], "Release stable2710 not found"),
            (['remove', 'stable2710'], "Release stable2710 not found"),
            (['remove-patches', 'stable2710'], "Release stable2710 not found"),
            (['backfill-patches', 'stable2710', '--start-date', '2027-11-01'], "Failed to backfill patches for stable2710"),
        ]:
            with self.subTest(' '.join(arguments)):
                self.assert_rejected(*arguments, message=message)

    def test_commands_for_a_release_do_not_take_a_patch(self):
        # They would act on all of stable2606
        for arguments in [
            ['remove', 'stable2606-1'],
            ['remove-patches', 'stable2606-1'],
            ['deprecate', 'stable2606-1', '2027-07-02', 'stable2609'],
        ]:
            with self.subTest(' '.join(arguments)):
                self.assert_rejected(*arguments, message="Expected a release, but stable2606-1 is a patch")


class RecommendTest(RegistryTestCase):
    def test_recommend(self):
        self.cli('recommend', 'stable2606')
        self.assertEqual(self.project()['recommended'], {'release': 'stable2606'})

        self.cli('recommend', 'stable2606', '1')
        self.assertEqual(self.project()['recommended'], {'release': 'stable2606', 'patch': '1'})

        self.cli('recommend', 'stable2609')
        self.assertEqual(self.project()['recommended'], {'release': 'stable2609'})

    def test_only_what_is_released_can_be_recommended(self):
        self.start_monthly()
        self.assert_rejected('recommend', 'stable2612', message="stable2612 is not a released release")
        self.assert_rejected('recommend', 'stable2606', '2', message="stable2606-2 is not a released patch")
        self.assert_rejected('recommend', 'stable2606', '7', message="stable2606-7 is not a released patch")
        self.assert_rejected('recommend', 'stable2606-1', message="Pass the patch number on its own")
        self.assert_rejected('recommend', 'stable2606', '01', message="Invalid patch number")


if __name__ == '__main__':
    unittest.main()
