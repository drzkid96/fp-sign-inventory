/* LA County street inventory: one map of priority tiles, agency records, street-level photo coverage and sign layers. */
const C = window.CFG, $ = s => document.querySelector(s), V = '?v=' + (C.DATA_V || 1);
const P_COL = ['#00574A', '#1B795A', '#6BD688', '#B9E6B4', '#E4EFE2'];
const Y_BRK = [[0, '#C9D3D5', 'BEFORE 2018'], [2018, '#9FB3B8', '2018-19'], [2020, '#6BD688', '2020-21'], [2022, '#1B795A', '2022-23'], [2024, '#00242E', '2024+']];
const AG = {   // agency layers in data/base/agency.pmtiles
  signs:    {label: 'County signs', type: 'circle', color: '#00242E'},
  striping: {label: 'County striping', type: 'line', color: '#568CBB'},
  markings: {label: 'County markings', type: 'circle', color: '#B07CC6'},
  signals:  {label: 'County signals', type: 'circle', color: '#FF6622'},
};
const sv = (lat, lon, h) => `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat.toFixed(6)},${lon.toFixed(6)}${h != null ? '&heading=' + Math.round(h) : ''}`;
const mlyLink = (lat, lon) => `https://www.mapillary.com/app/?lat=${lat.toFixed(6)}&lng=${lon.toFixed(6)}&z=19`;
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const day = ms => ms ? new Date(+ms).toISOString().slice(0, 10) : '';

