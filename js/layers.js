/* Data layers (volumes, speeds, walk and bike counts, parking), built from data/layers.json.
   A layer added to the registry and built by pipeline/layers.py shows up here with no code change. */
(() => {
  const $ = s => document.querySelector(s), esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const V = '?v=' + (window.CFG?.DATA_V || 1);
  let REG = null, IDX = {}, SINCE_Y = 2021; const SPEC = {}, IDS = {}, BASEF = {};
  const tpl = (t, p) => String(t || '').replace(/\{(\w+)\}/g, (_, k) => p[k] ?? '').replace(/\s+/g, ' ').trim();
  const fmt = (v, f) => v === undefined || v === null || v === '' ? null : f === 'num' ? Number(v).toLocaleString() : f === 'mph' ? `${v} mph` : f === 'money' ? `$${Number(v).toFixed(2)}`
    : f === 'date' && +v > 1e11 ? new Date(+v).toISOString().slice(0, 10) : String(v);
  const label = t => { const parts = []; String(t).split(/(\{\w+\})/).forEach(s => { const m = s.match(/^\{(\w+)\}$/); if (m) parts.push(['to-string', ['coalesce', ['get', m[1]], '']]); else if (s) parts.push(s); });
    return parts.length === 1 ? parts[0] : ['concat', ...parts]; };
  const size = st => { const s = st.stops || [[0, 4]]; if (!st.metric || s.length < 2) return s[0][1];
    return ['interpolate', ['linear'], ['to-number', ['get', st.metric], 0], ...s.flat()]; };

  async function init() {
    const get = (u, d) => fetch(u + V).then(r => r.ok ? r.json() : d).catch(() => d);
    [REG, IDX] = await Promise.all([get('data/layers.json', null), get('data/layers/index.json', {})]);
    if (!REG) return;
    SINCE_Y = +REG.since.slice(0, 4);
    const box = $('#data-groups'); if (!box) return;
    const groups = REG.groups.map(g => ({g, ls: REG.layers.filter(l => l.group === g.id)}));
    box.innerHTML = groups.map(({g, ls}) => `<h3>${esc(g.title.toUpperCase())}</h3><div class="chips">${ls.map(l => { const s = IDX[l.id] || {};
      const ok = s.count > 0 && s.tiles, n = ok ? ` <small>${s.count.toLocaleString()}</small>` : '';
      return `<button data-dl="${l.id}" ${ok ? '' : 'disabled'} title="${esc(ok ? l.source.name : s.error ? 'Build failed: ' + s.error : s.skipped || 'Not built yet')}"><i class="${l.geom === 'line' ? 'ln' : l.geom === 'polygon' ? 'sq' : ''}" style="--c:${g.color}"></i>${esc(l.title)}${n}</button>`; }).join('')}</div>`).join('');
    const yrs = []; for (let y = SINCE_Y; y <= new Date().getFullYear(); y++) yrs.push(y);
    $('#since').innerHTML = yrs.map(y => `<option value="${y}">${y}</option>`).join('');
    $('#since').onchange = () => { SINCE_Y = +$('#since').value; for (const id in IDS) filter(id); };
    const before = map.getLayer('signs-halo') ? 'signs-halo' : undefined;
    for (const l of REG.layers) {
      const s = IDX[l.id]; if (!s?.tiles || !s.count) continue;
      SPEC[l.id] = l; const g = REG.groups.find(x => x.id === l.group), c = g.color, st = l.style || {}, minz = st.minzoom || 9;
      map.addSource('dl-' + l.id, {type: 'vector', url: 'pmtiles://' + new URL(s.tiles, location.href).href});
      const base = {source: 'dl-' + l.id, 'source-layer': l.id, minzoom: minz, layout: {visibility: 'none'}}, ids = [];
      const add = (o) => { BASEF[o.id] = o.filter || null; map.addLayer(Object.assign({}, base, o, {layout: Object.assign({}, base.layout, o.layout || {})}), before); ids.push(o.id); };
      if (l.geom === 'polygon') {
        add({id: `dl-${l.id}-fill`, type: 'fill', paint: {'fill-color': c, 'fill-opacity': 0.12}});
        add({id: `dl-${l.id}-edge`, type: 'line', paint: {'line-color': c, 'line-width': 1.2, 'line-opacity': 0.8}});
      }
      if (l.geom === 'line') {
        add({id: `dl-${l.id}-line`, type: 'line', filter: ['==', ['geometry-type'], 'LineString'], layout: {'line-cap': 'round'},
          paint: {'line-color': c, 'line-width': ['*', size(st), ['interpolate', ['linear'], ['zoom'], 10, 0.6, 16, 1.6]], 'line-opacity': 0.85}});
      }
      if (l.geom !== 'polygon') {
        add({id: `dl-${l.id}-pt`, type: 'circle', filter: ['==', ['geometry-type'], 'Point'],
          paint: {'circle-color': c, 'circle-radius': ['*', size(st), ['interpolate', ['linear'], ['zoom'], 10, 0.7, 17, 1.5]], 'circle-stroke-color': '#fff', 'circle-stroke-width': 1, 'circle-opacity': 0.9}});
      }
      if (st.label) add({id: `dl-${l.id}-lbl`, type: 'symbol', minzoom: Math.max(minz, 14), layout: {'text-field': label(st.label), 'text-font': ['Noto Sans Bold'], 'text-size': 11,
        'symbol-placement': l.geom === 'line' ? 'line' : 'point', 'text-offset': l.geom === 'line' ? [0, -0.9] : [0, -1.2], 'text-allow-overlap': false},
        paint: {'text-color': c, 'text-halo-color': '#fff', 'text-halo-width': 2}});
      IDS[l.id] = ids; filter(l.id);
    }
    box.querySelectorAll('[data-dl]').forEach(b => b.onclick = () => { if (b.disabled) return; b.classList.toggle('on');
      (IDS[b.dataset.dl] || []).forEach(id => map.setLayoutProperty(id, 'visibility', b.classList.contains('on') ? 'visible' : 'none')); });
    const clickable = () => Object.values(IDS).flat().filter(id => !id.endsWith('-lbl') && !id.endsWith('-edge') && map.getLayoutProperty(id, 'visibility') === 'visible');
    window.dataHit = e => {
      const ids = clickable(); if (!ids.length) return false;
      const f = map.queryRenderedFeatures([[e.point.x - 6, e.point.y - 6], [e.point.x + 6, e.point.y + 6]], {layers: ids})[0];
      if (!f) return false; openData(f, e.lngLat); return true;
    };
    map.on('mousemove', e => { const ids = clickable(); if (!ids.length) return;
      const hit = map.queryRenderedFeatures([[e.point.x - 6, e.point.y - 6], [e.point.x + 6, e.point.y + 6]], {layers: ids}).length;
      if (hit) map.getCanvas().style.cursor = 'pointer'; else if (map.getCanvas().style.cursor === 'pointer' && !map.queryRenderedFeatures(e.point, {layers: ['signs-face', 'signs-halo'].filter(x => map.getLayer(x))}).length) map.getCanvas().style.cursor = ''; });
  }
  function filter(id) {
    const y = ['>=', ['to-number', ['get', 'year'], 0], SINCE_Y];
    (IDS[id] || []).forEach(x => map.setFilter(x, BASEF[x] ? ['all', BASEF[x], y] : y));
  }

  function openData(f, ll) {
    const l = SPEC[f.sourceLayer], p = f.properties, s = IDX[l.id] || {}, cd = l.card || {}, g = REG.groups.find(x => x.id === l.group);
    const rows = (cd.fields || []).map(([t, k, fm]) => [t, fmt(p[k], fm)]).filter(r => r[1] !== null);
    const files = Object.entries(s.files || {});
    const lat = ll.lat, lon = ll.lng;
    $('#card-body').innerHTML = `<div class="dc-head"><span class="badge" style="--c:${g.color}">${esc(g.title.toUpperCase())}</span>
      <div class="sc-code">${esc(tpl(cd.title, p) || l.title)}</div><div class="sc-name">${esc(tpl(cd.sub, p))}</div></div>
      <table class="facts">${rows.map(([t, v]) => `<tr><td>${esc(t)}</td><td>${esc(v)}</td></tr>`).join('')}</table>
      ${cd.live === 'ladot_occupancy' ? '<p class="note-x" id="live">Checking the meter sensor…</p>' : ''}
      ${cd.note ? `<p class="note-x">${esc(tpl(cd.note, p))}</p>` : ''}
      <p class="note-x">Source: <a href="${esc(/^https?:/.test(l.source.url) ? l.source.url : 'data.html')}" target="_blank" rel="noopener">${esc(l.source.agency)}, ${esc(l.source.name)}</a>${s.as_of ? ` · updated ${esc(s.as_of)}` : ''}</p>
      <div class="links"><a href="https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat.toFixed(6)},${lon.toFixed(6)}" target="_blank" rel="noopener">Street View</a><a href="data.html#${l.id}">Layer details</a></div>
      ${files.length ? `<p class="dl">Download layer: ${files.map(([k, u]) => `<a href="${esc(u)}">${esc(k)}</a>`).join(' · ')}</p>` : ''}`;
    $('#card').hidden = false; if (innerWidth < 700) { $('#panel').classList.add('folded'); $('#fold').textContent = '+'; }
    if (!map.getSource('sel')) { map.addSource('sel', {type: 'geojson', data: {type: 'FeatureCollection', features: []}});
      map.addLayer({id: 'sel', type: 'circle', source: 'sel', paint: {'circle-radius': 26, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#FF6622', 'circle-stroke-width': 3}}); }
    map.getSource('sel').setData({type: 'Feature', geometry: {type: 'Point', coordinates: [lon, lat]}, properties: {}});
    if (cd.live === 'ladot_occupancy' && p.space) fetch(`https://data.lacity.org/resource/e7h6-4a3e.json?spaceid=${encodeURIComponent(p.space)}`).then(r => r.json()).then(d => {
      const x = d[0], el = $('#live'); if (!el) return;
      el.innerHTML = x ? `Meter sensor: <b>${esc(String(x.occupancystate).toLowerCase())}</b> as of ${esc(String(x.eventtime).replace('T', ' ').slice(0, 16))}` : 'This meter has no occupancy sensor.';
    }).catch(() => { const el = $('#live'); if (el) el.textContent = 'Meter sensor status unavailable.'; });
  }

  const ready = () => { let ok = false; try { ok = !!map.getLayer('signs-halo'); } catch (e) {} ok ? init() : setTimeout(ready, 250); };
  ready();
})();
