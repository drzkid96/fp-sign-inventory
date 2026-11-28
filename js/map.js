/* LA County street inventory map.
   Three sign sources (our scanned inventory, Mapillary detections, county records) are merged on screen:
   one symbol per physical sign, drawn as its sign face, with every source that saw it listed on its card. */
const C = window.CFG, $ = s => document.querySelector(s), V = '?v=' + (C.DATA_V || 1);
const SSS = 'https://drzkid96.github.io/SoCal-Super-Standards';
const SRC = {fp: {c: '#1B795A', t: 'Scanned'}, county: {c: '#00242E', t: 'County record'}, mly: {c: '#568CBB', t: 'Mapillary'}};
const ORDER = ['fp', 'county', 'mly'];
const P_COL = ['#00574A', '#1B795A', '#6BD688', '#B9E6B4', '#E4EFE2'];
const Y_BRK = [[0, '#9FB3B8', '2021'], [2022, '#6BD688', '2022'], [2023, '#1B795A', '2023-24'], [2025, '#00242E', '2025+']];
const MERGE_M = 12, ICON_Z = 15.5, SINCE = Date.UTC(2021, 0, 1), SINCE_ISO = '2021-01-01T00:00:00Z';   // data before 2021 is not shown
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const day = ms => ms ? new Date(+ms).toISOString().slice(0, 10) : '';
const keyOf = c => String(c || '').toLowerCase().replace(/[() ]/g, '');
const famKey = c => keyOf(String(c || '').split('/')[0].replace(/\s*\(\d+\)\s*$/, ''));
const sv = (lat, lon) => `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat.toFixed(6)},${lon.toFixed(6)}`;
const mlyAt = (lat, lon) => `https://www.mapillary.com/app/?lat=${lat.toFixed(6)}&lng=${lon.toFixed(6)}&z=19`;
const graph = (path, q = '') => fetch(`https://graph.mapillary.com/${path}${path.includes('?') ? '&' : '?'}${q}&access_token=${encodeURIComponent(C.MLY)}`).then(r => r.json());
const metres = (a, b) => Math.hypot((a[0] - b[0]) * 92300, (a[1] - b[1]) * 110540);

const proto = new pmtiles.Protocol(); maplibregl.addProtocol('pmtiles', proto.tile);
const map = new maplibregl.Map({container: 'map', style: 'https://tiles.openfreemap.org/styles/positron', center: [-118.25, 34.05], zoom: 9.3,
  minZoom: 8, maxZoom: 21, hash: true, attributionControl: {compact: true}});
map.addControl(new maplibregl.NavigationControl({showCompass: false}), 'bottom-right');
map.addControl(new maplibregl.GeolocateControl({positionOptions: {enableHighAccuracy: true}}), 'bottom-right');
map.addControl(new maplibregl.ScaleControl({unit: 'imperial'}), 'bottom-left');

