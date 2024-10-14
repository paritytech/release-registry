import json
import argparse
import subprocess
import time

def parse_args():
	parser = argparse.ArgumentParser(description='Update project board')
	parser.add_argument('--project', help='Project number')
	parser.add_argument('--org', help='Organization name')
	return parser.parse_args()

def load_releases():
	releases = json.loads(open('releases-v1.json').read())['Polkadot SDK']['releases']

	# Unfold the `cutoff` and `publish` fields of every patch in a release, such that "{ estimated: { when: .. } }" just becomes the inner date.
	for release in releases:
		for patch in release['patches']:
			fix_date(patch)
		fix_date(release)
	
	return releases

def fix_date(patch):
	if 'estimated' in patch['cutoff']:
		patch['cutoff'] = patch['cutoff']['estimated']
	if 'endOfLife' in patch and 'estimated' in patch['endOfLife']:
		patch['endOfLife'] = patch['endOfLife']['estimated']
	if 'estimated' in patch['publish']:
		patch['publish'] = patch['publish']['estimated']
	else:
		patch['publish'] = patch['publish']['when']


# Check that the board has all the setup we need.
def validate_board(org, num, releases):
	fields = gh_list_fields(org, num)
	release_field = next((f for f in fields if f['name'] == 'Release'), None)

	if not release_field:
		raise Exception('Release field not found. Please add it.')
	if not 'options' in release_field:
		raise Exception('Release field is not an enum. Please make it an enum.')
	
	# Maps field option name to id
	release_field_options = {}
	release_field_id = release_field['id']

	for release in releases:
		o = next((o for o in release_field['options'] if o['name'] == release['name']), None)
		if not o:
			raise Exception(f'Please add option "{release['name']}" to project board field "Release". This cannot be done with the gh CLI.')
		release_field_options[release['name']] = o['id']

	start_date_field_id = next((f['id'] for f in fields if f['name'] == 'Start date'), None)
	if not start_date_field_id:
		raise Exception('Start date field not found. Please add it.')
	
	end_date_field_id = next((f['id'] for f in fields if f['name'] == 'End date'), None)
	if not end_date_field_id:
		raise Exception('End date field not found. Please add it.')
	
	project_id = gh_project_id(org, num)
	
	print(f'Project is valid')
	return { 'project_id': project_id, 'release_field_id': release_field_id, 'release_field_option_ids': release_field_options, 'start_date_field_id': start_date_field_id, 'end_date_field_id': end_date_field_id }

def main(org, project_num):
	print(f'Updating project board for project {project_num} in organization {org}')
	releases = load_releases()
	project = validate_board(org, project_num, releases)
	items = gh_list_items(org, project_num)

	for release in releases:
		release_field_option_id = project['release_field_option_ids'][release['name']]

		for patch in release['patches']:
			item = next((i for i in items if i['title'] == patch['name']), None)
			item_needs_update = False

			if not item:
				print(f'Creating item {patch["name"]} for release {release["name"]}')
				item_id = gh_create_item(org, project_num, patch['name'])
				item_needs_update = True
			else:
				print(f'Item {patch["name"]} already exists')
				item_id = item['id']

				if item.get('release') != release['name']:
					print(f'Item {patch["name"]} is in the wrong release. Updating')
					item_needs_update = True
				
				if item.get('start date') != patch['cutoff']:
					print(f'Item {patch["name"]} has the wrong start date. Updating')
					item_needs_update = True
				
				if item.get('end date') != patch['publish']:
					print(f'Item {patch["name"]} has the wrong end date. Updating')
					item_needs_update = True
			
			if item_needs_update:
				gh_create_set_option(project['project_id'], item_id, project['release_field_id'], release_field_option_id)
				gh_set_date(project['project_id'], item_id, project['start_date_field_id'], patch['cutoff'])
				gh_set_date(project['project_id'], item_id, project['end_date_field_id'], patch['publish'])

		# Add the overarching release item
		name = f"{release['name']} LTS"
		item = next((i for i in items if i['title'] == name), None)
		item_needs_update = False

		if not item:
			print(f'Creating item {name} for release {release["name"]}')
			item_id = gh_create_item(org, project_num, name)
			item_needs_update = True
		else:
			print(f'Item for release {release["name"]} already exists')
			item_id = item['id']

			if item.get('release') != release['name']:
				print(f'Item for release {release["name"]} is in the wrong release. Updating')
				item_needs_update = True
			
			if item.get('start date') != release['cutoff']:
				print(f'Item for release {release["name"]} has the wrong start date. Updating')
				item_needs_update = True
			
			if item.get('end date') != release['endOfLife']:
				print(f'Item for release {release["name"]} has the wrong end date. Updating')
				item_needs_update = True
		
		if item_needs_update:
			gh_create_set_option(project['project_id'], item_id, project['release_field_id'], release_field_option_id)
			gh_set_date(project['project_id'], item_id, project['start_date_field_id'], release['cutoff'])
			gh_set_date(project['project_id'], item_id, project['end_date_field_id'], release['endOfLife'])

	print(f'Found {json.dumps(items, indent=2)}')
	pass

def gh_project_id(org, project_num):
	return gh(['project', 'view', f'--owner={org}', project_num, '--format=json'])['id']

def gh_set_date(project_id, item_id, field_id, date):
	gh(['project', 'item-edit', f'--project-id={project_id}', f'--id={item_id}', f'--field-id={field_id}', f'--date={date}', '--format=json'])

def gh_create_set_option(project_id, item_id, field_id, option_id):
	gh(['project', 'item-edit', f'--project-id={project_id}', f'--id={item_id}', f'--field-id={field_id}', f'--single-select-option-id={option_id}', '--format=json'])

def gh_create_item(org, project_num, name):
	data = gh(['project', 'item-create', project_num, f'--title={name}', f'--owner={org}', '--format=json'])
	return data['id']

def gh_list_items(org, project_num):
	data = gh(['project', 'item-list', project_num, f'--owner={org}', '--format=json', '--limit=1000'])
	return data.get('items', [])

def gh_list_fields(org, project_num):
	data = gh(['project', 'field-list', project_num, f'--owner={org}', '--format=json', '--limit=1000'])
	return data.get('fields', [])

# Run gh cli, throw on error and return output
def gh(args):
	time.sleep(1) # Dont spam the API

	cmd = ['gh'] + args
	print(f'Running: {' '.join(cmd)}')
	result = subprocess.run(cmd, capture_output=True, text=True)
	if result.returncode != 0:
		raise Exception(f'Failed to run gh: {result.stderr}')
	return json.loads(result.stdout)

if __name__ == '__main__':
	args = parse_args()
	main(args.org, args.project)
