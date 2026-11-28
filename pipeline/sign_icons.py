"""Sign face icons for the map, from the standards site's sign artwork.

Writes assets/signs/<key>.png (64 px tall) and assets/signs/index.json {key: {name, slug}}.
key = code in lower case without brackets or spaces: R1-1 -> r1-1, SR4-1(CA) -> sr4-1ca.
Codes drawn only as dimension sheets get no icon; the map draws a plain code tag for those.
Usage: python3 pipeline/sign_icons.py <standards repo>
"""
import sys, os, json, subprocess, io
from PIL import Image

SRC = sys.argv[1]; OUT = 'assets/signs'; os.makedirs(OUT, exist_ok=True)
key = lambda c: c.lower().replace('(', '').replace(')', '').replace(' ', '')
signs = json.load(open(f'{SRC}/data/signs/signs.json'))
index = {}; made = 0
for s in signs:
    k = key(s['code']); svg = s.get('svg') or ''
    index[k] = {'code': s['code'], 'name': s.get('name', ''), 'slug': s.get('slug', k), 'svg': svg if 'Sheet_' not in svg else ''}
    if 'Sheet_' in svg or not svg: continue
    path = SRC + '/public' + svg
    if not os.path.exists(path): continue
    try:
        if path.endswith('.svg'):
            png = subprocess.run(['rsvg-convert', '-h', '64', path], capture_output=True, check=True).stdout
            im = Image.open(io.BytesIO(png)).convert('RGBA')
        else:
            im = Image.open(path).convert('RGBA'); im = im.resize((max(1, round(im.width * 64 / im.height)), 64), Image.LANCZOS)
        if im.width > 128: im = im.resize((128, max(1, round(im.height * 128 / im.width))), Image.LANCZOS)
        im.save(f'{OUT}/{k}.png', optimize=True); index[k]['icon'] = 1; made += 1
    except Exception as e:
        print('skip', s['code'], str(e)[:60])
json.dump(index, open(f'{OUT}/index.json', 'w'), separators=(',', ':'))
print(made, 'icons for', len(index), 'codes')
