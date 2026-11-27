"""
Unit tests for update-gantt.py. Run them from the top level dir with:

    just test

They check what goes into the chart and that the chart can be drawn. How it looks has to be
checked by eye: open .assets/timeline-gantt.png after `just gantt`.
"""

import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use('Agg')  # draw without a display

# The file name has a hyphen, so it cannot be imported by name.
spec = importlib.util.spec_from_file_location('update_gantt', Path(__file__).with_name('update-gantt.py'))
gantt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gantt)

DEPRECATED = {'deprecated': {'since': '2026-12-17', 'useInstead': 'stable2612'}}

QUARTERLY_RELEASES = [
    {
        'name': 'stable2506',
        'cutoff': {'estimated': '2025-05-15'},
        'publish': {'when': '2025-07-24', 'tag': 'polkadot-stable2506'},
        'state': {'deprecated': {'since': '2026-06-10', 'useInstead': 'stable2603'}},
        'endOfLife': {'estimated': '2026-06-30'}
    },
    {
        'name': 'stable2609',
        'cutoff': {'estimated': '2026-08-17'},
        'publish': {'when': '2026-10-12', 'tag': 'polkadot-stable2609'},
        'state': 'released',
        'endOfLife': {'estimated': '2027-10-01'},
        'patches': [
            {'name': 'stable2609-1', 'cutoff': '2026-11-02', 'publish': {'when': '2026-11-02', 'tag': 'polkadot-stable2609-1'}, 'state': 'released'},
            {'name': 'stable2609-2', 'cutoff': {'estimated': '2027-01-11'}, 'publish': {'estimated': '2027-01-14'}, 'state': 'planned'},
            {'name': 'stable2609-3', 'cutoff': {'estimated': '2027-02-08'}, 'publish': {'estimated': '2027-02-11'}, 'state': 'skipped'}
        ]
    },
    {
        'name': 'stable2612',
        'cutoff': {'estimated': '2026-11-09'},
        'publish': {'estimated': '2026-12-17'},
        'state': 'skipped',
        'endOfLife': {'estimated': '2027-12-17'}
    }
]

MONTHLY_RELEASES = [
    {
        'name': 'stable2611',
        'cadence': 'monthly',
        'cutoff': {'estimated': '2026-11-23'},
        'publish': {'when': '2026-11-26', 'tag': 'polkadot-stable2611'},
        'state': DEPRECATED,
        'endOfLife': '2026-12-17',
        'patches': [
            {'name': 'stable2611-1', 'cutoff': '2026-12-03', 'publish': {'when': '2026-12-03', 'tag': 'polkadot-stable2611-1'}, 'state': DEPRECATED}
        ]
    },
    {
        'name': 'stable2612',
        'cadence': 'monthly',
        'cutoff': {'estimated': '2026-12-14'},
        'publish': {'when': '2026-12-17', 'tag': 'polkadot-stable2612'},
        'state': 'released',
        'endOfLife': {'estimated': '2027-02-25'},
        'patches': [
            {'name': 'stable2612-1', 'cutoff': {'estimated': '2027-01-05'}, 'publish': {'estimated': '2027-01-05'}, 'state': 'planned'},
            {'name': 'stable2612-2', 'cutoff': {'estimated': '2027-01-19'}, 'publish': {'estimated': '2027-01-19'}, 'state': 'skipped'}
        ]
    },
    {
        'name': 'stable2701',
        'cadence': 'monthly',
        'cutoff': {'estimated': '2027-01-25'},
        'publish': {'estimated': '2027-01-28'},
        'state': 'skipped',
        'endOfLife': {'estimated': '2027-02-25'},
        'patches': [
            {'name': 'stable2701-1', 'cutoff': {'estimated': '2027-02-02'}, 'publish': {'estimated': '2027-02-02'}, 'state': 'planned'}
        ]
    },
    {
        'name': 'stable2702',
        'cadence': 'monthly',
        'cutoff': {'estimated': '2027-02-22'},
        'publish': {'estimated': '2027-02-25'},
        'state': 'planned',
        'endOfLife': {'estimated': '2027-03-25'}
    }
]

def registry(*releases):
    return {'Polkadot SDK': {'releases': list(releases)}}

def day(text):
    return datetime.fromisoformat(text)

