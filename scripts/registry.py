"""
Helpers shared by manage.py and the generator scripts.

The generator scripts have a hyphen in their file name and cannot be imported, so the logic they
have in common with manage.py lives here.
"""

from datetime import datetime

def is_monthly(release):
    """A release without a `cadence` field is a (legacy) quarterly release."""
    return release.get('cadence', 'quarterly') == 'monthly'

def release_sort_key(name):
    """Sort key of a release or patch name: 'stable2611' and 'stable2611-1' give (26, 11)."""
    yymm = name.replace('stable', '').split('-')[0]
    return int(yymm[:2]), int(yymm[2:])

def date_of(value):
    """
    The date in a date field of the registry. A date field has one of three shapes:
    'YYYY-MM-DD', {'when': 'YYYY-MM-DD', 'tag': ...} or {'estimated': 'YYYY-MM-DD'}.
    """
    if isinstance(value, dict):
        value = value.get('when') or value.get('estimated')
    if not isinstance(value, str):
        raise ValueError(f"Not a date field: {value!r}")
    return datetime.strptime(value, '%Y-%m-%d').date()
