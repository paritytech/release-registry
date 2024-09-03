import json
import os
import requests
from datetime import datetime

releases = json.load(open("releases-v1.json"))

def download_svg(url, filename):
    response = requests.get(url)
    print(f"Downloading SVG from {url}")
    
    if response.status_code == 200:
        svg_content = response.content
        
        with open(filename, 'wb') as file:
            file.write(svg_content)
        print(f"SVG successfully downloaded and saved as {filename}")
    else:
        raise Exception(f"Failed to download SVG. Status code: {response.status_code}")

def update_latest():
    recommended = releases["Polkadot SDK"]["recommended"]

    latest = recommended['release'].replace('stable', '')
    if 'patch' in recommended:
        latest += f"_{recommended['patch']}"

    latest_url = f"https://img.shields.io/badge/Current%20Stable%20Release-polkadot_{latest}-green"
    latest_name = "badges/polkadot-sdk-latest.svg"
    download_svg(latest_url, latest_name)

def find_next_unreleased_release(releases):
    for release in releases:
        if release['state'] in ['planned', 'staging']:
            return release
    return None

def format_date(date_str):
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    return date_obj.strftime("%Y/%m/%d")

def update_next():
    releases = json.load(open("releases-v1.json"))
    sdk_releases = releases["Polkadot SDK"]["releases"]
    
    next_release = find_next_unreleased_release(sdk_releases)
    
    if next_release:
        next_version = next_release['name'].replace('stable', '')
        publish_date = next_release['publish']
        
        if isinstance(publish_date, dict) and 'estimated' in publish_date:
            formatted_date = format_date(publish_date['estimated'])
        elif isinstance(publish_date, dict) and 'when' in publish_date:
            formatted_date = format_date(publish_date['when'])
        else:
            formatted_date = "Unknown"
        
        next_url = f"https://img.shields.io/badge/Next%20Stable%20Release%20%28polkadot_{next_version}%29-{formatted_date}-orange"
        next_name = "badges/polkadot-sdk-next.svg"
        download_svg(next_url, next_name)
    else:
        print("No upcoming unreleased version found.")

if __name__ == "__main__":
    update_latest()
    update_next()
