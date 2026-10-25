"""Create or update the Apify actors (created private; publishing to the Store is done in the Apify console) from this folder, then build them.

    python deploy.py            # all four
    python deploy.py secondhand

Uses APIFY_TOKEN if set; otherwise relies on a proxy that injects the Authorization header.
"""
import json
import os
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
MODES = ['mainstream', 'secondhand', 'indie', 'labels']


def files(mode):
    spec = json.loads((HERE / mode / '.actor' / 'actor.json').read_text())
    dockerfile = (HERE / 'Dockerfile').read_text().replace('ARG ACTOR_MODULE=mainstream', f'ARG ACTOR_MODULE={mode}')
    out = [{'name': '.actor/actor.json', 'format': 'TEXT', 'content': json.dumps(spec, indent=2)},
           {'name': 'Dockerfile', 'format': 'TEXT', 'content': dockerfile}]
    for path in sorted((HERE / mode / '.actor').glob('*.json')):  # output / dataset schemas next to actor.json
        if path.name != 'actor.json':
            out.append({'name': f'.actor/{path.name}', 'format': 'TEXT', 'content': path.read_text()})
    if (HERE / mode / 'README.md').exists():  # the actor's Apify Store page
        out.append({'name': 'README.md', 'format': 'TEXT', 'content': (HERE / mode / 'README.md').read_text()})
    for path in sorted((HERE / 'niche_actors').glob('*.py')):
        out.append({'name': f'niche_actors/{path.name}', 'format': 'TEXT', 'content': path.read_text()})
    return spec, out


def deploy(http, mode):
    spec, source = files(mode)
    version = {'versionNumber': spec['version'], 'sourceType': 'SOURCE_FILES', 'buildTag': 'latest', 'sourceFiles': source}
    me = http.get('users/me').raise_for_status().json()['data']['username']
    actor_id = f'{me}~{spec["name"]}'
    if http.get(f'acts/{actor_id}').status_code == 404:
        http.post('acts', json={'name': spec['name'], 'title': spec['title'], 'description': spec['description'],
                                'isPublic': False, 'versions': [version]}).raise_for_status()
    else:
        http.put(f'acts/{actor_id}/versions/{spec["version"]}', json=version).raise_for_status()
    build = http.post(f'acts/{actor_id}/builds', params={'version': spec['version'], 'tag': 'latest'}
                      ).raise_for_status().json()['data']
    while build['status'] in ('READY', 'RUNNING'):
        time.sleep(3)
        build = http.get(f'actor-builds/{build["id"]}').raise_for_status().json()['data']
    print(f'{me}/{spec["name"]}: build {build["status"]} ({build["id"]})')
    if build['status'] != 'SUCCEEDED':
        raise SystemExit(f'Build failed; see https://console.apify.com/actors/{build["actId"]}/builds/{build["id"]}')


if __name__ == '__main__':
    token = os.environ.get('APIFY_TOKEN')
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    with httpx.Client(base_url='https://api.apify.com/v2/', headers=headers, timeout=60) as http:
        for mode in sys.argv[1:] or MODES:
            deploy(http, mode)
