"""
Updates the iCal calendar file in the root directory. Just run it in the top level dir in its stock
configuration:

    python scripts/update-calendar.py

"""

import json
from datetime import datetime, timedelta
from icalendar import Calendar, Event
import pytz

def parse_date(date_str):
	if isinstance(date_str, str):
		return datetime.strptime(date_str, "%Y-%m-%d").date()
	elif isinstance(date_str, dict) and 'estimated' in date_str:
		return datetime.strptime(date_str['estimated'], "%Y-%m-%d").date()
	return None

def create_event(name, start_date, end_date=None, description=""):
	event = Event()
	event.add('summary', name)
	event.add('dtstart', start_date)
	if end_date:
		event.add('dtend', end_date)
	else:
		event.add('dtend', start_date + timedelta(days=1))  # Make it an all-day event
	description += "\n\nFull Calendar: https://github.com/paritytech/release-registry?tab=readme-ov-file#calendar"
	event.add('description', description)
	return event

def generate_ical(data):
	cal = Calendar()
	cal.add('prodid', '-//Polkadot SDK Release Calendar//EN')
	cal.add('version', '2.0')

	sdk_data = data['Polkadot SDK']
	
	for release in sdk_data['releases']:
		release_name = release['name']
		release_state = release['state']
		
		# Release cutoff event
		cutoff_date = parse_date(release['cutoff'])
		if cutoff_date:
			event = create_event(f"{release_name} Cutoff", cutoff_date, description=f"Cutoff for {release_name} ({release_state})")
			cal.add_component(event)
		
		# Release publish event
		publish_date = parse_date(release['publish'].get('when') or release['publish'].get('estimated'))
		if publish_date:
			event = create_event(f"{release_name} Release", publish_date, description=f"Release of {release_name} ({release_state})")
			cal.add_component(event)
		
		# End of life event
		eol_date = parse_date(release.get('endOfLife'))
		if eol_date:
			event = create_event(f"{release_name} End of Life", eol_date, description=f"End of Life for {release_name}")
			cal.add_component(event)
		
		# Patch events
		for patch in release.get('patches', []):
			patch_name = patch['name']
			patch_state = patch['state']
			
			# Patch cutoff event
			patch_cutoff_date = parse_date(patch['cutoff'])
			if patch_cutoff_date:
				event = create_event(f"{patch_name} Cutoff", patch_cutoff_date, description=f"Cutoff for {patch_name} ({patch_state})")
				cal.add_component(event)
			
			# Patch publish event
			patch_publish_date = parse_date(patch['publish'].get('when') or patch['publish'].get('estimated'))
			if patch_publish_date:
				event = create_event(f"{patch_name} Release", patch_publish_date, description=f"Release of {patch_name} ({patch_state})")
				cal.add_component(event)

	return cal.to_ical()

# Load JSON data
with open('releases-v1.json', 'r') as f:
	data = json.load(f)

# Generate iCal
ical_data = generate_ical(data)

# Write to file
with open('releases-v1.ics', 'wb') as f:
	f.write(ical_data)

print("iCal file 'releases-v1.ics' has been generated.")
