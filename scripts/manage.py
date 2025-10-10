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
    if not re.match(r'^stable2[0-9][01][0-9](-[0-9]*)?$', version):
        raise ValueError("Invalid version format. Expected 'stableYYMM' or 'stableYYMM-X' for patches.")

def validate_semver(semver):
    if not re.match(r'^\d+\.\d+\.\d+$', semver):
        raise ValueError("Invalid semver format. Expected 'X.Y.Z' where X, Y, Z are integers.")

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

def get_nth_monday(date):
    return (date.day - 1) // 7 + 1

def next_nth_monday(date, n):
    next_month = date.replace(day=1) + timedelta(days=32)
    next_month = next_month.replace(day=1)

    while next_month.weekday() != 0:
        next_month += timedelta(days=1)

    next_month += timedelta(weeks=n-1)
    return next_month

def create_planned_patches(release, start_date, num_patches=13):
    if 'patches' not in release:
        release['patches'] = []

    existing_patch_numbers = set(int(patch['name'].split('-')[-1]) for patch in release['patches'] if '-' in patch['name'])

    cutoff_date = datetime.strptime(start_date, '%Y-%m-%d')
    if cutoff_date.weekday() != 0:
        raise ValueError("Start date must be a Monday")

    nth_monday = get_nth_monday(cutoff_date)

    # Get base semver from parent release for patch generation
    base_semver = release.get('semver', '')
    base_major, base_minor = 0, 0
    if base_semver:
        try:
            parts = base_semver.split('.')
            base_major = int(parts[0])
            base_minor = int(parts[1])
        except (ValueError, IndexError):
            # If semver parsing fails, we'll skip semver generation for patches
            base_semver = ''

    for i in range(1, num_patches + 1):
        if i not in existing_patch_numbers:
            publish_date = cutoff_date + timedelta(days=3)  # Thursday of the same week

            cutoff_str = cutoff_date.strftime('%Y-%m-%d')
            publish_str = publish_date.strftime('%Y-%m-%d')
            new_patch = {
                'name': f'{release["name"]}-{i}',
                'cutoff': {'estimated': cutoff_str},
                'publish': {'estimated': publish_str},
                'state': 'planned'
            }

            # Add semver for patch if parent release has semver
            if base_semver:
                patch_semver = f'{base_major}.{base_minor}.{i}'
                new_patch['semver'] = patch_semver

            release['patches'].append(new_patch)

        cutoff_date = next_nth_monday(cutoff_date, nth_monday)

    # Sort patches by their number to maintain order
    release['patches'].sort(key=lambda x: int(x['name'].split('-')[-1]))

def update_release(data, version, date, field, semver=None):
    project, release = find_release(data, version)

    if not release and field == 'plan':
        # Create a new release if it doesn't exist
        project = next(iter(data.values()))  # Get the first (and only) project
        cutoff_date = datetime.strptime(date, '%Y-%m-%d')
        publish_date = cutoff_date + timedelta(days=45)  # 1.5 months after cutoff
        # If the publish date is on a weekend, move it to the next monday
        if publish_date.weekday() >= 5:
            publish_date += timedelta(days=(7 - publish_date.weekday()))
        new_release = {
            'name': version,
            'semver': semver,
            'cutoff': {'estimated': date},
            'publish': {'estimated': publish_date.strftime('%Y-%m-%d')},
            'state': 'planned',
            'endOfLife': {'estimated': (publish_date + timedelta(days=365)).strftime('%Y-%m-%d')}
        }
        project['releases'].append(new_release)
        return True

    if not release:
        return False

    if '-' in version:  # It's a patch
        return update_patch(release, version.split('-')[1], date, field)
    else:  # It's a release
        if field == 'cutoff':
            release['cutoff'] = { 'when': date, 'tag': f'polkadot-{version}-rc1' }
            release['state'] = 'drafted'
        elif field == 'publish':
            release['publish'] = {'when': date, 'tag': f'polkadot-{version}'}
            release['state'] = 'released'
        elif field == 'plan':
            cutoff_date = datetime.strptime(date, '%Y-%m-%d')
            publish_date = cutoff_date + timedelta(days=45)  # 1.5 months after cutoff
            release['cutoff'] = {'estimated': date}
            release['publish'] = {'estimated': publish_date.strftime('%Y-%m-%d')}
            release['state'] = 'planned'
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

    # Also deprecate all patches that were already published.
    # All unpublished patches should be marked as 'skipped'.
    for patch in release['patches']:
        if patch['state'] == 'released':
            patch['state'] = {
                'deprecated': {
                    'since': date,
                    'useInstead': use_instead
                }
            }
        elif patch['state'] == 'planned':
            patch['state'] = 'skipped'

    return True

