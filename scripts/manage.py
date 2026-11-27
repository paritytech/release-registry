import argparse
import json
from datetime import datetime, timedelta
import sys
import re

from registry import date_of, is_monthly, release_sort_key

MONTHLY = 'monthly'
QUARTERLY = 'quarterly'

# How many planned monthly releases the registry keeps ahead of the newest released one.
PLAN_AHEAD_COUNT = 6

# Order of the keys of a monthly release in the JSON file.
MONTHLY_KEY_ORDER = ['name', 'semver', 'cadence', 'lts', 'cutoff', 'publish', 'state', 'endOfLife', 'patches']

# The states in which a release accepts each action. An action on a release that is already out
# (or deprecated) would set its state back, and for a monthly release it would also rewrite the
# releases around it, as their semver and end-of-life dates follow from one another. Planning a
# release that is cut off would replace its cutoff date and tag with an estimate.
RELEASE_ACTIONS = {
    'plan': ('planned', 'skipped'),
    'cutoff': ('planned', 'staging'),
    'publish': ('planned', 'staging', 'released'),
    'skip': ('planned', 'staging', 'skipped'),
}

def load_json(file_path):
    with open(file_path, 'r') as f:
        return json.load(f)

def save_json(data, file_path):
    for project in data.values():
        sync_monthly_chain(project)

    # Serialize first, so that a failure cannot leave a half-written file behind.
    text = json.dumps(data, indent=2)
    with open(file_path, 'w') as f:
        f.write(text)

def validate_version(version):
    if not re.fullmatch(r'stable2[0-9](0[1-9]|1[0-2])(-[1-9][0-9]*)?', version):
        raise ValueError("Invalid version format. Expected 'stableYYMM' or 'stableYYMM-X' for patches.")

def validate_release(version):
    """For the commands that work on a whole release: the name of a patch is not accepted."""
    validate_version(version)
    if '-' in version:
        raise ValueError(f"Expected a release, but {version} is a patch")

def validate_semver(semver):
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', semver):
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

def is_deprecated(item):
    return isinstance(item['state'], dict) and 'deprecated' in item['state']

def state_of(item):
    return 'deprecated' if is_deprecated(item) else item['state']

def is_lts(release):
    return release.get('lts') is True

def superseded_on(item, use_instead, date):
    """Whether a release or patch was deprecated in favour of `use_instead` on `date`."""
    if not is_deprecated(item):
        return False
    deprecated = item['state']['deprecated']
    return deprecated.get('useInstead') == use_instead and deprecated.get('since') == date

