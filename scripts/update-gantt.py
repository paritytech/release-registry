import json
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from datetime import datetime, timedelta
import argparse
import sys
from typing import List, Dict, Any

from registry import is_monthly

def parse_date(date_info: Any) -> datetime:
	if isinstance(date_info, str):
		return datetime.fromisoformat(date_info)
	elif isinstance(date_info, dict):
		date_str = date_info.get('when') or date_info.get('estimated')
		return datetime.fromisoformat(date_str) if date_str else None
	return None

COLOR_RELEASED_BAR = '#E6007A'  # released version
COLOR_RELEASED_PATCH = '#E6007A' # released patch
COLOR_PLANNED_BAR = '#a3a3a3'   # planned version
COLOR_PLANNED_PATCH = '#a3a3a3'  # planned patch
COLOR_SKIPPED_PATCH = '#c7c7c7'  # skipped patch
COLOR_CURRENT_DATE = '#FF0000'  # current date line
COLOR_TEXT = '#191919'          # text on the background and on the planned bars
COLOR_TEXT_ON_RELEASED = '#FFFFFF' # text on the released bars
BAR_ALPHA = 0.8

# Height of the parts of the chart in inches. The panel of the quarterly releases has one row
# for each release and each patch, so it shrinks as these releases reach their end of life.
FIGURE_WIDTH = 15
MONTHLY_BAND_HEIGHT = 0.6
MONTHLY_PATCH_LANE_HEIGHT = 0.4
MONTHLY_LABEL_FONT_SIZES = [11, 10, 9, 8]
MONTHLY_LABEL_PADDING = 10  # pixels that have to stay free in a segment, next to its label
QUARTERLY_ROW_HEIGHT = 0.12
QUARTERLY_MIN_HEIGHT = 2

def is_deprecated(item: Dict) -> bool:
	return isinstance(item['state'], dict) and 'deprecated' in item['state']

def process_releases(data: Dict) -> List[Dict]:
	"""The rows of the quarterly panel: every supported quarterly release, followed by its patches."""
	tasks = []

	sdk_data = data.get("Polkadot SDK", {})
	releases = sdk_data.get("releases", [])

	for release in releases:
		if is_monthly(release):
			continue
		if is_deprecated(release) or release['state'] == 'skipped':
			continue

		name = release['name']
		start_date = parse_date(release['publish'])
		end_date = parse_date(release['endOfLife'])

		if not (start_date and end_date):
			continue

		tasks.append({
			'name': name,
			'start': start_date,
			'end': end_date,
			'color': COLOR_RELEASED_BAR if release['state'] == 'released' else COLOR_PLANNED_BAR
		})

		for patch in release.get('patches', []):
			patch_date = parse_date(patch['publish'])
			if not patch_date:
				continue

			patch_end = patch_date + timedelta(days=7)

			is_planned = (isinstance(patch['publish'], dict) and 'estimated' in patch['publish']) or (isinstance(patch['state'], dict) and 'deprecated' in patch['state'])
			is_skipped = patch['state'] == 'skipped'
			color = COLOR_SKIPPED_PATCH if is_skipped else (COLOR_PLANNED_PATCH if is_planned else COLOR_RELEASED_PATCH)

			tasks.append({
				'name': patch['name'].split('-')[1],
				'start': patch_date,
				'end': patch_end,
				'color': color
			})

	return tasks

