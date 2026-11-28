/* LA County street inventory map.
   Signs from three sources drawn as their sign faces (artwork from the standards site), a card per sign with its photo,
   build-order tiles, photo years and signals as context. */
const C = window.CFG, $ = s => document.querySelector(s), V = '?v=' + (C.DATA_V || 1);
const SSS = 'https://drzkid96.github.io/SoCal-Super-Standards';
const SRC = {fp: {c: '#1B795A', t: 'SCANNED'}, mly: {c: '#568CBB', t: 'INSTANT'}, county: {c: '#00242E', t: 'COUNTY RECORD'}};
const P_COL = ['#00574A', '#1B795A', '#6BD688', '#B9E6B4', '#E4EFE2'];
const Y_BRK = [[0, '#C9D3D5', '<2018'], [2018, '#9FB3B8', '18-19'], [2020, '#6BD688', '20-21'], [2022, '#1B795A', '22-23'], [2024, '#00242E', '2024+']];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const day = ms => ms ? new Date(+ms).toISOString().slice(0, 10) : '';
const keyOf = c => String(c || '').toLowerCase().replace(/[() ]/g, '');
const famKey = c => keyOf(String(c || '').split('/')[0].replace(/\s*\(\d+\)\s*$/, ''));
const sv = (lat, lon) => `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat.toFixed(6)},${lon.toFixed(6)}`;
const mlyAt = (lat, lon) => `https://www.mapillary.com/app/?lat=${lat.toFixed(6)}&lng=${lon.toFixed(6)}&z=19`;
const graph = (path, q = '') => fetch(`https://graph.mapillary.com/${path}${path.includes('?') ? '&' : '?'}${q}&access_token=${encodeURIComponent(C.MLY)}`).then(r => r.json());