def last_full_week_monday(year, month):
    """The Monday of the release week of a month: the last Monday whose Friday is in the same month."""
    last_day = datetime(year + month // 12, month % 12 + 1, 1).date() - timedelta(days=1)
    last_friday = last_day - timedelta(days=(last_day.weekday() - 4) % 7)
    return last_friday - timedelta(days=4)

def release_week(name):
    """The dates the week rule gives a monthly release: (cutoff Monday, publish Thursday)."""
    year, month = release_sort_key(name)
    cutoff = last_full_week_monday(2000 + year, month)
    return cutoff, cutoff + timedelta(days=3)

def next_release_name(name):
    year, month = release_sort_key(name)
    if month == 12:
        year, month = year + 1, 1
    else:
        month += 1
    return f'stable{year:02d}{month:02d}'

def next_minor(semver):
    """1.26.0 becomes 1.27.0."""
    validate_semver(semver)
    major, minor, _ = semver.split('.')
    return f'{int(major)}.{int(minor) + 1}.0'

def patch_semver(release, patch_number):
    """The semver of a patch of `release`, or None if the release has no usable semver."""
    base_semver = release.get('semver', '')
    if not base_semver:
        return None
    try:
        parts = base_semver.split('.')
        return f'{int(parts[0])}.{int(parts[1])}.{patch_number}'
    except (ValueError, IndexError):
        # If semver parsing fails, we'll skip semver generation for patches
        return None

def monthly_releases(project):
    """The monthly releases of a project, oldest first."""
    monthly = [release for release in project['releases'] if is_monthly(release)]
    return sorted(monthly, key=lambda release: release_sort_key(release['name']))

def earlier_monthly_releases(project, release):
    key = release_sort_key(release['name'])
    return [other for other in monthly_releases(project) if release_sort_key(other['name']) < key]

def check_release_action(release, action):
    state = state_of(release)
    if state not in RELEASE_ACTIONS[action]:
        hint = " Plan it again first." if state == 'skipped' else ""
        raise ValueError(f"Cannot {action} {release['name']}: its state is '{state}'.{hint}")

def check_not_overtaken(project, name):
    """
    Fails if a later monthly release is already cut off or released. A release that joins the
    schedule behind such a release would get the same semver, and could be published after it.
    """
    key = release_sort_key(name)
    later = [other['name'] for other in monthly_releases(project)
             if release_sort_key(other['name']) > key and other['state'] not in ('planned', 'skipped')]
    if later:
        raise ValueError(f"Cannot plan {name}: the later release {later[0]} is already cut off or released.")

def monthly_dates(cutoff):
    """The estimated (cutoff, publish) dates of a monthly release that is cut on `cutoff`."""
    cutoff_date = datetime.strptime(cutoff, '%Y-%m-%d')
    if cutoff_date.weekday() != 0:
        raise ValueError(f"The cutoff date of a monthly release must be a Monday, {cutoff} is a {cutoff_date:%A}")
    publish_date = cutoff_date + timedelta(days=3)  # Thursday of the same week
    return cutoff, publish_date.strftime('%Y-%m-%d')

def new_monthly_release(name, cutoff):
    """A planned monthly release. Its semver and end of life are filled in by sync_monthly_chain."""
    cutoff, publish = monthly_dates(cutoff)
    return {
        'name': name,
        'cadence': MONTHLY,
        'cutoff': {'estimated': cutoff},
        'publish': {'estimated': publish},
        'state': 'planned'
    }

def sort_releases(project):
    project['releases'].sort(key=lambda release: release_sort_key(release['name']))

def sync_monthly_chain(project):
    """
    Re-derives the fields of the monthly releases that follow from the releases around them. It
    changes nothing if they are already consistent and is run before every save:

    - End of life: a monthly release is supported until the next one that is not skipped is
      published. If none is planned yet, the date comes from the week rule.
    - SemVer: every planned monthly release has the minor version of the one before it plus one.
      Releases in any other state keep the semver they have, so the value recorded when a release
      is published is what the planned releases after it follow.
    - SemVer of patches: every patch has the major and minor version of its release.

    Skipped, deprecated and LTS releases keep their end of life.
    """
    monthly = monthly_releases(project)
    skipped = {release['name'] for release in monthly if release['state'] == 'skipped'}
    chain = [release for release in monthly if release['name'] not in skipped]

    for index, release in enumerate(chain):
        name = release['name']

        if release['state'] == 'planned':
            if index > 0:
                previous = chain[index - 1]
                if not previous.get('semver'):
                    raise ValueError(f"Cannot derive the semver of {name}: {previous['name']} has none")
                release['semver'] = next_minor(previous['semver'])
            elif not release.get('semver'):
                raise ValueError(f"{name} has no earlier monthly release to take its semver from, pass one: "
                                 f"release plan {name} <cutoff-date> <semver>")

        if not is_lts(release) and not is_deprecated(release):
            if index + 1 < len(chain):
                end_of_life = date_of(chain[index + 1]['publish'])
            else:
                successor = next_release_name(name)
                while successor in skipped:
                    successor = next_release_name(successor)
                end_of_life = release_week(successor)[1]
            release['endOfLife'] = {'estimated': end_of_life.strftime('%Y-%m-%d')}

    for release in monthly:
        for patch in release.get('patches', []):
            semver = patch_semver(release, patch['name'].split('-')[-1])
            if semver:
                patch['semver'] = semver
            else:
                patch.pop('semver', None)

        ordered = {key: release[key] for key in MONTHLY_KEY_ORDER if key in release}
        ordered.update(release)
        release.clear()
        release.update(ordered)

def plan_ahead(project, count=PLAN_AHEAD_COUNT):
    """
    Adds planned monthly releases, with the dates of the week rule, until `count` planned ones
    follow the newest monthly release that is released or in staging. Returns the names it added,
    which is none if enough are planned already.
    """
    monthly = monthly_releases(project)
    if not monthly:
        raise ValueError("There is no monthly release to plan ahead from. Plan the first one with: "
                         "release plan <release> <cutoff-date> <semver>")

    releases = {release['name']: release for release in project['releases']}
    started = [release for release in monthly if release['state'] not in ('planned', 'skipped')]
    name = next_release_name(started[-1]['name']) if started else monthly[0]['name']

    added = []
    planned = 0
    while planned < count:
        release = releases.get(name)
        if release is None:
            validate_version(name)
            release = new_monthly_release(name, release_week(name)[0].strftime('%Y-%m-%d'))
            project['releases'].append(release)
            added.append(name)
        elif not is_monthly(release):
            raise ValueError(f"Cannot plan ahead: {name} already exists as a quarterly release")

        if release['state'] == 'planned':
            planned += 1
        name = next_release_name(name)

    sort_releases(project)
    return added

def update_patch(release, patch_number, date, field):
    if 'patches' not in release:
        release['patches'] = []

    for patch in release['patches']:
        if patch['name'].endswith(f'-{patch_number}'):
            if field == 'cutoff':
                patch['cutoff'] = date
                patch['state'] = 'staging'
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

    # If the patch doesn't exist, create it. A patch that is cut off or published right away gets
    # the exact date as its cutoff.
    new_patch = {
        'name': f'{release["name"]}-{patch_number}',
        'cutoff': {'estimated': date} if field == 'plan' else date,
        'publish': {'when': date, 'tag': f'polkadot-{release["name"]}-{patch_number}'} if field == 'publish' else {'estimated': date},
        'state': 'staging' if field == 'cutoff' else ('released' if field == 'publish' else 'planned')
    }
    semver = patch_semver(release, patch_number)
    if semver:
        new_patch['semver'] = semver
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
            semver = patch_semver(release, i)
            if semver:
                new_patch['semver'] = semver

            release['patches'].append(new_patch)

        cutoff_date = next_nth_monday(cutoff_date, nth_monday)

    # Sort patches by their number to maintain order
    release['patches'].sort(key=lambda x: int(x['name'].split('-')[-1]))

def new_quarterly_release(name, cutoff, semver):
    cutoff_date = datetime.strptime(cutoff, '%Y-%m-%d')
    publish_date = cutoff_date + timedelta(days=45)  # 1.5 months after cutoff
    # If the publish date is on a weekend, move it to the next monday
    if publish_date.weekday() >= 5:
        publish_date += timedelta(days=(7 - publish_date.weekday()))
    new_release = {'name': name}
    if semver:
        new_release['semver'] = semver
    new_release.update({
        'cutoff': {'estimated': cutoff},
        'publish': {'estimated': publish_date.strftime('%Y-%m-%d')},
        'state': 'planned',
        'endOfLife': {'estimated': (publish_date + timedelta(days=365)).strftime('%Y-%m-%d')}
    })
    return new_release

def check_planned_semver(project, release, semver):
    """Fails if `semver` was given for a planned monthly release and is not the one that follows from the chain."""
    sync_monthly_chain(project)
    if semver and release['semver'] != semver:
        raise ValueError(f"Semver {semver} does not match {release['semver']}, which follows from the previous "
                         f"monthly release. Leave it out, or pass a different semver when publishing.")

def publish_monthly_release(project, release, date, semver):
    """
    Marks a monthly release as released and rolls the schedule forward: the monthly releases it
    replaces become deprecated, and new ones are planned so that PLAN_AHEAD_COUNT stay planned.
    """
    name = release['name']
    earlier_releases = earlier_monthly_releases(project, release)

    pending = [earlier['name'] for earlier in earlier_releases if earlier['state'] in ('planned', 'staging')]
    if pending:
        raise ValueError(f"Cannot publish {name}: {', '.join(pending)} is not released yet. Publish or skip it first.")

    # Set if the release is published again to correct its date.
    published_before = release['publish'].get('when') if release['state'] == 'released' else None

    if semver:
        release['semver'] = semver
    release['publish'] = {'when': date, 'tag': f'polkadot-{name}'}
    release['state'] = 'released'

    replaced = []
    for earlier in earlier_releases:
        if is_lts(earlier):
            continue
        if earlier['state'] == 'released':
            mark_deprecated(earlier, date, name)
        elif published_before and superseded_on(earlier, name, published_before):
            # Deprecated by the first publish: move it along with the corrected date.
            for item in [earlier] + earlier.get('patches', []):
                if superseded_on(item, name, published_before):
                    item['state']['deprecated']['since'] = date
        else:
            continue
        earlier['endOfLife'] = date
        replaced.append(earlier['name'])

    plan_ahead(project)

    if project['recommended']['release'] in replaced:
        project['recommended'] = {'release': name}

def update_monthly_release(project, release, date, field, semver):
    name = release['name']

    if field == 'cutoff':
        if semver:
            raise ValueError("A semver cannot be set at cutoff. Pass it when publishing instead.")
        release['cutoff'] = {'when': date, 'tag': f'polkadot-{name}-rc1'}
        release['state'] = 'staging'
    elif field == 'publish':
        publish_monthly_release(project, release, date, semver)
    elif field == 'plan':
        if release['state'] == 'skipped':
            check_not_overtaken(project, name)
        cutoff, publish = monthly_dates(date)
        release['cutoff'] = {'estimated': cutoff}
        release['publish'] = {'estimated': publish}
        release['state'] = 'planned'
        if semver:
            release['semver'] = semver
        check_planned_semver(project, release, semver)

def update_release(data, version, date, field, semver=None, cadence=None):
    project, release = find_release(data, version)
    is_patch = '-' in version

    if cadence and (field != 'plan' or is_patch):
        raise ValueError("--cadence can only be used when planning a release")

    if not release and field == 'plan' and not is_patch:
        # Create a new release if it doesn't exist
        project = next(iter(data.values()))  # Get the first (and only) project
        if (cadence or MONTHLY) == MONTHLY:
            check_not_overtaken(project, version)
            new_release = new_monthly_release(version, date)
            if semver:
                new_release['semver'] = semver
        else:
            new_release = new_quarterly_release(version, date, semver)
        project['releases'].append(new_release)
        sort_releases(project)
        if is_monthly(new_release):
            check_planned_semver(project, new_release, semver)
        return True

    if not release:
        return False

    if is_patch:
        patch_number = version.split('-')[1]
        if field in ('cutoff', 'publish') and state_of(release) not in ('released', 'deprecated'):
            raise ValueError(f"Cannot {field} {version}: {release['name']} is not released, "
                             f"its state is '{state_of(release)}'.")
        # The semver of a patch follows from its release, so a given one can only confirm it.
        expected = patch_semver(release, patch_number)
        if semver and semver != expected:
            raise ValueError(f"Semver {semver} does not match {expected}, which follows from {release['name']}")
        return update_patch(release, patch_number, date, field)

    if cadence and cadence != release.get('cadence', QUARTERLY):
        raise ValueError(f"{version} exists as a {release.get('cadence', QUARTERLY)} release, its cadence cannot be changed")

    check_release_action(release, field)
    if is_monthly(release):
        update_monthly_release(project, release, date, field, semver)
    elif field == 'cutoff':
        release['cutoff'] = { 'when': date, 'tag': f'polkadot-{version}-rc1' }
        release['state'] = 'staging'
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

def mark_deprecated(release, date, use_instead):
    release['state'] = {
        'deprecated': {
            'since': date,
            'useInstead': use_instead
        }
    }

    # Also deprecate all patches that were already published.
    # All unpublished patches should be marked as 'skipped'.
    for patch in release.get('patches', []):
        if patch['state'] == 'released':
            patch['state'] = {
                'deprecated': {
                    'since': date,
                    'useInstead': use_instead
                }
            }
        elif patch['state'] in ('planned', 'staging'):
            patch['state'] = 'skipped'

def deprecate_release(data, version, date, use_instead):
    project, release = find_release(data, version)
    if not release:
        return False

    mark_deprecated(release, date, use_instead)
    return True

def skip_monthly_release(project, release):
    chain = [other for other in monthly_releases(project) if other['state'] != 'skipped']

    release['state'] = 'skipped'
    semver = release.pop('semver', None)

    # A skipped release does not use up a version number: sync_monthly_chain gives the planned
    # releases after it the semver of the release before it plus one. The first monthly release
    # has none before it, so it hands its semver to the next one here.
    if semver and len(chain) > 1 and chain[0] is release and chain[1]['state'] == 'planned':
        chain[1]['semver'] = semver

def skip_release(data, version):
    project, release = find_release(data, version)
    if not release:
        return False

    if '-' in version:  # It's a patch
        for patch in release.get('patches', []):
            if patch['name'] == version:
                patch['state'] = 'skipped'
                return True
        return False
    else:  # It's a release
        check_release_action(release, 'skip')
        if is_monthly(release):
            skip_monthly_release(project, release)
        else:
            release['state'] = 'skipped'
        return True

def recommend_release(data, version, patch_number=None):
    project, release = find_release(data, version)
    if not release:
        return False

    if release['state'] != 'released':
        raise ValueError(f"{version} is not a released release")

    recommended = {'release': version}
    if patch_number:
        patch_name = f'{version}-{patch_number}'
        patch = next((patch for patch in release.get('patches', []) if patch['name'] == patch_name), None)
        if patch is None or patch['state'] != 'released':
            raise ValueError(f"{patch_name} is not a released patch")
        recommended['patch'] = patch_number

    project['recommended'] = recommended
    return True

def backfill_patches(data, version=None, start_date=None):
    releases_updated = False
    for project in data.values():
        for release in project['releases']:
            if release['name'].startswith('stable') and (version is None or release['name'] == version):
                # Monthly releases have no patch schedule, their patches are planned one by one.
                if is_monthly(release):
                    if version:
                        raise ValueError(f"{version} is a monthly release and has no patch schedule. "
                                         f"Plan a single patch with: release plan {version}-<N> <date>")
                    continue

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

    if update_release(data, args.version, date, args.field, args.semver or None, args.cadence):
        save_json(data, args.file)
        print(f"Successfully updated {args.field} for {args.version}")
    else:
        raise ValueError(f"Release or patch {args.version} not found")

def handle_plan_ahead_command(args, data):
    if args.count < 1:
        raise ValueError("--count must be at least 1")

    project = next(iter(data.values()))  # Get the first (and only) project
    added = plan_ahead(project, args.count)

    save_json(data, args.file)
    if added:
        print(f"Successfully planned {', '.join(added)}")
    else:
        print(f"Nothing to plan, {args.count} monthly releases are planned already")

def handle_recommend_command(args, data):
    validate_version(args.version)
    if '-' in args.version:
        raise ValueError("Pass the patch number on its own, e.g. 'recommend stable2609 2'")
    if args.patch and not re.fullmatch(r'[1-9][0-9]*', args.patch):
        raise ValueError("Invalid patch number. Expected a positive integer.")

    if recommend_release(data, args.version, args.patch or None):
        save_json(data, args.file)
        recommended = f"{args.version}-{args.patch}" if args.patch else args.version
        print(f"Successfully set the recommended release to {recommended}")
    else:
        raise ValueError(f"Release {args.version} not found")

def handle_deprecate_command(args, data):
    validate_release(args.version)
    date = validate_date(args.date)
    validate_version(args.use_instead)
    if deprecate_release(data, args.version, date, args.use_instead):
        save_json(data, args.file)
        print(f"Successfully deprecated {args.version}")
    else:
        raise ValueError(f"Release {args.version} not found")

def handle_skip_command(args, data):
    validate_version(args.version)
    if skip_release(data, args.version):
        save_json(data, args.file)
        print(f"Successfully skipped {args.version}")
    else:
        raise ValueError(f"Release or patch {args.version} not found")

def handle_backfill_patches_command(args, data):
    if args.version:
        validate_version(args.version)

    start_date = None
    if args.start_date:
        start_date = validate_date(args.start_date)
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        if start_date_obj.weekday() != 0:
            raise ValueError("Start date must be a Monday")

    if args.version:
        if backfill_patches(data, args.version, start_date):
            save_json(data, args.file)
            print(f"Successfully backfilled patches for {args.version}")
        else:
            raise ValueError(f"Failed to backfill patches for {args.version}. Release may not exist or have a valid publish date.")
    else:
        if backfill_patches(data, start_date=start_date):
            save_json(data, args.file)
            print("Successfully backfilled patches for all applicable stable releases")
        else:
            print("No releases were updated. All releases may already have patches or lack valid publish dates.")

def handle_remove_command(args, data):
    validate_release(args.version)
    project, release = find_release(data, args.version)
    if not release:
        raise ValueError(f"Release {args.version} not found")

    project['releases'].remove(release)
    save_json(data, args.file)
    print(f"Successfully removed release {args.version}")

def handle_remove_patches_command(args, data):
    validate_release(args.version)
    project, release = find_release(data, args.version)
    if not release:
        raise ValueError(f"Release {args.version} not found")

    if remove_planned_patches(data, args.version):
        save_json(data, args.file)
        print(f"Successfully removed planned patches for {args.version}")
    else:
        print(f"No planned patches found for {args.version}")

def main(argv=None):
    parser = argparse.ArgumentParser(description="Manage releases-v1.json file")
    subparsers = parser.add_subparsers(dest='action', required=True)

    # Release parser
    release_parser = subparsers.add_parser('release')
    release_parser.add_argument('field', choices=['cutoff', 'publish', 'plan'])
    release_parser.add_argument('version', help="Release version (e.g., stable2401 or stable2401-1 for patches)")
    release_parser.add_argument('date', help="Date in YYYY-MM-DD format")
    release_parser.add_argument('semver', nargs='?', help="Semantic version (e.g., 1.17.0) - optional. Monthly releases derive it from the previous one")
    release_parser.add_argument('--cadence', choices=[MONTHLY, QUARTERLY], help=f"Cadence of a newly planned release (default: {MONTHLY})")

    # Plan ahead parser
    plan_ahead_parser = subparsers.add_parser('plan-ahead')
    plan_ahead_parser.add_argument('--count', type=int, default=PLAN_AHEAD_COUNT, help=f"Number of planned monthly releases to keep (default: {PLAN_AHEAD_COUNT})")

    # Recommend parser
    recommend_parser = subparsers.add_parser('recommend')
    recommend_parser.add_argument('version', help="Release version to recommend (e.g., stable2609)")
    recommend_parser.add_argument('patch', nargs='?', help="Patch number to recommend (e.g., 2) - optional")

    # Release remove parser
    remove_parser = subparsers.add_parser('remove')
    remove_parser.add_argument('version', help="Release version to remove")

    # Deprecate parser
    deprecate_parser = subparsers.add_parser('deprecate')
    deprecate_parser.add_argument('version', help="Release version to deprecate")
    deprecate_parser.add_argument('date', help="Deprecation date in YYYY-MM-DD format")
    deprecate_parser.add_argument('use_instead', help="Version to use instead")

    # Skip parser
    skip_parser = subparsers.add_parser('skip')
    skip_parser.add_argument('version', help="Release or patch version to skip (e.g., stable2401 or stable2401-1 for patches)")

    # Backfill patches parser
    backfill_parser = subparsers.add_parser('backfill-patches')
    backfill_parser.add_argument('version', nargs='?', help="Specific stable version to backfill (e.g., stable2401)")
    backfill_parser.add_argument('--start-date', help="Start date for the first patch cutoff (must be a Monday, format: YYYY-MM-DD)")

    # Remove patches parser
    remove_patches_parser = subparsers.add_parser('remove-patches')
    remove_patches_parser.add_argument('version', help="Release version to remove planned patches from")

    parser.add_argument('--file', default='releases-v1.json', help="Path to the JSON file")

    args = parser.parse_args(argv)

    try:
        data = load_json(args.file)

        if args.action == 'release':
            handle_release_command(args, data)
        elif args.action == 'plan-ahead':
            handle_plan_ahead_command(args, data)
        elif args.action == 'recommend':
            handle_recommend_command(args, data)
        elif args.action == 'deprecate':
            handle_deprecate_command(args, data)
        elif args.action == 'skip':
            handle_skip_command(args, data)
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
