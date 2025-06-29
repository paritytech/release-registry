import json
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import argparse
import sys
from typing import List, Dict, Any

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

def process_releases(data: Dict) -> tuple[List[Dict], datetime, datetime]:
	tasks = []
	min_date = datetime.max
	max_date = datetime.min
	
	sdk_data = data.get("Polkadot SDK", {})
	releases = sdk_data.get("releases", [])
	
	for release in releases:
		if 'deprecated' in release['state']:
			continue

		name = release['name']
		start_date = parse_date(release['publish'])
		end_date = parse_date(release['endOfLife'])
		
		if not (start_date and end_date):
			continue
			
		min_date = min(min_date, start_date)
		max_date = max(max_date, end_date)
		
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
			max_date = max(max_date, patch_end)
			
			is_planned = (isinstance(patch['publish'], dict) and 'estimated' in patch['publish']) or (isinstance(patch['state'], dict) and 'deprecated' in patch['state'])
			is_skipped = patch['state'] == 'skipped'
			color = COLOR_SKIPPED_PATCH if is_skipped else (COLOR_PLANNED_PATCH if is_planned else COLOR_RELEASED_PATCH)
			
			tasks.append({
				'name': patch['name'].split('-')[1],
				'start': patch_date,
				'end': patch_end,
				'color': color
			})
	
	return tasks, min_date, max_date

def create_gantt_chart(tasks: List[Dict], min_date: datetime, max_date: datetime, output: str):
	fig, ax = plt.subplots(figsize=(15, 8))
	
	# Plot bars
	for idx, task in enumerate(tasks):
		ax.barh(idx, 
				(task['end'] - task['start']).days, 
				left=task['start'], 
				color=task['color'], 
				alpha=0.8)
	
	# Add current date line
	current_date = datetime.now()
	if min_date <= current_date <= max_date:
		ax.axvline(x=current_date, color=COLOR_CURRENT_DATE, linestyle='--', linewidth=1, label='Current Date', dashes=(5, 5))
		ax.legend()
		
	# Customize axis
	ax.set_ylim(-0.5, len(tasks) - 0.5)
	ax.set_yticks(range(len(tasks)))
	ax.set_yticklabels(['stable\n'+t['name'].replace('stable', '') if 'stable' in t['name'] else '' for t in tasks], fontsize=15)
	
	# Format dates
	ax.xaxis.set_major_locator(mdates.MonthLocator())
	ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
	plt.xticks(rotation=45)
	
	# Add grid and title
	ax.grid(True, axis='x', alpha=0.3)
	ax.set_title('Polkadot SDK Release Timeline', pad=12)
	
	# Adjust layout and save
	plt.tight_layout()
	plt.savefig(output, dpi=300, bbox_inches='tight')
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
	
	tasks, min_date, max_date = process_releases(data)
	create_gantt_chart(tasks, min_date, max_date, args.output)

if __name__ == '__main__':
	main()