def process_monthly_releases(data: Dict) -> tuple[List[Dict], List[Dict]]:
	"""
	The monthly panel: one segment for each monthly release, from the day it is published until
	the next one replaces it, and one marker for each of their patches. Skipped releases are left
	out. `past` marks what belongs to a release that is deprecated.
	"""
	segments = []
	markers = []

	sdk_data = data.get("Polkadot SDK", {})
	releases = sdk_data.get("releases", [])

	for release in releases:
		if not is_monthly(release) or release['state'] == 'skipped':
			continue

		start_date = parse_date(release['publish'])
		end_date = parse_date(release['endOfLife'])

		if not (start_date and end_date):
			continue

		past = is_deprecated(release)
		is_released = past or release['state'] == 'released'

		segments.append({
			'name': release['name'].replace('stable', ''),
			'start': start_date,
			'end': end_date,
			'color': COLOR_RELEASED_BAR if is_released else COLOR_PLANNED_BAR,
			'past': past
		})

		for patch in release.get('patches', []):
			patch_date = parse_date(patch['publish'])
			if not patch_date:
				continue

			if patch['state'] == 'skipped':
				color = COLOR_SKIPPED_PATCH
			elif patch['state'] == 'released' or is_deprecated(patch):
				color = COLOR_RELEASED_PATCH
			else:
				color = COLOR_PLANNED_PATCH

			markers.append({
				'start': patch_date,
				'end': patch_date + timedelta(days=7),
				'color': color,
				'past': past
			})

	return segments, markers

def limit_to_time_window(tasks: List[Dict], segments: List[Dict], markers: List[Dict]) -> tuple[List[Dict], List[Dict]]:
	"""
	The chart spans the releases that are supported or planned. Deprecated monthly releases only
	show as far as they reach into that time, so the chart does not grow with every release.
	"""
	current = tasks + [item for item in segments + markers if not item['past']]
	if not current:
		return segments, markers

	window_start = min(item['start'] for item in current)

	visible_segments = []
	for segment in segments:
		if not segment['past']:
			visible_segments.append(segment)
		elif segment['end'] > window_start:
			visible_segments.append({**segment, 'start': max(segment['start'], window_start)})

	visible_markers = [marker for marker in markers if not marker['past'] or marker['start'] >= window_start]
	return visible_segments, visible_markers

def draw_monthly_panel(ax, segments: List[Dict], markers: List[Dict]) -> List:
	"""Draws the monthly releases as one row. Returns the labels of the segments, to check that they fit."""
	band_y, lane_y = 1, 0
	labels = []

	for segment in segments:
		# The white edge separates segments that touch
		ax.barh(band_y,
				(segment['end'] - segment['start']).days,
				left=segment['start'],
				height=0.8,
				color=segment['color'],
				alpha=BAR_ALPHA,
				edgecolor='white',
				linewidth=2)
		center = segment['start'] + (segment['end'] - segment['start']) / 2
		label = ax.text(center, band_y, segment['name'],
				ha='center', va='center', fontsize=MONTHLY_LABEL_FONT_SIZES[0], fontweight='bold',
				color=COLOR_TEXT_ON_RELEASED if segment['color'] == COLOR_RELEASED_BAR else COLOR_TEXT)
		label.set_in_layout(False)
		labels.append((label, segment))

	# The patches are not labelled, as in the panel of the quarterly releases: a patch sits below
	# the release it belongs to.
	for marker in markers:
		ax.barh(lane_y,
				(marker['end'] - marker['start']).days,
				left=marker['start'],
				height=0.5,
				color=marker['color'],
				alpha=BAR_ALPHA)

	if markers:
		ax.set_ylim(lane_y - 0.6, band_y + 0.6)
		ax.set_yticks([lane_y, band_y])
		ax.set_yticklabels(['patches', 'releases'], fontsize=10)
	else:
		ax.set_ylim(band_y - 0.6, band_y + 0.6)
		ax.set_yticks([])

	ax.grid(True, axis='x', alpha=0.3)
	ax.set_title('Monthly releases', loc='left', fontsize=12)
	return labels

def fit_labels(fig, ax, labels: List) -> None:
	"""
	A label that is wider than its segment would run into the segments next to it. Each label gets
	the largest font size at which it fits, and is left out if it is too wide even at the smallest.
	"""
	fig.canvas.draw()  # the positions are only known once the chart is laid out
	renderer = fig.canvas.get_renderer()

	for label, segment in labels:
		left = ax.transData.transform((mdates.date2num(segment['start']), 0))[0]
		right = ax.transData.transform((mdates.date2num(segment['end']), 0))[0]

		for fontsize in MONTHLY_LABEL_FONT_SIZES:
			label.set_fontsize(fontsize)
			if label.get_window_extent(renderer).width + MONTHLY_LABEL_PADDING <= right - left:
				break
		else:
			label.set_visible(False)

