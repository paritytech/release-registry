# set quiet

default: venv readme calendar badges gantt

badges: venv
	venv/bin/python3 scripts/update-badges.py

calendar: venv
	venv/bin/python3 scripts/update-calendar.py

readme:
	venv/bin/python3 scripts/update-readme.py && venv/bin/python3 scripts/update-readme.py --max-patches 99 --output CALENDAR.md

gantt: venv
	venv/bin/python3 scripts/update-gantt.py releases-v1.json -o .assets/timeline-gantt.png

venv:
	#!/bin/bash

	# Check if venv folder exists
	if [ ! -d "venv" ]; then
		# Create virtual environment
		python3 -m venv venv
		venv/bin/pip install -r scripts/requirements.txt
	fi

publish release date:
	python3 scripts/manage.py release publish {{release}} {{date}}

cutoff release date:
	python3 scripts/manage.py release cutoff {{release}} {{date}}

deprecate release date use_instead:
	python3 scripts/manage.py deprecate {{release}} {{date}} {{use_instead}}
