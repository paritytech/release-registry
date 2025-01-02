import json
import re
from typing import Dict, Any, List

import argparse

def format_date(date_info: Any) -> str:
    if isinstance(date_info, str):
        return date_info
    elif 'estimated' in date_info:
        return date_info.get('estimated', 'N/A')
    elif 'when' in date_info:
        return date_info['when']
    return 'N/A'

def format_state(state: Any) -> str:
    if isinstance(state, str):
        return state.capitalize()
    elif isinstance(state, dict) and 'deprecated' in state:
        return f"Deprecated"
    return 'N/A'

def link_to_changelog(name: str, publish: Any, cutoff: Any, is_deprecated: bool) -> str:
    tag = None
    if isinstance(publish, dict) and 'tag' in publish:
        tag = publish['tag']
    elif isinstance(cutoff, dict) and 'tag' in cutoff:
        tag = cutoff['tag']
    
    if tag:
        name_with_link = f"[{name}](https://github.com/paritytech/polkadot-sdk/releases/tag/{tag})"
    else:
        name_with_link = name
    
    return f"~~{name_with_link}~~" if is_deprecated else name_with_link

def generate_row(item: Dict[str, Any], is_patch: bool = False, is_recommended: bool = False, is_planned: bool = False) -> str:
    state = format_state(item['state'])
    state = link_to_changelog(state, item['publish'], item['cutoff'], state.lower() == 'deprecated')
    is_deprecated = isinstance(item['state'], str) and item['state'].lower() == 'deprecated'
    name = f"{'&nbsp;&nbsp;' if is_patch else ''}{item['name']}"
    cutoff = format_date(item['cutoff'])
    publish = format_date(item['publish'])
    end_of_life = format_date(item.get('endOfLife', '-'))
    bold = '' if is_patch else '**'

    return f"| {bold + name + bold} | " \
           f"{cutoff} | { publish } | " \
           f"{end_of_life if not is_patch else ''} | {state} |"

def generate_markdown_table(data: Dict[str, Any], max_patches=3) -> str:
    project_info = data["Polkadot SDK"]
    recommended = project_info['recommended']
    releases = project_info['releases']

    table = "| Version | Cutoff | Publish | End of Life | State |\n" \
            "|---------|--------|-----------|-------------|-------|\n"

    for release in releases:
        is_recommended = release['name'] == recommended['release']
        is_planned = isinstance(release['state'], str) and release['state'].lower() == 'planned'
        table += generate_row(release, is_recommended=is_recommended and recommended.get('patch') is None, is_planned=is_planned) + '\n'

        patches = release.get('patches', [])
        past_patches = [p for p in patches if not (isinstance(p['state'], str) and p['state'].lower() == 'planned')]
        future_patches = [p for p in patches if isinstance(p['state'], str) and p['state'].lower() == 'planned']

        # Handle past patches (newest to oldest)
        sorted_past_patches = sorted(past_patches, key=lambda x: x['name'])
        
        for patch in sorted_past_patches[-max_patches:]:
            is_recommended_patch = is_recommended and patch['name'].split('-')[-1] == recommended.get('patch')
            table += generate_row(patch, is_patch=True, is_recommended=is_recommended_patch, is_planned=False) + '\n'

        # Handle future patches
        for i, patch in enumerate(future_patches[:max_patches]):
            is_recommended_patch = is_recommended and patch['name'].split('-')[-1] == recommended.get('patch')
            table += generate_row(patch, is_patch=True, is_recommended=is_recommended_patch, is_planned=True) + '\n'
        
        if len(past_patches) > max_patches or len(future_patches) > max_patches:
            if len(past_patches) > max_patches:
                table += f"| &nbsp;&nbsp;([{len(past_patches) - max_patches} more past"
            if len(past_patches) > max_patches and len(future_patches) > max_patches:
                table += ", "
            else:
                table += "| &nbsp;&nbsp;(["
            if len(future_patches) > max_patches:
                table += f"{len(future_patches) - max_patches} more planned"
            table += "](CALENDAR.md)) |  |  | | |\n"        

    return table

def update_readme(markdown_table: str, output) -> None:
    try:
        with open(output, 'r+') as file:
            content = file.read()
            updated_content = re.sub(
                r'(<!-- TEMPLATE BEGIN -->).*?(<!-- TEMPLATE END -->)',
                r'\1\n\n' + markdown_table + r'\n\2',
                content,
                flags=re.DOTALL
            )
            file.seek(0)
            file.write(updated_content)
            file.truncate()
        print(f"{output} has been updated successfully.")
    except FileNotFoundError:
        print(f"Error: '{output}' file not found.")

def main(max_patches, output) -> None:
    try:
        with open('releases-v1.json', 'r') as file:
            json_data = json.load(file)
        markdown_table = generate_markdown_table(json_data, max_patches)
        update_readme(markdown_table, output)
    except FileNotFoundError:
        print("Error: 'releases-v1.json' file not found.")
    except json.JSONDecodeError:
        print("Error: Invalid JSON format in 'releases-v1.json'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-patches", type=int, default=2, help="Maximum number of patches to display for each release.")
    parser.add_argument("--output", type=str, default="README.md", help="Output file to write the updated README to.")
    args = parser.parse_args()
    main(max_patches=args.max_patches, output=args.output)
