# set quiet

default: venv validate readme calendar badges gantt

# Check releases-v1.json against its JSON schema
validate: venv
	venv/bin/python3 scripts/validate.py

# Run the unit tests of the scripts
test: venv
	venv/bin/python3 -m unittest discover --start-directory scripts --pattern 'test_*.py'

badges: venv
	venv/bin/python3 scripts/update-badges.py

calendar: venv
	venv/bin/python3 scripts/update-calendar.py

readme: venv
	venv/bin/python3 scripts/update-readme.py && venv/bin/python3 scripts/update-readme.py --max-patches 99 --output CALENDAR.md

gantt: venv
	venv/bin/python3 scripts/update-gantt.py releases-v1.json -o .assets/timeline-gantt.png

venv:
	#!/bin/bash
	set -euo pipefail

	# Create the virtual environment if it does not exist
	if [ ! -d "venv" ]; then
		python3 -m venv venv
	fi

	# Install the requirements again whenever they differ from the ones of the last install
	if ! cmp -s scripts/requirements.txt venv/requirements.installed.txt; then
		venv/bin/pip install -r scripts/requirements.txt
		cp scripts/requirements.txt venv/requirements.installed.txt
	fi

# Mark a release or patch as released (semver: only if a monthly release gets another one than planned)
publish release date semver='':
	python3 scripts/manage.py release publish {{quote(release)}} {{quote(date)}} {{ if semver == '' { '' } else { quote(semver) } }}

cutoff release date:
	python3 scripts/manage.py release cutoff {{quote(release)}} {{quote(date)}}

deprecate release date use_instead:
	python3 scripts/manage.py deprecate {{quote(release)}} {{quote(date)}} {{quote(use_instead)}}

skip release:
	python3 scripts/manage.py skip {{quote(release)}}

# Plan or move a monthly release or a patch (semver: only for the first monthly release)
plan release date semver='':
	python3 scripts/manage.py release plan {{quote(release)}} {{quote(date)}} {{ if semver == '' { '' } else { quote(semver) } }}

# Plan monthly releases until `count` of them are planned
plan-ahead count='6':
	python3 scripts/manage.py plan-ahead --count {{quote(count)}}

# Set the recommended release, optionally with a patch number
recommend release patch='':
	python3 scripts/manage.py recommend {{quote(release)}} {{ if patch == '' { '' } else { quote(patch) } }}

backfill release date:
	python3 scripts/manage.py backfill-patches {{quote(release)}} --start-date {{quote(date)}}
