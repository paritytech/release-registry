import json
import re
from typing import Dict, Any, List

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
        deprecated_info = state['deprecated']
        return f"Deprecated since {deprecated_info['since']}, use {deprecated_info['useInstead']}"
    return 'N/A'

def generate_name_link(name: str, publish: Any, is_deprecated: bool) -> str:
    if isinstance(publish, dict) and 'tag' in publish:
        name_with_link = f"[{name}](https://github.com/paritytech/polkadot-sdk/releases/tag/{publish['tag']})"
    else:
        name_with_link = name
    
    return f"~~{name_with_link}~~" if is_deprecated else name_with_link

def generate_row(item: Dict[str, Any], is_patch: bool = False, is_recommended: bool = False, is_planned: bool = False) -> str:
    state = format_state(item['state'])
    is_deprecated = isinstance(item['state'], str) and item['state'].lower() == 'deprecated'
    name = generate_name_link(item['name'], item['publish'], is_deprecated)
    name = f"{'&nbsp;&nbsp;' if is_patch else ''}{name}"
    cutoff = format_date(item['cutoff'])
    publish = format_date(item['publish'])
    end_of_life = format_date(item.get('endOfLife', '-'))

    return f"| {'**' if not is_patch else ''}{name}{'**' if not is_patch else ''} | " \
           f"{cutoff} | {publish} | " \
           f"{end_of_life if not is_patch else ''} | {state if not is_patch else ''} |"

def generate_markdown_table(data: Dict[str, Any]) -> str:
    project_info = data["Polkadot SDK"]
    recommended = project_info['recommended']
    releases = project_info['releases']

    table = "| Version | Cutoff | Published | End of Life | State |\n" \
            "|---------|--------|-----------|-------------|-------|\n"

    for release in releases:
        is_recommended = release['name'] == recommended['release']
        is_planned = isinstance(release['state'], str) and release['state'].lower() == 'planned'
        table += generate_row(release, is_recommended=is_recommended and recommended.get('patch') is None, is_planned=is_planned) + '\n'

        for patch in release.get('patches', []):
            is_recommended_patch = is_recommended and patch['name'].split('-')[-1] == recommended.get('patch')
            is_patch_planned = isinstance(patch['state'], str) and patch['state'].lower() == 'planned'
            table += generate_row(patch, is_patch=True, is_recommended=is_recommended_patch, is_planned=is_patch_planned) + '\n'

    return table

def update_readme(markdown_table: str) -> None:
    try:
        with open('README.md', 'r+') as file:
            content = file.read()
            updated_content = re.sub(
                r'(<!-- TEMPLATE BEGIN -->).*?(<!-- TEMPLATE END -->)',
                r'\1\n\n' + markdown_table + r'\n\n\2',
                content,
                flags=re.DOTALL
            )
            file.seek(0)
            file.write(updated_content)
            file.truncate()
        print("README.md has been updated successfully.")
    except FileNotFoundError:
        print("Error: 'README.md' file not found.")

def main() -> None:
    try:
        with open('releases-v1.json', 'r') as file:
            json_data = json.load(file)
        markdown_table = generate_markdown_table(json_data)
        update_readme(markdown_table)
    except FileNotFoundError:
        print("Error: 'releases-v1.json' file not found.")
    except json.JSONDecodeError:
        print("Error: Invalid JSON format in 'releases-v1.json'.")

if __name__ == "__main__":
    main()
