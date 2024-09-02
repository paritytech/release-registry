import argparse
import json
from datetime import datetime, timedelta
import sys
import re

def load_json(file_path):
    with open(file_path, 'r') as f:
        return json.load(f)

def save_json(data, file_path):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)

def validate_version(version):
    if not re.match(r'^stable2[45][01][0-9](-[0-9]*)?$', version):
        raise ValueError("Invalid version format. Expected 'stableYYMM' or 'stableYYMM-X' for patches.")

def validate_date(date_str):
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')
    except ValueError:
        raise ValueError("Invalid date format. Expected 'YYYY-MM-DD'.")

def find_release(data, version):
    release_version = version.split('-')[0]
    for project in data.values():
        for release in project['releases']:
            if release['name'] == release_version:
                return project, release
    return None, None

def update_patch(release, patch_number, date, field):
    if 'patches' not in release:
        release['patches'] = []

    for patch in release['patches']:
        if patch['name'].endswith(f'-{patch_number}'):
            if field == 'cutoff':
                patch['cutoff'] = date
                patch['state'] = 'testing'
            elif field == 'publish':
                patch['publish'] = {'when': date, 'tag': f'polkadot-{patch["name"]}'}
                patch['state'] = 'released'
                # Also set the cutoff if it was not set
                if isinstance(patch['cutoff'], dict) and 'estimated' in patch['cutoff']:
                    patch['cutoff'] = date
            elif field == 'plan':
                patch['cutoff'] = {'estimated': date}
                patch['publish'] = {'estimated': date}
                patch['state'] = 'planned'
            return True

    # If the patch doesn't exist, create it
    new_patch = {
        'name': f'{release["name"]}-{patch_number}',
        'cutoff': date if field == 'cutoff' else {'estimated': date},
        'publish': {'when': date, 'tag': f'polkadot-{release["name"]}-{patch_number}'} if field == 'publish' else {'estimated': date},
        'state': 'testing' if field == 'cutoff' else ('released' if field == 'publish' else 'planned')
    }
    release['patches'].append(new_patch)
    return True

def create_planned_patches(release, start_date, num_patches=26):
    if 'patches' not in release:
        release['patches'] = []

    existing_patch_numbers = set(int(patch['name'].split('-')[-1]) for patch in release['patches'] if '-' in patch['name'])
    
    last_patch_date = datetime.strptime(start_date, '%Y-%m-%d')
    for i in range(1, num_patches + 1):
        if i not in existing_patch_numbers:
            cutoff_date = (last_patch_date + timedelta(days=14)).strftime('%Y-%m-%d')
            publish_date = (last_patch_date + timedelta(days=17)).strftime('%Y-%m-%d')
            new_patch = {
                'name': f'{release["name"]}-{i}',
                'cutoff': {'estimated': cutoff_date},
                'publish': {'estimated': publish_date},
                'state': 'planned'
            }
            release['patches'].append(new_patch)
            last_patch_date = datetime.strptime(cutoff_date, '%Y-%m-%d')
        else:
            # If the patch already exists, find its date to continue the sequence
            existing_patch = next(patch for patch in release['patches'] if patch['name'].endswith(f'-{i}'))
            if 'cutoff' in existing_patch:
                # If no publish date, use cutoff date
                if isinstance(existing_patch['cutoff'], dict):
                    if 'when' in existing_patch['cutoff']:
                        last_patch_date = datetime.strptime(existing_patch['cutoff']['when'], '%Y-%m-%d')
                    elif 'estimated' in existing_patch['cutoff']:
                        last_patch_date = datetime.strptime(existing_patch['cutoff']['estimated'], '%Y-%m-%d')
                elif isinstance(existing_patch['cutoff'], str):
                    last_patch_date = datetime.strptime(existing_patch['cutoff'], '%Y-%m-%d')
            else:
                # If no publish or cutoff date, use the previous patch date + 14 days
                last_patch_date += timedelta(days=14)

    # Sort patches by their number to maintain order
    release['patches'].sort(key=lambda x: int(x['name'].split('-')[-1]))

def update_release(data, version, date, field):
    project, release = find_release(data, version)

    if not release and field == 'plan':
        # Create a new release if it doesn't exist
        project = next(iter(data.values()))  # Get the first (and only) project
        cutoff_date = datetime.strptime(date, '%Y-%m-%d')
        publish_date = cutoff_date + timedelta(days=45)  # 1.5 months after cutoff
        new_release = {
            'name': version,
            'cutoff': {'estimated': date},
            'publish': {'estimated': publish_date.strftime('%Y-%m-%d')},
            'state': 'planned',
            'endOfLife': {'estimated': (publish_date + timedelta(days=365)).strftime('%Y-%m-%d')}
        }
        project['releases'].append(new_release)
        create_planned_patches(new_release, publish_date.strftime('%Y-%m-%d'))
        return True

    if not release:
        return False

    if '-' in version:  # It's a patch
        return update_patch(release, version.split('-')[1], date, field)
    else:  # It's a release
        if field == 'cutoff':
            release['cutoff'] = date
            release['state'] = 'testing'
        elif field == 'publish':
            release['publish'] = {'when': date, 'tag': f'polkadot-{version}'}
            release['state'] = 'released'
        elif field == 'plan':
            cutoff_date = datetime.strptime(date, '%Y-%m-%d')
            publish_date = cutoff_date + timedelta(days=45)  # 1.5 months after cutoff
            release['cutoff'] = {'estimated': date}
            release['publish'] = {'estimated': publish_date.strftime('%Y-%m-%d')}
            release['state'] = 'planned'
            create_planned_patches(release, publish_date.strftime('%Y-%m-%d'))
        return True