class QuarterlyPanelTest(unittest.TestCase):
    def test_rows(self):
        tasks = gantt.process_releases(registry(*QUARTERLY_RELEASES, *MONTHLY_RELEASES))

        # One row for the supported release and each of its patches. The deprecated and the skipped
        # release are left out, and so are the monthly releases.
        self.assertEqual([task['name'] for task in tasks], ['stable2609', '1', '2', '3'])
        self.assertEqual([task['color'] for task in tasks], [
            gantt.COLOR_RELEASED_BAR, gantt.COLOR_RELEASED_PATCH, gantt.COLOR_PLANNED_PATCH, gantt.COLOR_SKIPPED_PATCH,
        ])
        self.assertEqual((tasks[0]['start'], tasks[0]['end']), (day('2026-10-12'), day('2027-10-01')))
        # A patch is drawn one week wide
        self.assertEqual((tasks[1]['start'], tasks[1]['end']), (day('2026-11-02'), day('2026-11-09')))

class MonthlyPanelTest(unittest.TestCase):
    def setUp(self):
        self.segments, self.markers = gantt.process_monthly_releases(registry(*QUARTERLY_RELEASES, *MONTHLY_RELEASES))

    def test_segments(self):
        # The skipped stable2701 is left out, and the quarterly releases are not part of this panel
        self.assertEqual([segment['name'] for segment in self.segments], ['2611', '2612', '2702'])
        self.assertEqual([segment['color'] for segment in self.segments],
                         [gantt.COLOR_RELEASED_BAR, gantt.COLOR_RELEASED_BAR, gantt.COLOR_PLANNED_BAR])
        self.assertEqual([segment['past'] for segment in self.segments], [True, False, False])
        # From the day a release is published until the next one replaces it
        self.assertEqual([(segment['start'], segment['end']) for segment in self.segments], [
            (day('2026-11-26'), day('2026-12-17')),
            (day('2026-12-17'), day('2027-02-25')),
            (day('2027-02-25'), day('2027-03-25')),
        ])

    def test_patch_markers(self):
        # The patch of the skipped stable2701 is left out
        self.assertEqual([marker['start'] for marker in self.markers],
                         [day('2026-12-03'), day('2027-01-05'), day('2027-01-19')])
        self.assertEqual([marker['color'] for marker in self.markers],
                         [gantt.COLOR_RELEASED_PATCH, gantt.COLOR_PLANNED_PATCH, gantt.COLOR_SKIPPED_PATCH])
        self.assertEqual([marker['past'] for marker in self.markers], [True, False, False])

    def test_deprecated_release_shows_inside_the_time_of_the_chart(self):
        tasks = gantt.process_releases(registry(*QUARTERLY_RELEASES))
        segments, markers = gantt.limit_to_time_window(tasks, self.segments, self.markers)
        # stable2609 was published before stable2611, so all of stable2611 is inside
        self.assertEqual(segments, self.segments)
        self.assertEqual(markers, self.markers)

    def test_deprecated_release_is_cut_at_the_start_of_the_chart(self):
        tasks = [{'name': 'stable2703', 'start': day('2026-12-01'), 'end': day('2027-12-01'), 'color': gantt.COLOR_PLANNED_BAR}]
        segments, markers = gantt.limit_to_time_window(tasks, self.segments, self.markers)
        self.assertEqual([(segment['name'], segment['start']) for segment in segments],
                         [('2611', day('2026-12-01')), ('2612', day('2026-12-17')), ('2702', day('2027-02-25'))])
        self.assertEqual(len(markers), 3)

    def test_deprecated_release_before_the_chart_is_left_out(self):
        # Without quarterly releases the chart starts when stable2612 is published
        segments, markers = gantt.limit_to_time_window([], self.segments, self.markers)
        self.assertEqual([segment['name'] for segment in segments], ['2612', '2702'])
        self.assertEqual([marker['start'] for marker in markers], [day('2027-01-05'), day('2027-01-19')])

class DrawTest(unittest.TestCase):
    def draw(self, *releases):
        data = registry(*releases)
        tasks = gantt.process_releases(data)
        segments, markers = gantt.limit_to_time_window(tasks, *gantt.process_monthly_releases(data))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'chart.png'
            gantt.create_gantt_chart(tasks, segments, markers, str(output), dpi=50)
            self.assertGreater(output.stat().st_size, 0)

    def test_both_panels(self):
        self.draw(*QUARTERLY_RELEASES, *MONTHLY_RELEASES)

    def test_monthly_releases_only(self):
        self.draw(*MONTHLY_RELEASES)

    def test_monthly_releases_without_patches(self):
        self.draw(MONTHLY_RELEASES[3])

    def test_quarterly_releases_only(self):
        self.draw(*QUARTERLY_RELEASES)

    def test_nothing_to_show(self):
        self.draw()


if __name__ == '__main__':
    unittest.main()