const proto = new pmtiles.Protocol(); maplibregl.addProtocol('pmtiles', proto.tile);
const map = new maplibregl.Map({
  container: 'map', center: [-118.25, 34.05], zoom: 9.2, minZoom: 8, maxZoom: 20, hash: true, attributionControl: {compact: true},
  style: {version: 8, glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf', sources: {
    light: {type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256, maxzoom: 19, attribution: '© OpenStreetMap contributors'},
    aerial: {type: 'raster', tiles: ['https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 16, attribution: 'Imagery: USGS The National Map'},
    hires: {type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 20, attribution: 'Imagery © Esri'}},
    layers: [{id: 'light', type: 'raster', source: 'light', paint: {'raster-saturation': -0.85, 'raster-brightness-min': 0.12, 'raster-contrast': -0.1}},
             {id: 'aerial', type: 'raster', source: 'aerial', maxzoom: 16, layout: {visibility: 'none'}},
             {id: 'labels', type: 'raster', source: 'hires', minzoom: 16, layout: {visibility: 'none'}}]},
});
map.addControl(new maplibregl.NavigationControl({showCompass: false}), 'top-right');
map.addControl(new maplibregl.ScaleControl({unit: 'imperial'}), 'bottom-right');

const groups = {tiles: ['tiles-fill', 'tiles-line'], photos: ['ph-seq', 'ph-img'], mly: ['mly'], fp: ['fp']};
const vis = (ids, on) => ids.forEach(id => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none'));
const yearColor = ['step', ['to-number', ['get', 'captured_at'], 0], Y_BRK[0][1]].concat(Y_BRK.slice(1).flatMap(([y, c]) => [Date.UTC(y, 0, 1), c]));

map.on('load', async () => {
  // priority tiles
  map.addSource('tiles', {type: 'geojson', data: 'data/base/tiles.geojson' + V});
  map.addLayer({id: 'tiles-fill', type: 'fill', source: 'tiles', paint: {
    'fill-color': ['match', ['get', 'p'], 1, P_COL[0], 2, P_COL[1], 3, P_COL[2], 4, P_COL[3], P_COL[4]],
    'fill-opacity': ['interpolate', ['linear'], ['zoom'], 9, 0.62, 12, 0.32, 14, 0.08, 15, 0]}});
  map.addLayer({id: 'tiles-line', type: 'line', source: 'tiles', minzoom: 11, paint: {'line-color': '#fff', 'line-width': 0.6, 'line-opacity': ['interpolate', ['linear'], ['zoom'], 11, 0.6, 15, 0]}});

  // street-level photo coverage (Mapillary, live)
  map.addSource('mlycov', {type: 'vector', tiles: [`https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}?access_token=${C.MLY}`], minzoom: 6, maxzoom: 14, attribution: 'Photos © Mapillary (CC BY-SA)'});
  map.addLayer({id: 'ph-seq', type: 'line', source: 'mlycov', 'source-layer': 'sequence', minzoom: 12, layout: {visibility: 'none', 'line-cap': 'round'},
    paint: {'line-color': yearColor, 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 1.2, 17, 4], 'line-opacity': 0.85}});
  map.addLayer({id: 'ph-img', type: 'circle', source: 'mlycov', 'source-layer': 'image', minzoom: 16, layout: {visibility: 'none'},
    paint: {'circle-color': yearColor, 'circle-radius': 2.5, 'circle-stroke-color': '#fff', 'circle-stroke-width': 0.5}});

  // agency records (built in the cloud; absent until the first run finishes)
  let agency = null;
  try { const r = await fetch('data/base/agency.json' + V); if (r.ok) agency = await r.json(); } catch (e) {}
  const box = $('#agency');
  Object.entries(AG).forEach(([k, a]) => {
    const n = agency && agency['county_' + k] ? agency['county_' + k].count : null;
    box.insertAdjacentHTML('beforeend', `<div class="row${n == null ? ' off' : ''}"><label><input type="checkbox" data-layer="ag-${k}" ${n == null ? 'disabled' : k === 'signs' ? '' : ''}>${a.label}${n != null ? ` <span class="note">(${n.toLocaleString()})</span>` : ''}</label><i class="chip${a.type === 'line' ? ' line' : ''}" style="--c:${a.color}"></i></div>`);
  });
  if (agency) {
    const any = Object.values(agency)[0];
    $('#agency-note').textContent = `Unincorporated county, downloaded ${any.downloaded}. City records are added city by city in the build order.`;
    map.addSource('ag', {type: 'vector', url: 'pmtiles://' + location.href.replace(/[#?].*$/, '').replace(/[^/]*$/, '') + 'data/base/agency.pmtiles'});
    Object.entries(AG).forEach(([k, a]) => {
      groups['ag-' + k] = ['ag-' + k];
      map.addLayer(a.type === 'line'
        ? {id: 'ag-' + k, type: 'line', source: 'ag', 'source-layer': k, minzoom: 12, layout: {visibility: 'none'}, paint: {'line-color': a.color, 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 1, 18, 3]}}
        : {id: 'ag-' + k, type: 'circle', source: 'ag', 'source-layer': k, minzoom: 12, layout: {visibility: 'none'}, paint: {'circle-color': a.color, 'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, 2, 18, 6], 'circle-stroke-color': '#fff', 'circle-stroke-width': 1}});
    });
  } else $('#agency-note').textContent = 'County sign, striping, marking and signal records are being downloaded in the cloud; they appear here when the run finishes.';

  // Mapillary detected signs (live) and the FP inventory
  // Mapillary detected signs (live), translated to CA MUTCD codes and graded by the trust table
  const [CMAP, TRUST] = await Promise.all([fetch('data/classmap.json' + V).then(r => r.json()), fetch('data/base/trust.json' + V).then(r => r.json()).catch(() => ({codes: {}}))]);
  const fam = c => (c || '').split('/')[0].split('(')[0].trim();
  window.MLYMAP = CMAP; window.TRUST = TRUST.codes;
  const byTrust = {likely: [], mixed: [], low: []}, toCode = [];
  for (const [v, m] of Object.entries(CMAP)) {
    const c = fam(m.code); if (!c) continue; toCode.push(v, c + (m.val ? ' (' + m.val + ')' : ''));
    const t = (TRUST.codes[c] || {}).trust; if (byTrust[t]) byTrust[t].push(v);
  }
  const trustX = ['match', ['get', 'value']]; for (const k of ['likely', 'mixed', 'low']) if (byTrust[k].length) trustX.push(byTrust[k], k); trustX.push('other');
  const codeX = ['match', ['get', 'value'], ...toCode, ''];
  map.addSource('mlysign', {type: 'vector', tiles: [`https://tiles.mapillary.com/maps/vtp/mly_map_feature_traffic_sign/2/{z}/{x}/{y}?access_token=${C.MLY}`], minzoom: 14, maxzoom: 14});
  map.addLayer({id: 'mly', type: 'circle', source: 'mlysign', 'source-layer': 'traffic_sign', minzoom: 14, layout: {visibility: 'none'},
    filter: ['!=', codeX, ''],
    paint: {'circle-color': ['match', trustX, 'likely', '#568CBB', 'mixed', '#ffffff', '#ffffff'],
            'circle-stroke-color': ['match', trustX, 'likely', '#ffffff', 'mixed', '#568CBB', '#9FB3B8'],
            'circle-stroke-width': ['match', trustX, 'likely', 1, 2],
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 14, ['match', trustX, 'likely', 3, 'mixed', 2.6, 2], 19, ['match', trustX, 'likely', 7, 'mixed', 6, 4.5]]}});
  map.addLayer({id: 'mly-lab', type: 'symbol', source: 'mlysign', 'source-layer': 'traffic_sign', minzoom: 17, layout: {visibility: 'none',
    'text-field': codeX, 'text-font': ['Noto Sans Bold'], 'text-size': 11, 'text-offset': [0, 1.1], 'text-anchor': 'top', 'text-allow-overlap': false},
    paint: {'text-color': '#00242E', 'text-halo-color': '#ffffff', 'text-halo-width': 1.6}});
  groups.mly = ['mly', 'mly-lab'];
  window.MLYX = {trustX, codeX};
  map.addSource('fp', {type: 'geojson', data: 'data/base/fp.geojson' + V});
  map.addLayer({id: 'fp', type: 'circle', source: 'fp', paint: {
    'circle-color': ['case', ['==', ['get', 'name'], 1], '#9FB3B8', '#1B795A'],
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 2, 14, 3.5, 19, 8],
    'circle-stroke-color': ['case', ['==', ['get', 'status'], 'review'], '#FF6622', '#fff'], 'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 10, 0.5, 16, 2]}});

  // legends
  $('#ramp-p').innerHTML = P_COL.map((c, i) => `<span style="background:${c}" class="${i > 1 ? 'dk' : ''}">P${i + 1}</span>`).join('');
  $('#ramp-y').innerHTML = Y_BRK.map(([, c, t], i) => `<span style="background:${c}" class="${i < 3 ? 'dk' : ''}">${t}</span>`).join('');

  // tiles summary and the GO TO list in build order
  const T = await (await fetch('data/base/tiles.geojson' + V)).json();
  const cities = {};
  for (const f of T.features) {
    const p = f.properties, cs = f.geometry.coordinates[0];
    const c = cities[p.city] ||= {best: 1e9, n: 0, b: [180, 90, -180, -90]};
    c.best = Math.min(c.best, p.rank); c.n++;
    for (const [x, y] of cs) { c.b[0] = Math.min(c.b[0], x); c.b[1] = Math.min(c.b[1], y); c.b[2] = Math.max(c.b[2], x); c.b[3] = Math.max(c.b[3], y); }
  }
  const byP = [1, 2, 3, 4, 5].map(k => T.features.filter(f => f.properties.p === k).length);
  $('#tiles-note').textContent = `${T.features.length.toLocaleString()} tiles with streets. Each priority holds a fifth of the weighted street length: P1 ${byP[0]} tiles, P5 ${byP[4].toLocaleString()}. Ranked by street density, arterials, urban area and jobs and residents.`;
  Object.entries(cities).filter(([n]) => n !== 'Unincorporated').sort((a, b) => a[1].best - b[1].best)
    .forEach(([n, c]) => $('#city').insertAdjacentHTML('beforeend', `<option value="${c.b.join(',')}">${esc(n)}</option>`));
  $('#city').onchange = e => { const v = e.target.value; if (!v) return map.flyTo({center: [-118.25, 34.05], zoom: 9.2}); map.fitBounds(v.split(',').map(Number), {padding: 40, maxZoom: 14}); };

  // toggles
  document.querySelectorAll('input[data-layer]').forEach(i => {
    const apply = () => { vis(groups[i.dataset.layer] || [], i.checked); if (i.dataset.layer === 'photos') $('#ramp-y').hidden = !i.checked; hud(); };
    i.onchange = apply; apply();
  });
  document.querySelectorAll('[data-base]').forEach(b => b.onclick = () => {
    document.querySelectorAll('[data-base]').forEach(x => x.classList.toggle('on', x === b));
    const a = b.dataset.base === 'aerial'; vis(['aerial', 'labels'], a); vis(['light'], !a);
  });
  map.on('zoomend', hud); hud();
});

function hud() {
  const z = map.getZoom(), need = ['photos', 'mly'].some(k => document.querySelector(`input[data-layer="${k}"]`)?.checked) && z < 14
    || [...document.querySelectorAll('input[data-layer^="ag-"]')].some(i => i.checked) && z < 12;
  $('#hud').hidden = !need; $('#hud').textContent = 'Zoom in to see the street-level layers.';
}

// popups
const pop = (e, html) => new maplibregl.Popup({maxWidth: '300px'}).setLngLat(e.lngLat).setHTML(`<div class="pop">${html}</div>`).addTo(map);
const rows = o => '<table>' + Object.entries(o).filter(([, v]) => v !== '' && v != null).map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('') + '</table>';
const links = (lat, lon, h) => `<a href="${sv(lat, lon, h)}" target="_blank" rel="noopener">Street View</a> · <a href="${mlyLink(lat, lon)}" target="_blank" rel="noopener">Mapillary</a>`;
const hitAt = e => { const L = ['fp', 'mly', 'ag-signals', 'ag-signs', 'ag-markings', 'ag-striping', 'ph-img', 'tiles-fill'].filter(id => map.getLayer(id) && map.getLayoutProperty(id, 'visibility') !== 'none');
  return map.queryRenderedFeatures([[e.point.x - 5, e.point.y - 5], [e.point.x + 5, e.point.y + 5]], {layers: L})[0]; };
map.on('click', e => {
  const f = hitAt(e); if (!f) return; const p = f.properties, [lon, lat] = f.geometry.type === 'Point' ? f.geometry.coordinates : [e.lngLat.lng, e.lngLat.lat];
  const id = f.layer.id;
  if (id === 'fp') pop(e, `<h3>${esc(p.code)}</h3><span class="tag${p.status === 'review' ? ' rv' : ''}">${p.status === 'review' ? 'CHECK IN FIELD' : p.name ? 'STREET NAME' : 'HIGH CONFIDENCE'}</span>${p.crop ? `<img src="${p.crop}" alt="">` : ''}` +
    rows({Location: esc(p.loc), Photo: esc(p.seen), Confidence: p.conf ? Math.round(p.conf * 100) + '%' : '', Area: esc(p.area), Source: 'FP street-level inventory'}) + links(lat, lon, p.dir));
  else if (id === 'mly') {
    const m = MLYMAP[p.value] || {}, c = (m.code || '').split('/')[0].split('(')[0].trim(), t = TRUST[c] || {trust: 'untested'};
    const TT = {likely: 'LIKELY RIGHT', mixed: 'MIXED', low: 'OFTEN WRONG', untested: 'NOT YET TESTED'};
    pop(e, `<h3>${esc(c)}${m.val ? ' (' + esc(m.val) + ')' : ''}</h3><span class="tag${t.trust === 'likely' ? '' : ' rv'}">${TT[t.trust]}</span>` +
      rows({'Agreement': t.found != null ? `found ${Math.round(t.found * 100)}% of our ${t.ours} scanned ${esc(c)} signs` : '', 'Precision': t.precision != null ? Math.round(t.precision * 100) + '% of its ' + esc(c) + ' calls match ours' : '',
            'Mapillary class': esc(p.value), 'First seen': day(p.first_seen_at), 'Last seen': day(p.last_seen_at), Source: 'Mapillary detection, code translated, not yet read by our model'}) + links(lat, lon));
  }
  else if (id.startsWith('ag-')) pop(e, `<h3>${esc(p.code || AG[id.slice(3)].label)}</h3>` + rows({Description: esc(p.desc), Location: esc(p.loc), Status: esc(p.status), Date: esc(p.date), Source: esc(p.src)}) + links(lat, lon));
  else if (id === 'ph-img') pop(e, rows({Photo: day(p.captured_at), Type: p.is_pano ? '360' : 'Flat'}) + links(lat, lon));
  else if (id === 'tiles-fill') pop(e, `<h3>${esc(p.city)} · P${p.p}</h3>` + rows({'Build order': '#' + p.rank.toLocaleString(), 'Arterial km': p.art, 'All street km': p.loc, Urban: Math.round(p.urban * 100) + '%', 'Jobs + residents': (p.jobs + p.res).toLocaleString()}));
});
['fp', 'mly', 'ag-signs', 'ag-markings', 'ag-signals', 'ag-striping', 'tiles-fill'].forEach(id => {
  map.on('mouseenter', id, () => map.getCanvas().style.cursor = 'pointer'); map.on('mouseleave', id, () => map.getCanvas().style.cursor = '');
});
