set quiet

default: venv readme
	venv/bin/python3 scripts/update-calendar.py
	venv/bin/python3 scripts/update-badges.py

readme:
	venv/bin/python3 scripts/update-readme.py && venv/bin/python3 scripts/update-readme.py --max-patches 99 --output CALENDAR.md

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