let IDX = {}, CMAP = {}, TRUST = {}, CITIES = [], FP = [], RAW = new Map();
const on = k => document.querySelector(`.chips [data-layer="${k}"]`)?.classList.contains('on');
const vis = (ids, v) => ids.forEach(id => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', v ? 'visible' : 'none'));

/* county object marker codes (TN1, TK1, TQ1, TP1R ...) read as Caltrans object marker types */
let CC = {};
function county(k) {
  const m = String(k || '').match(/^t([nkqrl])-?\d*$/) || String(k || '').match(/^t(p)\d*([rl])$/);
  if (!m) return null; return CC[m[2] ? 'tp' + m[2] : 't' + m[1]] || null;
}
function drawSVG(kind) {
  if (kind === 'q') return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 60"><rect x="6" y="4" width="12" height="54" rx="6" fill="#fff" stroke="#00242E" stroke-width="2"/><rect x="6" y="9" width="12" height="5" fill="#FDBE0F"/><rect x="6" y="17" width="12" height="5" fill="#FDBE0F"/><rect x="6" y="25" width="12" height="5" fill="#FDBE0F"/></svg>`;
  if (kind === 'k') return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 60"><rect x="8" y="4" width="8" height="54" rx="2" fill="#fff" stroke="#00242E" stroke-width="2"/><rect x="6" y="6" width="12" height="16" rx="1" fill="#FDBE0F" stroke="#00242E" stroke-width="1.5"/></svg>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 60"><rect x="6" y="2" width="16" height="56" rx="3" fill="#8a7a66"/><rect x="4" y="14" width="20" height="4" fill="#FDBE0F" stroke="#00242E"/><rect x="4" y="22" width="20" height="4" fill="#FDBE0F" stroke="#00242E"/><rect x="4" y="30" width="20" height="4" fill="#FDBE0F" stroke="#00242E"/></svg>`;
}
/* sign faces */
const resolve = k => IDX[k]?.icon ? k : IDX[k + 'ca']?.icon ? k + 'ca' : null;
const NUMERIC = ['r2-1', 'w13-1p'];
const faceKey = (k, v) => NUMERIC.includes(k) ? k + '@' + (/^\d+$/.test(String(v || '')) ? v : '?') : k;
function speedSVG(code, v) {
  if (code === 'w13-1p') return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 60"><rect x="2" y="2" width="56" height="56" rx="5" fill="#FDBE0F" stroke="#000" stroke-width="3"/><text x="30" y="34" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="26" text-anchor="middle">${v}</text><text x="30" y="51" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="12" text-anchor="middle">MPH</text></svg>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 60"><rect x="1.5" y="1.5" width="45" height="57" rx="3" fill="#fff" stroke="#000" stroke-width="2"/><rect x="4" y="4" width="40" height="52" rx="2" fill="none" stroke="#000" stroke-width="1.5"/><text x="24" y="17" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="9" text-anchor="middle">SPEED</text><text x="24" y="27" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="9" text-anchor="middle">LIMIT</text><text x="24" y="51" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="24" text-anchor="middle">${v}</text></svg>`;
}
function svgImage(svg, h) {
  return new Promise((ok, no) => { const im = new Image(); im.onload = () => { const r = im.width / im.height || 0.8, cv = document.createElement('canvas');
    cv.height = h; cv.width = Math.round(h * r); const x = cv.getContext('2d'); x.drawImage(im, 0, 0, cv.width, cv.height);
    ok({width: cv.width, height: cv.height, data: new Uint8Array(x.getImageData(0, 0, cv.width, cv.height).data.buffer)}); };
    im.onerror = no; im.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg); });
}
function tag(text) {
  const s = 2, f = 12 * s, cv = document.createElement('canvas'), x = cv.getContext('2d');
  x.font = `700 ${f}px Albert Sans, sans-serif`; const w = Math.ceil(x.measureText(text).width) + 10 * s, h = f + 9 * s;
  cv.width = w; cv.height = h; x.font = `700 ${f}px Albert Sans, sans-serif`;
  x.fillStyle = '#fff'; x.strokeStyle = '#5b7278'; x.lineWidth = 1.5 * s; x.setLineDash([3 * s, 2 * s]); x.beginPath(); x.roundRect(s, s, w - 2 * s, h - 2 * s, 3 * s); x.fill(); x.stroke();
  x.fillStyle = '#00242E'; x.textAlign = 'center'; x.textBaseline = 'middle'; x.fillText(text, w / 2, h / 2 + s);
  return {width: w, height: h, data: new Uint8Array(x.getImageData(0, 0, w, h).data.buffer)};
}
const loading = new Set();
async function face(k) {
  if (!k || loading.has(k)) return; loading.add(k);
  try {
    const put = img => { if (map.hasImage('sg:' + k)) map.removeImage('sg:' + k); map.addImage('sg:' + k, img, {pixelRatio: 2}); };
    if (k.startsWith('?')) { put(tag(k.slice(1).toUpperCase() + ' ?')); return; }
    if (k.includes('@')) { const [c, v] = k.split('@'); put(await svgImage(speedSVG(c, v), 128)); return; }
    const cc = county(k);
    if (cc?.face.startsWith('draw:')) { put(await svgImage(drawSVG(cc.face.slice(5)), 128)); return; }
    const r = cc ? cc.face : resolve(k); if (!r) throw 0;
    put((await map.loadImage(`assets/signs/${r}.png`)).data);
  } catch (e) { if (!map.hasImage('sg:' + k)) map.addImage('sg:' + k, tag((IDX[k]?.code || k.split('@')[0]).toUpperCase()), {pixelRatio: 2}); }
}
map.on('styleimagemissing', e => { if (e.id.startsWith('sg:') && !map.hasImage(e.id)) map.addImage(e.id, tag(e.id.slice(3).split('@')[0].toUpperCase() || '?'), {pixelRatio: 2}); });
const SERIES = {r1: 'Stop or yield', r2: 'Speed limit', r3: 'Lane use or turn', r4: 'Keep right or lane', r5: 'Do not enter or exclusion', r6: 'One way',
  r7: 'Parking', r8: 'Parking', r9: 'Pedestrian', r10: 'Signal', r11: 'Road closed', r26: 'Parking', r28: 'Parking', w: 'Warning', sw: 'Warning', om: 'Object marker', d: 'Guide', sr: 'School', s: 'School', m: 'Route marker', g: 'Guide'};
