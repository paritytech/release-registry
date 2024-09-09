"""
This script updates the SVG files in the badges folder.

Just run it in its stock configuration from the root folder:

    python scripts/update-badges.py

"""

import json
import os
import requests
from datetime import datetime

releases = json.load(open("releases-v1.json"))

def download(url, filename):
    response = requests.get(url)

    if response.status_code == 200:
        with open(filename, 'wb') as file:
            file.write(response.content)
            print(f"Downloaded {filename}")
    else:
        raise Exception(f"Failed to download SVG. Status code: {response.status_code}")

def update_latest():
    recommended = releases["Polkadot SDK"]["recommended"]

    latest = recommended['release'].replace('stable', '')
    if 'patch' in recommended:
        latest += f"_{recommended['patch']}"

    latest_url = f"https://img.shields.io/badge/Current%20Stable%20Release-polkadot_{latest}-green"
    latest_name = "badges/polkadot-sdk-latest.svg"
    download(latest_url, latest_name)

def find_next_unreleased_release(releases):
    for release in releases:
        if release['state'] in ['planned', 'staging']:
            return release
    return None

def format_date(date_info):
    if isinstance(date_info, dict):
        if 'estimated' in date_info:
            date_str = date_info['estimated']
        elif 'when' in date_info:
            date_str = date_info['when']
        else:
            return "Unknown"
    else:
        date_str = date_info
    
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    return date_obj.strftime("%Y/%m/%d")

def update_next():
    releases = json.load(open("releases-v1.json"))
    sdk_releases = releases["Polkadot SDK"]["releases"]
    
    next_release = find_next_unreleased_release(sdk_releases)
    
    if next_release:
        next_version = next_release['name'].replace('stable', '')
        cutoff_info = next_release['cutoff']
        
        formatted_date = format_date(cutoff_info)
        
        if isinstance(cutoff_info, dict) and 'tag' in cutoff_info:
            cutoff_tag = cutoff_info['tag']
        else:
            cutoff_tag = f"polkadot-{next_release['name']}-cutoff"
        
        next_url = f"https://img.shields.io/badge/Next%20Stable%20Release%20%28{cutoff_tag}%29-{formatted_date}-orange"
        next_name = "badges/polkadot-sdk-next.svg"
        download(next_url, next_name)
    else:
        print("No upcoming unreleased version found.")

if __name__ == "__main__":
    update_latest()
    update_next()
