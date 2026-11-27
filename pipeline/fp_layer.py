"""Merge every scanned area's signs into one map layer: data/base/fp.geojson."""
import json, glob, os
feats = []
for f in sorted(glob.glob('data/areas/*/signs.json')):
    d = json.load(open(f)); key = os.path.basename(os.path.dirname(f))
    for s in d.get('signs', []) + [dict(x, name=1) for x in d.get('name_signs', [])]:
        if 'lat' not in s: continue
        code = s.get('code', '') + (f" ({s['val']})" if s.get('val') else '')
        feats.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [round(s['lon'], 6), round(s['lat'], 6)]},
                      'properties': {'id': s.get('id', ''), 'code': code or 'NAME SIGN', 'conf': s.get('conf', 0), 'status': s.get('status', ''),
                                     'seen': str(s.get('seen', '')), 'loc': s.get('loc', ''), 'dir': s.get('dir', 0), 'name': 1 if s.get('name') else 0,
                                     'crop': f"data/areas/{key}/crops/{s['crop']}" if s.get('crop') else '', 'img': s.get('img', ''),
                                     'area': d.get('area', key), 'src': 'FP street-level inventory'}})
json.dump({'type': 'FeatureCollection', 'features': feats}, open('data/base/fp.geojson', 'w'), separators=(',', ':'))
print(len(feats), 'signs from', len(glob.glob('data/areas/*/signs.json')), 'areas')