const proto = new pmtiles.Protocol(); maplibregl.addProtocol('pmtiles', proto.tile);
const map = new maplibregl.Map({
  container: 'map', center: [-118.25, 34.05], zoom: 9.3, minZoom: 8, maxZoom: 20.5, hash: true, attributionControl: {compact: true},
  style: {version: 8, glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf', sources: {
    osm: {type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256, maxzoom: 19, attribution: '© OpenStreetMap contributors'},
    usgs: {type: 'raster', tiles: ['https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 16, attribution: 'USGS'},
    esri: {type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 20, attribution: 'Imagery © Esri'}},
    layers: [{id: 'base-map', type: 'raster', source: 'osm', paint: {'raster-saturation': -0.9, 'raster-brightness-min': 0.15, 'raster-contrast': -0.15}},
             {id: 'base-usgs', type: 'raster', source: 'usgs', maxzoom: 15, layout: {visibility: 'none'}},
             {id: 'base-esri', type: 'raster', source: 'esri', minzoom: 15, layout: {visibility: 'none'}}]},
});
map.addControl(new maplibregl.NavigationControl({showCompass: false}), 'bottom-right');
map.addControl(new maplibregl.GeolocateControl({positionOptions: {enableHighAccuracy: true}}), 'bottom-right');
map.addControl(new maplibregl.ScaleControl({unit: 'imperial'}), 'bottom-left');

let IDX = {}, CMAP = {}, TRUST = {}, CITIES = [];
const groups = {tiles: ['tiles-fill', 'tiles-line'], photos: ['ph-seq'], signals: ['signals'],
  fp: ['fp-dot', 'fp-ico'], mly: ['mly-dot', 'mly-ico'], county: ['county-dot', 'county-ico']};
const SIGN_LAYERS = ['fp-ico', 'fp-dot', 'county-ico', 'county-dot', 'mly-ico', 'mly-dot'];
const vis = (ids, on) => ids.forEach(id => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none'));

/* sign face images: 'sg:<key>' from the icon set, or a plain code tag when there is no artwork */
const resolve = k => IDX[k]?.icon ? k : IDX[k + 'ca']?.icon ? k + 'ca' : null;
function tag(text) {
  const s = 2, f = 13 * s, cv = document.createElement('canvas'), x = cv.getContext('2d');
  x.font = `700 ${f}px Albert Sans, sans-serif`; const w = Math.ceil(x.measureText(text).width) + 12 * s, h = f + 10 * s;
  cv.width = w; cv.height = h; x.font = `700 ${f}px Albert Sans, sans-serif`;
  x.fillStyle = '#fff'; x.strokeStyle = '#00242E'; x.lineWidth = 2 * s; x.beginPath(); x.roundRect(s, s, w - 2 * s, h - 2 * s, 4 * s); x.fill(); x.stroke();
  x.fillStyle = '#00242E'; x.textAlign = 'center'; x.textBaseline = 'middle'; x.fillText(text, w / 2, h / 2 + s);
  return {width: w, height: h, data: new Uint8Array(x.getImageData(0, 0, w, h).data.buffer)};
}
async function loadIcons(keys) {
  await Promise.all([...new Set(keys)].filter(k => k && !map.hasImage('sg:' + k)).map(async k => {
    const r = resolve(k);
    try {
      if (!r) throw 0;
      const img = await map.loadImage(`assets/signs/${r}.png`);
      if (!map.hasImage('sg:' + k)) map.addImage('sg:' + k, img.data, {pixelRatio: 2});
    } catch (e) { if (!map.hasImage('sg:' + k)) map.addImage('sg:' + k, tag((IDX[k]?.code || k).toUpperCase()), {pixelRatio: 2}); }
  }));
}
map.on('styleimagemissing', e => { if (e.id.startsWith('sg:') && !map.hasImage(e.id)) map.addImage(e.id, tag(e.id.slice(3).toUpperCase() || '?'), {pixelRatio: 2}); });

/* one source of signs = a dot (always) + its sign face (close in) */
function signLayers(id, src, extra, iconX, opacityX) {
  const color = SRC[id].c;
  map.addLayer(Object.assign({id: id + '-dot', type: 'circle', source: src, minzoom: 13,
    paint: {'circle-color': color, 'circle-opacity': opacityX || 1, 'circle-stroke-opacity': opacityX || 1,
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 13, 2.2, 16, 4, 19, 6], 'circle-stroke-color': '#fff', 'circle-stroke-width': 1.2}}, extra));
  map.addLayer(Object.assign({id: id + '-ico', type: 'symbol', source: src, minzoom: 15.5,
    layout: {'icon-image': iconX, 'icon-size': ['interpolate', ['linear'], ['zoom'], 15.5, 0.42, 18, 0.7, 20, 0.95],
      'icon-allow-overlap': false, 'icon-padding': 1, 'icon-anchor': 'bottom', 'icon-offset': [0, -4]},
    paint: {'icon-opacity': opacityX || 1}}, extra));
}

map.on('load', async () => {
  const get = (u, d) => fetch(u + V).then(r => r.ok ? r.json() : d).catch(() => d);
  const [tiles, idx, cmap, trust, agency] = await Promise.all([get('data/base/tiles.geojson', {features: []}), get('assets/signs/index.json', {}),
    get('data/classmap.json', {}), get('data/base/trust.json', {codes: {}}), get('data/base/agency.json', null)]);
  IDX = idx; CMAP = cmap; TRUST = trust.codes || {};

  // build order tiles
  map.addSource('tiles', {type: 'geojson', data: tiles});
  map.addLayer({id: 'tiles-fill', type: 'fill', source: 'tiles', paint: {'fill-color': ['match', ['get', 'p'], 1, P_COL[0], 2, P_COL[1], 3, P_COL[2], 4, P_COL[3], P_COL[4]],
    'fill-opacity': ['interpolate', ['linear'], ['zoom'], 9, 0.6, 12, 0.3, 14, 0.06, 15, 0]}});
  map.addLayer({id: 'tiles-line', type: 'line', source: 'tiles', minzoom: 11, maxzoom: 15, paint: {'line-color': '#fff', 'line-width': 0.6, 'line-opacity': 0.6}});

  // photo years (Mapillary sequences)
  const yearX = ['step', ['to-number', ['get', 'captured_at'], 0], Y_BRK[0][1]].concat(Y_BRK.slice(1).flatMap(([y, c]) => [Date.UTC(y, 0, 1), c]));
  map.addSource('mlycov', {type: 'vector', tiles: [`https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}?access_token=${C.MLY}`], minzoom: 6, maxzoom: 14, attribution: 'Photos © Mapillary'});
  map.addLayer({id: 'ph-seq', type: 'line', source: 'mlycov', 'source-layer': 'sequence', minzoom: 11, layout: {visibility: 'none', 'line-cap': 'round'},
    paint: {'line-color': yearX, 'line-width': ['interpolate', ['linear'], ['zoom'], 11, 1, 17, 4], 'line-opacity': 0.9}});

  // county records and signals
  const nCounty = agency?.county_signs?.count || 0, nSig = agency?.county_signals?.count || 0;
  if (agency) {
    map.addSource('ag', {type: 'vector', url: 'pmtiles://' + new URL('data/base/agency.pmtiles', location.href).href});
    signLayers('county', 'ag', {'source-layer': 'signs'}, ['concat', 'sg:', ['coalesce', ['get', 'key'], ['downcase', ['get', 'code']]]]);
    map.addLayer({id: 'signals', type: 'circle', source: 'ag', 'source-layer': 'signals', minzoom: 11, layout: {visibility: 'none'},
      paint: {'circle-color': '#FF6622', 'circle-radius': ['interpolate', ['linear'], ['zoom'], 11, 2.5, 18, 7], 'circle-stroke-color': '#fff', 'circle-stroke-width': 1.5}});
    $('#county-dd').textContent = `LA County Public Works inventory, ${nCounty.toLocaleString()} signs in unincorporated areas (downloaded ${agency.county_signs.downloaded}).`;
  }
  if (!nCounty) document.querySelector('[data-layer="county"]').disabled = true;
  if (!nSig) document.querySelector('[data-layer="signals"]').disabled = true;

  // instant (Mapillary detections, code translated, faded by trust)
  const iconOf = {}, trustOf = {likely: [], mixed: []};
  for (const [v, m] of Object.entries(CMAP)) {
    const k = famKey(m.code); if (!k) continue; iconOf[v] = k;
    const t = (TRUST[String(m.code).split('/')[0].split('(')[0].trim()] || {}).trust; if (trustOf[t]) trustOf[t].push(v);
  }
  const vals = Object.keys(iconOf);
  const mIcon = vals.length ? ['match', ['get', 'value'], ...vals.flatMap(v => [v, 'sg:' + iconOf[v]]), 'sg:'] : 'sg:';
  const mOp = ['match', ['get', 'value']]; if (trustOf.likely.length) mOp.push(trustOf.likely, 1); if (trustOf.mixed.length) mOp.push(trustOf.mixed, 0.75); mOp.push(0.4);
  map.addSource('mlysign', {type: 'vector', tiles: [`https://tiles.mapillary.com/maps/vtp/mly_map_feature_traffic_sign/2/{z}/{x}/{y}?access_token=${C.MLY}`], minzoom: 14, maxzoom: 14});
  signLayers('mly', 'mlysign', {'source-layer': 'traffic_sign', filter: ['in', ['get', 'value'], ['literal', vals]]}, mIcon, mOp);

  // scanned (our model)
  const fp = await get('data/base/fp.geojson', {type: 'FeatureCollection', features: []});
  fp.features = fp.features.filter(f => !f.properties.name);
  fp.features.forEach(f => f.properties.key = f.properties.key || famKey(f.properties.code));
  map.addSource('fp', {type: 'geojson', data: fp});
  signLayers('fp', 'fp', {}, ['concat', 'sg:', ['get', 'key']]);

  await loadIcons([...Object.values(iconOf), ...fp.features.map(f => f.properties.key), ...(agency?.county_signs?.keys || [])]);

  // legends
  $('#ramp-tiles').innerHTML = P_COL.map((c, i) => `<span style="background:${c}" class="${i > 1 ? 'dk' : ''}">P${i + 1}</span>`).join('');
  $('#ramp-photos').innerHTML = Y_BRK.map(([, c, t], i) => `<span style="background:${c}" class="${i < 3 ? 'dk' : ''}">${t}</span>`).join('');

  // cities for search
  const cs = {};
  for (const f of tiles.features) {
    const p = f.properties; if (p.city === 'Unincorporated') continue;
    const c = cs[p.city] ||= {name: p.city, rank: 1e9, b: [180, 90, -180, -90]}; c.rank = Math.min(c.rank, p.rank);
    for (const [x, y] of f.geometry.coordinates[0]) { c.b[0] = Math.min(c.b[0], x); c.b[1] = Math.min(c.b[1], y); c.b[2] = Math.max(c.b[2], x); c.b[3] = Math.max(c.b[3], y); }
  }
  CITIES = Object.values(cs).sort((a, b) => a.rank - b.rank);

  // toggles
  document.querySelectorAll('.chips button[data-layer]').forEach(b => {
    const apply = () => { vis(groups[b.dataset.layer] || [], b.classList.contains('on')); if (b.dataset.layer === 'tiles') $('#ramp-tiles').hidden = !b.classList.contains('on');
      if (b.dataset.layer === 'photos') $('#ramp-photos').hidden = !b.classList.contains('on'); hint(); };
    b.onclick = () => { if (b.disabled) return; b.classList.toggle('on'); apply(); };
    if (b.disabled) b.classList.remove('on'); apply();
  });
  document.querySelectorAll('[data-base]').forEach(b => b.onclick = () => {
    document.querySelectorAll('[data-base]').forEach(x => x.classList.toggle('on', x === b));
    const a = b.dataset.base === 'aerial'; vis(['base-usgs', 'base-esri'], a); vis(['base-map'], !a);
  });
  map.on('zoomend', hint); hint();
});

function hint() {
  const on = ['fp', 'mly', 'county'].some(k => document.querySelector(`[data-layer="${k}"]`)?.classList.contains('on'));
  const z = map.getZoom(); $('#hint').hidden = !(on && z < 15.5);
  $('#hint').textContent = z < 13 ? 'Zoom in to see signs' : 'Zoom in closer to see sign faces';
}

/* panel: fold and search */
$('#fold').onclick = () => { $('#panel').classList.toggle('folded'); $('#fold').textContent = $('#panel').classList.contains('folded') ? '+' : '–'; };
let qT;
$('#q').oninput = () => { clearTimeout(qT); qT = setTimeout(search, 300); };
$('#q').onkeydown = e => { if (e.key === 'Enter') { const b = $('#hits button'); if (b) b.click(); } };
async function search() {
  const q = $('#q').value.trim(), box = $('#hits'); if (q.length < 2) { box.hidden = true; return; }
  const ql = q.toLowerCase(), local = CITIES.filter(c => c.name.toLowerCase().includes(ql)).slice(0, 4);
  let geo = [];
  if (q.length > 3) try {
    geo = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=5&bounded=1&viewbox=-118.95,34.83,-117.64,33.70&q=${encodeURIComponent(q)}`).then(r => r.json());
  } catch (e) {}
  box.innerHTML = local.map((c, i) => `<button data-c="${i}">${esc(c.name)} <small>city</small></button>`).join('') +
    geo.map((g, i) => `<button data-g="${i}">${esc(g.display_name.split(',').slice(0, 3).join(','))}</button>`).join('') || '<button disabled>No match</button>';
  box.hidden = false;
  box.querySelectorAll('[data-c]').forEach(b => b.onclick = () => { map.fitBounds(local[+b.dataset.c].b, {padding: 40}); box.hidden = true; });
  box.querySelectorAll('[data-g]').forEach(b => b.onclick = () => { const g = geo[+b.dataset.g]; map.flyTo({center: [+g.lon, +g.lat], zoom: 17.5}); box.hidden = true; });
}
document.addEventListener('click', e => { if (!e.target.closest('.search')) $('#hits').hidden = true; });

/* sign card */
$('#close').onclick = () => { $('#card').hidden = true; if (map.getSource('sel')) map.getSource('sel').setData({type: 'FeatureCollection', features: []}); };
map.on('click', e => {
  const L = SIGN_LAYERS.filter(id => map.getLayer(id) && map.getLayoutProperty(id, 'visibility') !== 'none');
  const hit = map.queryRenderedFeatures([[e.point.x - 8, e.point.y - 8], [e.point.x + 8, e.point.y + 8]], {layers: L});
  const order = ['fp', 'county', 'mly'];
  const f = hit.sort((a, b) => order.indexOf(a.layer.id.split('-')[0]) - order.indexOf(b.layer.id.split('-')[0]))[0];
  if (f) return openCard(f.layer.id.split('-')[0], f);
  const t = map.getLayer('tiles-fill') && map.getLayoutProperty('tiles-fill', 'visibility') !== 'none' && map.getZoom() < 14 && map.queryRenderedFeatures(e.point, {layers: ['tiles-fill']})[0];
  if (t) { const p = t.properties;
    new maplibregl.Popup({maxWidth: '240px'}).setLngLat(e.lngLat).setHTML(`<b>${esc(p.city)}</b> · P${p.p}<br><small>Build order #${p.rank.toLocaleString()} of 8,717 · ${p.art} km arterials · ${(p.jobs + p.res).toLocaleString()} jobs and residents</small>`).addTo(map); }
});
SIGN_LAYERS.forEach(id => { map.on('mouseenter', id, () => map.getCanvas().style.cursor = 'pointer'); map.on('mouseleave', id, () => map.getCanvas().style.cursor = ''); });

function openCard(src, f) {
  const p = f.properties, [lon, lat] = f.geometry.coordinates;
  let code = '', val = '', badges = [], facts = {}, photo = '';
  if (src === 'fp') {
    code = String(p.code || '').replace(/\s*\(\d+\)$/, ''); val = p.val || (String(p.code).match(/\((\d+)\)$/) || [])[1] || '';
    badges = [`<span class="badge" style="--c:${SRC.fp.c}">${SRC.fp.t}</span>`, p.status === 'review' ? '<span class="badge warn">CHECK IN FIELD</span>' : '<span class="badge lt">HIGH CONFIDENCE</span>'];
    facts = {Location: p.loc, Photo: p.seen, Confidence: p.conf ? Math.round(p.conf * 100) + '%' : '', Area: p.area};
    photo = p.crop ? `<div class="photo"><img src="${esc(p.crop)}" alt="Sign photo"><div class="cap">Photo ${esc(p.seen)} · read by our sign model</div></div>` : '';
  } else if (src === 'mly') {
    const m = CMAP[p.value] || {}; code = String(m.code || '').split('/')[0]; val = m.val || '';
    const t = TRUST[code.split('(')[0].trim()] || {trust: 'untested'};
    const TT = {likely: ['badge lt', 'CODE USUALLY RIGHT'], mixed: ['badge warn', 'CODE SOMETIMES WRONG'], low: ['badge warn', 'CODE OFTEN WRONG'], untested: ['badge warn', 'CODE NOT YET TESTED']};
    badges = [`<span class="badge" style="--c:${SRC.mly.c}">${SRC.mly.t}</span>`, `<span class="${TT[t.trust][0]}">${TT[t.trust][1]}</span>`];
    facts = {'First seen': day(p.first_seen_at), 'Last seen': day(p.last_seen_at), Agreement: t.found != null ? `Matched ${Math.round(t.found * 100)}% of ${t.ours} scanned ${code} signs` : '', Detected: String(p.value).replace(/--/g, ' · ').replace(/-/g, ' ')};
    photo = `<div class="photo" id="ph"><div class="msg">Loading photo…</div></div>`;
  } else {
    code = p.code || ''; badges = [`<span class="badge" style="--c:${SRC.county.c}">${SRC.county.t}</span>`, p.status ? `<span class="badge lt">${esc(String(p.status).toUpperCase())}</span>` : ''];
    facts = {Description: p.desc, Location: p.loc, Facing: p.dir, Date: p.date, Source: p.src};
    photo = `<div class="photo" id="ph"><div class="msg">Looking for the nearest street photo…</div></div>`;
  }
  const k = famKey(code), info = IDX[resolve(k) || k] || IDX[k] || {};
  const art = info.svg ? `<img src="${SSS}${info.svg}" alt="${esc(code)}">` : `<b>${esc(code)}</b>`;
  $('#card-body').innerHTML = `<div class="sc-head"><div class="sc-art">${art}</div><div><div class="sc-code">${esc(code || 'No code')}${val ? ` <span style="font-weight:500">(${esc(val)})</span>` : ''}</div>
    <div class="sc-name">${esc(info.name || '')}</div></div></div><div class="badges">${badges.join('')}</div>${photo}
    <table class="facts">${Object.entries(facts).filter(([, v]) => v).map(([k_, v]) => `<tr><td>${k_}</td><td>${esc(v)}</td></tr>`).join('')}</table>
    <div class="links">${info.slug ? `<a href="${SSS}/signs/${info.slug}/" target="_blank" rel="noopener">Standard</a>` : ''}<a href="${sv(lat, lon)}" target="_blank" rel="noopener">Street View</a><a href="${mlyAt(lat, lon)}" target="_blank" rel="noopener">Mapillary</a></div>`;
  $('#card').hidden = false;
  if (!map.getSource('sel')) { map.addSource('sel', {type: 'geojson', data: {type: 'FeatureCollection', features: []}});
    map.addLayer({id: 'sel', type: 'circle', source: 'sel', paint: {'circle-radius': 14, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#FF6622', 'circle-stroke-width': 3}}); }
  map.getSource('sel').setData({type: 'Feature', geometry: {type: 'Point', coordinates: [lon, lat]}, properties: {}});
  if (src === 'mly') mlyPhoto(p.id); if (src === 'county') nearPhoto(lon, lat);
}

/* Mapillary: newest photo that saw this sign, cropped to the sign with CSS */
async function mlyPhoto(id) {
  const box = $('#ph'); if (!box) return;
  try {
    const d = (await graph(`${id}/detections`, 'fields=image,geometry')).data || [];
    if (!d.length) throw 0;
    const ims = await Promise.all(d.slice(0, 6).map(x => graph(x.image.id, 'fields=thumb_1024_url,captured_at,width,height').then(i => ({i, g: x.geometry}))));
    const {i, g} = ims.filter(x => x.i.thumb_1024_url).sort((a, b) => b.i.captured_at - a.i.captured_at)[0];
    const bb = mvtBox(g); const iw = 1024, ih = Math.round(1024 * i.height / i.width);
    const W = box.clientWidth || 308, H = 170, pad = 2.2;
    const bw = Math.max(bb[2] - bb[0], 0.01) * iw * pad, bh = Math.max(bb[3] - bb[1], 0.01) * ih * pad;
    const s = Math.min(W / bw, H / bh, 3), cx = (bb[0] + bb[2]) / 2 * iw * s, cy = (bb[1] + bb[3]) / 2 * ih * s;
    box.innerHTML = `<a href="${esc(i.thumb_1024_url)}" target="_blank" rel="noopener"><div class="crop" style="background-image:url('${i.thumb_1024_url}');background-size:${iw * s}px ${ih * s}px;background-position:${W / 2 - cx}px ${H / 2 - cy}px"></div></a>
      <div class="cap">Photo ${day(i.captured_at)} · ${d.length} photo${d.length > 1 ? 's' : ''} saw this sign · tap for the full photo</div>`;
  } catch (e) { box.innerHTML = '<div class="msg">No photo available for this detection</div>'; }
}
/* County records carry no photo: show the nearest street photo */
async function nearPhoto(lon, lat) {
  const box = $('#ph'); if (!box) return; const r = 0.00025;
  try {
    const d = (await graph('images', `fields=thumb_1024_url,captured_at&limit=10&bbox=${lon - r},${lat - r},${lon + r},${lat + r}`)).data || [];
    const i = d.sort((a, b) => b.captured_at - a.captured_at)[0]; if (!i) throw 0;
    box.innerHTML = `<a href="${esc(i.thumb_1024_url)}" target="_blank" rel="noopener"><img src="${esc(i.thumb_1024_url)}" alt="Nearest street photo"></a><div class="cap">Nearest street photo, ${day(i.captured_at)} (not matched to this record)</div>`;
  } catch (e) { box.innerHTML = '<div class="msg">No street photo within 25 m</div>'; }
}
/* bounding box (0-1) of a Mapillary detection geometry: base64 vector tile with one feature */
function mvtBox(b64) {
  const u = Uint8Array.from(atob(b64), c => c.charCodeAt(0)); let ext = 4096, pts = [];
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
