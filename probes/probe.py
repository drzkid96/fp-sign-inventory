import json, urllib.request, urllib.parse
b='34.0197,-118.3995,34.0253,-118.3925'
q=f'[out:json][timeout:120];(way["highway"~"^(motorway|trunk|primary|secondary|tertiary|residential|unclassified|living_street|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link|service)$"]({b});node["highway"~"^(stop|give_way|traffic_signals)$"]({b}););out geom;'
for u in ('https://overpass-api.de/api/interpreter','https://overpass.private.coffee/api/interpreter','https://maps.mail.ru/osm/tools/overpass/api/interpreter'):
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,data=urllib.parse.urlencode({'data':q}).encode(),headers={'User-Agent':'fp-sign-inventory/1.0'}),timeout=200)
        open('probes/osm_culver.json','wb').write(r.read()); print('ok',u); break
    except Exception as e: print(u,e)
