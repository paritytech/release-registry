set quiet

default: venv
	venv/bin/python3 scripts/update-readme.py
	venv/bin/python3 scripts/update-calendar.py
	venv/bin/python3 scripts/update-badges.py

venv:
	#!/bin/bash

	# Check if venv folder exists
	if [ ! -d "venv" ]; then
		# Create virtual environment
		python3 -m venv venv
		venv/bin/pip install -r scripts/requirements.txt
	fi