def backfill_patches(data, version=None, start_date=None):
    releases_updated = False
    for project in data.values():
        for release in project['releases']:
            if release['name'].startswith('stable') and (version is None or release['name'] == version):
                if start_date:
                    create_planned_patches(release, start_date)
                    releases_updated = True
                elif 'publish' in release and isinstance(release['publish'], dict):
                    if 'when' in release['publish']:
                        release_date = release['publish']['when']
                    elif 'estimated' in release['publish']:
                        release_date = release['publish']['estimated']
                    else:
                        continue  # Skip if no valid publish date

                    # Find the next Monday after the release date
                    release_date = datetime.strptime(release_date, '%Y-%m-%d')
                    while release_date.weekday() != 0:
                        release_date += timedelta(days=1)

                    create_planned_patches(release, release_date.strftime('%Y-%m-%d'))
                    releases_updated = True
                else:
                    continue  # Skip if no valid publish field

                if version:  # If a specific version was requested, we're done after processing it
                    return True
    return releases_updated

def remove_planned_patches(data, version):
    project, release = find_release(data, version)
    if not release:
        return False

    if 'patches' not in release:
        return False

    release['patches'] = [patch for patch in release['patches']
                          if not (patch['state'] == 'planned' and
                                  isinstance(patch['cutoff'], dict) and
                                  'estimated' in patch['cutoff'])]
    return True

def handle_release_command(args, data):
    validate_version(args.version)
    date = validate_date(args.date)

    # Validate semver if provided
    if args.semver:
        validate_semver(args.semver)

    if update_release(data, args.version, date, args.field, args.semver):
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

    start_date = None
    if args.start_date:
        start_date = validate_date(args.start_date)
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        if start_date_obj.weekday() != 0:
            print("Error: Start date must be a Monday")
            return

    if args.version:
        if backfill_patches(data, args.version, start_date):
            save_json(data, args.file)
            print(f"Successfully backfilled patches for {args.version}")
        else:
            print(f"Failed to backfill patches for {args.version}. Release may not exist or have a valid publish date.")
    else:
        if backfill_patches(data, start_date=start_date):
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

def handle_remove_patches_command(args, data):
    validate_version(args.version)
    if remove_planned_patches(data, args.version):
        save_json(data, args.file)
        print(f"Successfully removed planned patches for {args.version}")
    else:
        print(f"No planned patches found or release {args.version} not found")

def main():
    parser = argparse.ArgumentParser(description="Manage releases-v1.json file")
    subparsers = parser.add_subparsers(dest='action', required=True)

    # Release parser
    release_parser = subparsers.add_parser('release')
    release_parser.add_argument('field', choices=['cutoff', 'publish', 'plan'])
    release_parser.add_argument('version', help="Release version (e.g., stable2401 or stable2401-1 for patches)")
    release_parser.add_argument('date', help="Date in YYYY-MM-DD format")
    release_parser.add_argument('semver', nargs='?', help="Semantic version (e.g., 1.17.0) - optional")

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
    backfill_parser.add_argument('--start-date', help="Start date for the first patch cutoff (must be a Monday, format: YYYY-MM-DD)")

    # Remove patches parser
    remove_patches_parser = subparsers.add_parser('remove-patches')
    remove_patches_parser.add_argument('version', help="Release version to remove planned patches from")

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
        elif args.action == 'remove-patches':
            handle_remove_patches_command(args, data)

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