const seriesOf = k => { const m = String(k).match(/^([a-z]+)(\d*)/) || []; return SERIES[m[1] + m[2]] ? m[1] + m[2] : SERIES[m[1]] ? m[1] : null; };
const trustOf = code => (TRUST[String(code || '').split('/')[0].split('(')[0].trim()] || {trust: 'untested'});

map.on('load', async () => {
  const get = (u, d) => fetch(u + V).then(r => r.ok ? r.json() : d).catch(() => d);
  const [tiles, idx, cmap, trust, agency, fp, cc] = await Promise.all([get('data/base/tiles.geojson', {features: []}), get('assets/signs/index.json', {}),
    get('data/classmap.json', {}), get('data/base/trust.json', {codes: {}}), get('data/base/agency.json', null), get('data/base/fp.geojson', {features: []}), get('assets/signs/county-codes.json', {})]);
  IDX = idx; CMAP = cmap; TRUST = trust.codes || {}; CC = cc;
  FP = fp.features.filter(f => !f.properties.name && (Date.parse(f.properties.seen) || 0) >= SINCE);

  // aerial sits under the street names
  const firstLabel = map.getStyle().layers.find(l => l.type === 'symbol')?.id;
  map.addSource('usgs', {type: 'raster', tiles: ['https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 16, attribution: 'USGS'});
  map.addSource('esri', {type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 20, attribution: 'Imagery © Esri'});
  map.addLayer({id: 'base-usgs', type: 'raster', source: 'usgs', maxzoom: 15, layout: {visibility: 'none'}}, firstLabel);
  map.addLayer({id: 'base-esri', type: 'raster', source: 'esri', minzoom: 15, layout: {visibility: 'none'}}, firstLabel);

  // build order tiles
  map.addSource('tiles', {type: 'geojson', data: tiles});
  map.addLayer({id: 'tiles-fill', type: 'fill', source: 'tiles', maxzoom: 15, paint: {'fill-color': ['match', ['get', 'p'], 1, P_COL[0], 2, P_COL[1], 3, P_COL[2], 4, P_COL[3], P_COL[4]],
    'fill-opacity': ['interpolate', ['linear'], ['zoom'], 9, 0.55, 12, 0.28, 14, 0.05]}}, firstLabel);

  // photo years
  const yearX = ['step', ['to-number', ['get', 'captured_at'], 0], Y_BRK[0][1]].concat(Y_BRK.slice(1).flatMap(([y, c]) => [Date.UTC(y, 0, 1), c]));
  map.addSource('mlycov', {type: 'vector', tiles: [`https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}?access_token=${C.MLY}`], minzoom: 6, maxzoom: 14, attribution: 'Photos © Mapillary'});
  map.addLayer({id: 'ph-seq', type: 'line', source: 'mlycov', 'source-layer': 'sequence', minzoom: 11, filter: ['>=', ['to-number', ['get', 'captured_at'], 0], SINCE], layout: {visibility: 'none', 'line-cap': 'round'},
    paint: {'line-color': yearX, 'line-width': ['interpolate', ['linear'], ['zoom'], 11, 1, 17, 4], 'line-opacity': 0.85}}, firstLabel);

  // raw sources: dots when zoomed out; invisible but loaded close in, where the merged layer takes over
  const dot = (id, src, extra, op) => map.addLayer(Object.assign({id: id + '-dot', type: 'circle', source: src, minzoom: 12,
    paint: {'circle-color': SRC[id].c, 'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, 1.8, 15, 3.5],
      'circle-opacity': ['step', ['zoom'], op || 1, ICON_Z, 0], 'circle-stroke-color': '#fff', 'circle-stroke-width': ['step', ['zoom'], 1, ICON_Z, 0]}}, extra));
  const nCounty = agency?.county_signs?.count || 0, nSig = agency?.county_signals?.count || 0;
  if (agency) {
    map.addSource('ag', {type: 'vector', url: 'pmtiles://' + new URL('data/base/agency.pmtiles', location.href).href});
    dot('county', 'ag', {'source-layer': 'signs'});
    map.addLayer({id: 'signals', type: 'circle', source: 'ag', 'source-layer': 'signals', minzoom: 11, layout: {visibility: 'none'},
      paint: {'circle-color': '#FF6622', 'circle-radius': ['interpolate', ['linear'], ['zoom'], 11, 2.5, 18, 7], 'circle-stroke-color': '#fff', 'circle-stroke-width': 1.5}});
    $('#county-dd').textContent = `LA County Public Works sign records, ${nCounty.toLocaleString()} signs in unincorporated areas (downloaded ${agency.county_signs.downloaded}).`;
  }
  if (!nCounty) document.querySelector('[data-layer="county"]').disabled = true;
  if (!nSig) document.querySelector('[data-layer="signals"]').disabled = true;
  const vals = Object.keys(CMAP).filter(v => famKey(CMAP[v].code));
  map.addSource('mlysign', {type: 'vector', tiles: [`https://tiles.mapillary.com/maps/vtp/mly_map_feature_traffic_sign/2/{z}/{x}/{y}?access_token=${C.MLY}`], minzoom: 14, maxzoom: 14});
  dot('mly', 'mlysign', {'source-layer': 'traffic_sign', minzoom: 14, filter: ['all', ['in', ['get', 'value'], ['literal', vals]], ['>=', ['to-number', ['get', 'last_seen_at'], 0], SINCE]]}, 0.8);
  map.addSource('fp', {type: 'geojson', data: {type: 'FeatureCollection', features: FP}});
  dot('fp', 'fp', {});

  // merged signs (one symbol per physical sign)
  map.addSource('signs', {type: 'geojson', data: {type: 'FeatureCollection', features: []}});
  map.addLayer({id: 'signs-halo', type: 'circle', source: 'signs', minzoom: ICON_Z, paint: {
    'circle-radius': ['interpolate', ['linear'], ['zoom'], ICON_Z, 12, 19, 22], 'circle-color': '#fff', 'circle-opacity': 0.9,
    'circle-stroke-color': ['get', 'ring'], 'circle-stroke-width': ['case', ['>', ['get', 'n'], 1], 3.5, 2], 'circle-stroke-opacity': ['get', 'op']}});
  map.addLayer({id: 'signs-face', type: 'symbol', source: 'signs', minzoom: ICON_Z, layout: {'icon-image': ['concat', 'sg:', ['get', 'face']],
    'icon-size': ['interpolate', ['linear'], ['zoom'], ICON_Z, 0.32, 19, 0.55], 'icon-allow-overlap': true, 'icon-anchor': 'center',
    'symbol-sort-key': ['get', 'rank']}, paint: {'icon-opacity': ['get', 'op']}});
  map.addLayer({id: 'signs-n', type: 'symbol', source: 'signs', minzoom: 17, filter: ['>', ['get', 'n'], 1], layout: {'text-field': ['to-string', ['get', 'n']],
    'text-font': ['Noto Sans Bold'], 'text-size': 10, 'text-offset': [1.35, -1.35], 'text-allow-overlap': true},
    paint: {'text-color': '#fff', 'text-halo-color': '#1B795A', 'text-halo-width': 4}});

  // legends and search list
  $('#ramp-tiles').innerHTML = P_COL.map((c, i) => `<span style="background:${c}" class="${i > 1 ? 'dk' : ''}">P${i + 1}</span>`).join('');
  $('#ramp-photos').innerHTML = Y_BRK.map(([, c, t], i) => `<span style="background:${c}" class="${i < 3 ? 'dk' : ''}">${t}</span>`).join('');
  const cs = {};
  for (const f of tiles.features) { const p = f.properties; if (p.city === 'Unincorporated') continue;
    const c = cs[p.city] ||= {name: p.city, rank: 1e9, b: [180, 90, -180, -90]}; c.rank = Math.min(c.rank, p.rank);
    for (const [x, y] of f.geometry.coordinates[0]) { c.b[0] = Math.min(c.b[0], x); c.b[1] = Math.min(c.b[1], y); c.b[2] = Math.max(c.b[2], x); c.b[3] = Math.max(c.b[3], y); } }
  CITIES = Object.values(cs).sort((a, b) => a.rank - b.rank);

  // toggles
  const groups = {tiles: ['tiles-fill'], photos: ['ph-seq'], signals: ['signals'], fp: ['fp-dot'], mly: ['mly-dot'], county: ['county-dot']};
  document.querySelectorAll('.chips button[data-layer]').forEach(b => {
    const apply = () => { vis(groups[b.dataset.layer] || [], b.classList.contains('on')); $('#ramp-tiles').hidden = !on('tiles'); $('#ramp-photos').hidden = !on('photos'); hint(); merge(); };
    b.onclick = () => { if (b.disabled) return; b.classList.toggle('on'); apply(); };
    if (b.disabled) b.classList.remove('on'); apply();
  });
  document.querySelectorAll('[data-base]').forEach(b => b.onclick = () => {
    document.querySelectorAll('[data-base]').forEach(x => x.classList.toggle('on', x === b)); vis(['base-usgs', 'base-esri'], b.dataset.base === 'aerial');
  });
  map.on('moveend', merge); map.on('idle', merge); map.on('zoomend', hint); hint();
});

/* merge the three sources in view: same code family within MERGE_M metres = one sign */
let mergeT, shown = false;
function merge() {
  clearTimeout(mergeT); mergeT = setTimeout(() => {
    if (!map.getSource('signs')) return;
    if (map.getZoom() < ICON_Z) { if (shown) { map.getSource('signs').setData({type: 'FeatureCollection', features: []}); shown = false; } return; }
    const b = map.getBounds(), pad = 0.002, inView = ([x, y]) => x > b.getWest() - pad && x < b.getEast() + pad && y > b.getSouth() - pad && y < b.getNorth() + pad;
    const recs = [];
    if (on('fp')) for (const f of FP) if (inView(f.geometry.coordinates)) { const p = f.properties, k = famKey(p.code);
      recs.push({src: 'fp', ll: f.geometry.coordinates, fam: k, face: faceKey(k, p.val || (String(p.code).match(/\((\d+)\)$/) || [])[1]), p, op: 1}); }
    if (on('county') && map.getSource('ag')) for (const f of map.querySourceFeatures('ag', {sourceLayer: 'signs'})) { const ll = f.geometry.coordinates; if (!inView(ll)) continue;
      const p = f.properties, k = p.key || keyOf(p.code), v = (String(p.desc || '').match(/(\d{2})\s*MPH|LIMIT\s*(\d{2})/i) || []).slice(1).find(Boolean);
      recs.push({src: 'county', ll, fam: k, face: faceKey(k, v), p, op: 1}); }
    if (on('mly') && map.getSource('mlysign')) for (const f of map.querySourceFeatures('mlysign', {sourceLayer: 'traffic_sign'})) { const ll = f.geometry.coordinates; if (!inView(ll)) continue;
      const m = CMAP[f.properties.value]; if (!m || +f.properties.last_seen_at < SINCE) continue; const k = famKey(m.code); if (!k) continue; const t = trustOf(m.code).trust;
      const sure = t === 'likely' || t === 'mixed', ser = seriesOf(k);
      recs.push({src: 'mly', ll, fam: sure ? k : (ser || k), face: sure ? faceKey(k, m.val) : '?' + (ser || k), unsure: !sure, p: f.properties, op: sure ? (t === 'likely' ? 1 : 0.85) : 0.7}); }
    const seen = new Set(), uniq = recs.filter(r => { const id = r.src + (r.p.id ?? r.ll.map(x => x.toFixed(6)).join()); if (seen.has(id)) return false; seen.add(id); return true; });
    uniq.sort((a, b) => ORDER.indexOf(a.src) - ORDER.indexOf(b.src));
    const groups = [];
    for (const r of uniq) {
      const g = groups.find(g => (g.fam === r.fam || (r.unsure && seriesOf(g.fam) === r.fam)) && !g.recs.some(x => x.src === r.src && r.src !== 'mly') && metres(g.ll, r.ll) < MERGE_M);
      if (g) g.recs.push(r); else groups.push({fam: r.fam, ll: r.ll, recs: [r]});
    }
    RAW = new Map(); const feats = groups.map((g, i) => { RAW.set(i, g); const top = g.recs[0], n = new Set(g.recs.map(r => r.src)).size;
      const sure = g.recs.filter(r => !r.unsure), faceK = (sure.find(r => r.face.includes('@') && !r.face.endsWith('@?')) || sure[0] || top).face; face(faceK);
      return {type: 'Feature', geometry: {type: 'Point', coordinates: top.ll}, properties: {gid: i, face: faceK, ring: SRC[top.src].c, n, op: n > 1 ? 1 : top.op, rank: ORDER.indexOf(top.src)}}; });
    shown = true; map.getSource('signs').setData({type: 'FeatureCollection', features: feats});
  }, 120);
}

function hint() {
  const any = ['fp', 'mly', 'county'].some(on), z = map.getZoom(); $('#hint').hidden = !(any && z < ICON_Z);
  $('#hint').textContent = z < 12 ? 'Zoom in to see signs' : 'Zoom in closer to see sign faces';
}

/* panel and search */
const narrow = () => innerWidth < 700;
const fold = f => { $('#panel').classList.toggle('folded', f); $('#fold').textContent = f ? '+' : '–'; };
if (narrow()) fold(true);
$('#fold').onclick = () => fold(!$('#panel').classList.contains('folded'));
let qT;
$('#q').oninput = () => { clearTimeout(qT); qT = setTimeout(search, 300); };
$('#q').onkeydown = e => { if (e.key === 'Enter') { const b = $('#hits button'); if (b) b.click(); } };
async function search() {
  const q = $('#q').value.trim(), box = $('#hits'); if (q.length < 2) { box.hidden = true; return; }
  const local = CITIES.filter(c => c.name.toLowerCase().includes(q.toLowerCase())).slice(0, 4);
  let geo = [];
  if (q.length > 3) try { geo = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=5&bounded=1&viewbox=-118.95,34.83,-117.64,33.70&q=${encodeURIComponent(q)}`).then(r => r.json()); } catch (e) {}
  box.innerHTML = local.map((c, i) => `<button data-c="${i}">${esc(c.name)} <small>city</small></button>`).join('') +
    geo.map((g, i) => `<button data-g="${i}">${esc(g.display_name.split(',').slice(0, 3).join(','))}</button>`).join('') || '<button disabled>No match</button>';
  box.hidden = false;
  box.querySelectorAll('[data-c]').forEach(b => b.onclick = () => { map.fitBounds(local[+b.dataset.c].b, {padding: 40}); box.hidden = true; if (narrow()) fold(true); });
  box.querySelectorAll('[data-g]').forEach(b => b.onclick = () => { const g = geo[+b.dataset.g]; map.flyTo({center: [+g.lon, +g.lat], zoom: 18}); box.hidden = true; if (narrow()) fold(true); });
}
document.addEventListener('click', e => { if (!e.target.closest('.search')) $('#hits').hidden = true; });

/* clicks */
$('#close').onclick = () => { $('#card').hidden = true; if (map.getSource('sel')) map.getSource('sel').setData({type: 'FeatureCollection', features: []}); };
map.on('click', e => {
  if (window.dataHit && window.dataHit(e)) return;
  const box = [[e.point.x - 10, e.point.y - 10], [e.point.x + 10, e.point.y + 10]];
  const g = map.getLayer('signs-face') && map.queryRenderedFeatures(box, {layers: ['signs-face', 'signs-halo']})[0];
  if (g) return openCard(RAW.get(g.properties.gid));
  const d = ['fp-dot', 'county-dot', 'mly-dot'].filter(id => map.getLayer(id) && map.getLayoutProperty(id, 'visibility') !== 'none');
  if (map.getZoom() < ICON_Z && d.length && map.queryRenderedFeatures(box, {layers: d}).length) return map.flyTo({center: e.lngLat, zoom: 17.5});
  const t = map.getLayer('tiles-fill') && map.getLayoutProperty('tiles-fill', 'visibility') !== 'none' && map.getZoom() < 15 && map.queryRenderedFeatures(e.point, {layers: ['tiles-fill']})[0];
  if (t) { const p = t.properties;
    new maplibregl.Popup({maxWidth: '240px'}).setLngLat(e.lngLat).setHTML(`<b>${esc(p.city)}</b> · P${p.p}<br><small>Build order #${p.rank.toLocaleString()} of 8,717 · ${p.art} km arterials · ${(p.jobs + p.res).toLocaleString()} jobs and residents</small>`).addTo(map); }
});
['signs-face', 'signs-halo'].forEach(id => { map.on('mouseenter', id, () => map.getCanvas().style.cursor = 'pointer'); map.on('mouseleave', id, () => map.getCanvas().style.cursor = ''); });

/* sign card: the sign, its photo, and every source that has it */
function codeOf(r) {
  if (r.src === 'fp') return {code: String(r.p.code || '').replace(/\s*\(\d+\)$/, ''), val: r.p.val || (String(r.p.code).match(/\((\d+)\)$/) || [])[1] || ''};
  if (r.src === 'mly') { const m = CMAP[r.p.value] || {}; return {code: String(m.code || '').split('/')[0], val: m.val || ''}; }
  return {code: r.p.code || '', val: r.face.includes('@') ? r.face.split('@')[1].replace('?', '') : ''};
}
function srcRow(r) {
  const {code, val} = codeOf(r), cv = esc(code) + (val ? ` (${esc(val)})` : '');
  if (r.src === 'fp') return [cv, `${r.p.status === 'review' ? 'check in field' : 'high confidence'}${r.p.conf ? ', ' + Math.round(r.p.conf * 100) + '%' : ''} · photo ${esc(r.p.seen)}`];
  if (r.src === 'mly') { const t = trustOf(code); const TT = {likely: 'code usually right', mixed: 'code sometimes wrong', low: 'code often wrong', untested: 'code not yet tested'};
    return [cv, `${TT[t.trust]} · seen ${day(r.p.first_seen_at)}${r.p.last_seen_at && day(r.p.last_seen_at) !== day(r.p.first_seen_at) ? ' to ' + day(r.p.last_seen_at) : ''}`]; }
  return [cv, [r.p.desc, r.p.dir && 'faces ' + r.p.dir, r.p.status && String(r.p.status).toLowerCase(), r.p.date].filter(Boolean).map(esc).join(' · ')];
}
function openCard(g) {
  if (!g) return; const top = g.recs[0], [lon, lat] = top.ll;
  const sureRecs = g.recs.filter(r => !r.unsure), best = sureRecs.find(r => r.face.includes('@') && !r.face.endsWith('@?')) || sureRecs[0] || top;
  const unsure = !sureRecs.length;
  const {code, val} = codeOf(best), k = famKey(code), cc = county(k);
  const info = cc ? {name: `${cc.name} · county code ${code}`, slug: cc.slug, svg: cc.slug && IDX[cc.slug]?.svg, note: cc.note, draw: cc.face.startsWith('draw:') && cc.face.slice(5)} : (IDX[resolve(k) || k] || IDX[k] || {});
  const serName = SERIES[seriesOf(k)] || 'Sign';
  if (unsure) { info.name = `${serName} sign. Mapillary's label (${code}) is often wrong for this kind of sign; check the photo.`; info.slug = null; info.svg = null; }
  const art = unsure ? `<b>?</b>` : info.draw ? `<img src="data:image/svg+xml;charset=utf-8,${encodeURIComponent(drawSVG(info.draw))}" alt="">` : NUMERIC.includes(k) ? `<img src="data:image/svg+xml;charset=utf-8,${encodeURIComponent(speedSVG(k, val || '?'))}" alt="">`
    : info.svg ? `<img src="${SSS}${info.svg}" alt="">` : `<b>${esc(code)}</b>`;
  const srcs = [...new Set(g.recs.map(r => r.src))];
  const agree = srcs.length > 1 ? `<span class="badge lt">${srcs.length} SOURCES AGREE</span>` : '';
  const fpRec = g.recs.find(r => r.src === 'fp' && r.p.crop), mRec = g.recs.find(r => r.src === 'mly');
  const photo = fpRec ? `<div class="photo"><img src="${esc(fpRec.p.crop)}" alt="Sign photo"><div class="cap">${age(Date.parse(fpRec.p.seen) || Date.now())}Photo ${esc(fpRec.p.seen)} · read by our sign model</div></div>`
    : `<div class="photo" id="ph"><div class="msg">Loading photo…</div></div>`;
  $('#card-body').innerHTML = `<div class="sc-head"><div class="sc-art">${art}</div><div><div class="sc-code">${unsure ? esc(serName) + ' sign' : esc(code || 'No code') + (val ? ` <span style="font-weight:500">(${esc(val)})</span>` : '')}</div>
    <div class="sc-name">${esc(info.name || (top.src === 'county' ? top.p.desc : '') || '')}</div></div></div>${info.note ? `<p class="note-x">${esc(info.note)}</p>` : ''}
    <div class="badges">${srcs.map(s => `<span class="badge" style="--c:${SRC[s].c}">${SRC[s].t.toUpperCase()}</span>`).join('')}${agree}${unsure ? '<span class="badge warn">CODE NOT CONFIRMED</span>' : ''}</div>${photo}
    ${top.src === 'mly' ? '<p class="note-x">Position estimated by Mapillary from the photos; it can be several meters off.</p>' : ''}
    <table class="facts">${g.recs.map(r => { const [a, b] = srcRow(r); return `<tr><td><b style="color:${SRC[r.src].c}">${SRC[r.src].t}</b><br>${a}</td><td>${b}</td></tr>`; }).join('')}</table>
    <div class="links">${info.slug ? `<a href="${SSS}/signs/${info.slug}/" target="_blank" rel="noopener">Standard</a>` : ''}<a href="${sv(lat, lon)}" target="_blank" rel="noopener">Street View</a><a href="${mlyAt(lat, lon)}" target="_blank" rel="noopener">Mapillary</a></div>`;
  $('#card').hidden = false; if (narrow()) fold(true);
  if (!map.getSource('sel')) { map.addSource('sel', {type: 'geojson', data: {type: 'FeatureCollection', features: []}});
    map.addLayer({id: 'sel', type: 'circle', source: 'sel', paint: {'circle-radius': 26, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#FF6622', 'circle-stroke-width': 3}}); }
  map.getSource('sel').setData({type: 'Feature', geometry: {type: 'Point', coordinates: [lon, lat]}, properties: {}});
  if (!fpRec) mRec ? mlyPhoto(mRec.p.id) : nearPhoto(lon, lat);
}
const age = ms => { const y = (Date.now() - ms) / 3.156e10; return y >= 4 ? `<b class="old">${Math.floor(y)} years old, may be out of date.</b> ` : ''; };
async function mlyPhoto(id) {
  const box = $('#ph'); if (!box) return;
  try {
    const d = (await graph(`${id}/detections`, 'fields=image,geometry')).data || []; if (!d.length) throw 0;
    const ims = await Promise.all(d.slice(0, 6).map(x => graph(x.image.id, 'fields=thumb_1024_url,captured_at,width,height').then(i => ({i, g: x.geometry}))));
    const pick = ims.filter(x => x.i.thumb_1024_url && x.i.captured_at >= SINCE); if (!pick.length) { box.innerHTML = '<div class="msg">No photo of this sign since 2021</div>'; return; }
    const {i, g} = pick.sort((a, b) => b.i.captured_at - a.i.captured_at)[0];
    const bb = mvtBox(g), iw = 1024, ih = Math.round(1024 * i.height / i.width), W = box.clientWidth || 308, H = 170, pad = 2.2;
    const bw = Math.max(bb[2] - bb[0], 0.01) * iw * pad, bh = Math.max(bb[3] - bb[1], 0.01) * ih * pad;
    const s = Math.min(W / bw, H / bh, 3), cx = (bb[0] + bb[2]) / 2 * iw * s, cy = (bb[1] + bb[3]) / 2 * ih * s;
    box.innerHTML = `<a href="${esc(i.thumb_1024_url)}" target="_blank" rel="noopener"><div class="crop" style="background-image:url('${i.thumb_1024_url}');background-size:${iw * s}px ${ih * s}px;background-position:${W / 2 - cx}px ${H / 2 - cy}px"></div></a>
      <div class="cap">${age(i.captured_at)}Photo ${day(i.captured_at)} · ${d.length} photo${d.length > 1 ? 's' : ''} saw this sign · tap for the full photo</div>`;
  } catch (e) { box.innerHTML = '<div class="msg">No photo available for this detection</div>'; }
}
async function nearPhoto(lon, lat) {
  const box = $('#ph'); if (!box) return; const r = 0.00025;
  try {
    const d = (await graph('images', `fields=thumb_1024_url,captured_at&limit=10&start_captured_at=${SINCE_ISO}&bbox=${lon - r},${lat - r},${lon + r},${lat + r}`)).data || [];
    const i = d.sort((a, b) => b.captured_at - a.captured_at)[0]; if (!i) throw 0;
    box.innerHTML = `<a href="${esc(i.thumb_1024_url)}" target="_blank" rel="noopener"><img src="${esc(i.thumb_1024_url)}" alt="Nearest street photo"></a><div class="cap">${age(i.captured_at)}Nearest street photo, ${day(i.captured_at)} (not matched to this sign)</div>`;
  } catch (e) { box.innerHTML = '<div class="msg">No street photo within 25 m since 2021</div>'; }
}
function mvtBox(b64) {
  const u = Uint8Array.from(atob(b64), c => c.charCodeAt(0)); let ext = 4096; const pts = [];
  const rd = (b, o) => { let v = 0, s = 0, c; do { c = b[o.i++]; v += (c & 0x7f) * 2 ** s; s += 7; } while (c & 0x80); return v; };
  const walk = (b, fn) => { const o = {i: 0}; while (o.i < b.length) { const t = rd(b, o), f = t >>> 3, w = t & 7;
    if (w === 2) { const n = rd(b, o); fn(f, b.subarray(o.i, o.i + n)); o.i += n; } else if (w === 0) fn(f, rd(b, o)); else if (w === 5) o.i += 4; else if (w === 1) o.i += 8; } };
  walk(u, (f, layer) => { if (f !== 3) return; walk(layer, (lf, v) => { if (lf === 5) ext = v; if (lf !== 2) return; walk(v, (ff, g) => { if (ff !== 4) return;
    const o = {i: 0}; let x = 0, y = 0; while (o.i < g.length) { const c = rd(g, o), id = c & 7, n = c >>> 3; if (id === 7) continue;
      for (let k = 0; k < n; k++) { const dx = rd(g, o), dy = rd(g, o); x += (dx >>> 1) ^ -(dx & 1); y += (dy >>> 1) ^ -(dy & 1); pts.push([x, y]); } } }); }); });
  if (!pts.length) return [0.4, 0.4, 0.6, 0.6];
  const xs = pts.map(p => p[0] / ext), ys = pts.map(p => p[1] / ext);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}