def draw_quarterly_panel(ax, tasks: List[Dict]) -> None:
	# Plot bars
	for idx, task in enumerate(tasks):
		ax.barh(idx,
				(task['end'] - task['start']).days,
				left=task['start'],
				color=task['color'],
				alpha=BAR_ALPHA)

	# Customize axis
	ax.set_ylim(-0.5, len(tasks) - 0.5)
	ax.set_yticks(range(len(tasks)))
	ax.set_yticklabels(['stable\n'+t['name'].replace('stable', '') if 'stable' in t['name'] else '' for t in tasks], fontsize=15)

	ax.grid(True, axis='x', alpha=0.3)
	ax.set_title('Quarterly releases (legacy)', loc='left', fontsize=12)

def create_gantt_chart(tasks: List[Dict], segments: List[Dict], markers: List[Dict], output: str, dpi: int = 300):
	# One panel for the monthly releases and one for the quarterly ones, on the same time axis.
	# A panel without anything to show is left out.
	heights = []
	if segments:
		heights.append(MONTHLY_BAND_HEIGHT + (MONTHLY_PATCH_LANE_HEIGHT if markers else 0))
	if tasks or not segments:
		heights.append(max(len(tasks) * QUARTERLY_ROW_HEIGHT, QUARTERLY_MIN_HEIGHT))

	# 1.6 inches are for the title, the legend and the dates below the chart
	fig, axes = plt.subplots(len(heights), 1,
			figsize=(FIGURE_WIDTH, sum(heights) + 1.6),
			sharex=True, squeeze=False,
			gridspec_kw={'height_ratios': heights},
			layout='constrained')
	axes = list(axes[:, 0])

	labels = []
	if segments:
		labels = draw_monthly_panel(axes[0], segments, markers)
	if tasks or not segments:
		draw_quarterly_panel(axes[-1], tasks)

	legend = [
		Patch(color=COLOR_RELEASED_BAR, alpha=BAR_ALPHA, label='Released'),
		Patch(color=COLOR_PLANNED_BAR, alpha=BAR_ALPHA, label='Planned'),
	]
	if any(item['color'] == COLOR_SKIPPED_PATCH for item in tasks + markers):
		legend.append(Patch(color=COLOR_SKIPPED_PATCH, alpha=BAR_ALPHA, label='Skipped patch'))

	# Add current date line
	items = tasks + segments + markers
	current_date = datetime.now()
	if items and min(item['start'] for item in items) <= current_date <= max(item['end'] for item in items):
		for ax in axes:
			ax.axvline(x=current_date, color=COLOR_CURRENT_DATE, linestyle='--', linewidth=1, dashes=(5, 5))
		legend.append(Line2D([], [], color=COLOR_CURRENT_DATE, linestyle='--', linewidth=1, dashes=(5, 5), label='Current Date'))

	# Format dates
	axes[-1].xaxis.set_major_locator(mdates.MonthLocator())
	axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
	axes[-1].tick_params(axis='x', labelrotation=45)

	# Add legend and title
	fig.legend(handles=legend, loc='outside upper right', ncols=len(legend), frameon=False)
	fig.suptitle('Polkadot SDK Release Timeline')

	if labels:
		fit_labels(fig, axes[0], labels)

	# Save
	plt.savefig(output, dpi=dpi, bbox_inches='tight')
	plt.close()

def main():
	parser = argparse.ArgumentParser(description='Generate release timeline Gantt chart')
	parser.add_argument('input', help='Input JSON file path')
	parser.add_argument('-o', '--output', help='Output PNG file path', default='gantt.png')

	args = parser.parse_args()

	try:
		with open(args.input, 'r') as f:
			data = json.load(f)
	except Exception as e:
		print(f"Error reading input file: {e}", file=sys.stderr)
		sys.exit(1)

	tasks = process_releases(data)
	segments, markers = process_monthly_releases(data)
	segments, markers = limit_to_time_window(tasks, segments, markers)
	create_gantt_chart(tasks, segments, markers, args.output)

if __name__ == '__main__':
	main()