def deprecate_release(data, version, date, use_instead):
    project, release = find_release(data, version)
    if not release:
        return False

    release['state'] = {
        'deprecated': {
            'since': date,
            'useInstead': use_instead
        }
    }
    return True

def backfill_patches(data, version=None):
    releases_updated = False
    for project in data.values():
        for release in project['releases']:
            if release['name'].startswith('stable') and (version is None or release['name'] == version):
                if 'publish' in release and isinstance(release['publish'], dict):
                    if 'when' in release['publish']:
                        start_date = release['publish']['when']
                    elif 'estimated' in release['publish']:
                        start_date = release['publish']['estimated']
                    else:
                        continue  # Skip if no valid publish date
                else:
                    continue  # Skip if no valid publish field

                create_planned_patches(release, start_date)
                releases_updated = True
                
                if version:  # If a specific version was requested, we're done after processing it
                    return True
    return releases_updated

def handle_release_command(args, data):
    validate_version(args.version)
    date = validate_date(args.date)
    if update_release(data, args.version, date, args.field):
        save_json(data, args.file)
        print(f"Successfully updated {args.field} for {args.version}")
    else:
        print(f"Release or patch {args.version} not found")

def handle_deprecate_command(args, data):
    validate_version(args.version)
    date = validate_date(args.date)
    validate_version(args.use_instead)
    if deprecate_release(data, args.version, date, args.use_instead):
        save_json(data, args.file)
        print(f"Successfully deprecated {args.version}")
    else:
        print(f"Release {args.version} not found")

def handle_backfill_patches_command(args, data):
    if args.version:
        validate_version(args.version)
        if backfill_patches(data, args.version):
            save_json(data, args.file)
            print(f"Successfully backfilled patches for {args.version}")
        else:
            print(f"Failed to backfill patches for {args.version}. Release may not exist or have a valid publish date.")
    else:
        if backfill_patches(data):
            save_json(data, args.file)
            print("Successfully backfilled patches for all applicable stable releases")
        else:
            print("No releases were updated. All releases may already have patches or lack valid publish dates.")

def handle_remove_command(args, data):
    validate_version(args.version)
    project, release = find_release(data, args.version)
    if not release:
        print(f"Release {args.version} not found")
        return

    project['releases'].remove(release)
    save_json(data, args.file)
    print(f"Successfully removed release {args.version}")

def main():
    parser = argparse.ArgumentParser(description="Manage releases-v1.json file")
    subparsers = parser.add_subparsers(dest='action', required=True)

    # Release parser
    release_parser = subparsers.add_parser('release')
    release_parser.add_argument('field', choices=['cutoff', 'publish', 'plan'])
    release_parser.add_argument('version', help="Release version (e.g., stable2401 or stable2401-1 for patches)")
    release_parser.add_argument('date', help="Date in YYYY-MM-DD format")

    # Release remove parser
    remove_parser = subparsers.add_parser('remove')
    remove_parser.add_argument('version', help="Release version to remove")

    # Deprecate parser
    deprecate_parser = subparsers.add_parser('deprecate')
    deprecate_parser.add_argument('version', help="Release version to deprecate")
    deprecate_parser.add_argument('date', help="Deprecation date in YYYY-MM-DD format")
    deprecate_parser.add_argument('use_instead', help="Version to use instead")

    # Backfill patches parser
    backfill_parser = subparsers.add_parser('backfill-patches')
    backfill_parser.add_argument('version', nargs='?', help="Specific stable version to backfill (e.g., stable2401)")

    parser.add_argument('--file', default='releases-v1.json', help="Path to the JSON file")

    args = parser.parse_args()

    try:
        data = load_json(args.file)

        if args.action == 'release':
            handle_release_command(args, data)
        elif args.action == 'deprecate':
            handle_deprecate_command(args, data)
        elif args.action == 'backfill-patches':
            handle_backfill_patches_command(args, data)
        elif args.action == 'remove':
            handle_remove_command(args, data)

    except ValueError as e:
        print(f"Error: {str(e)}")
        sys.exit(1)
    except FileNotFoundError:
        print(f"Error: File '{args.file}' not found")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in '{args.file}'")
        sys.exit(1)

if __name__ == "__main__":
    main()
