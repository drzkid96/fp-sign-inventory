/* Data layers (volumes, turning counts, speeds, walk and bike, intersection control, transit, parking), built from
   data/layers.json and data/layers/index.json. A layer added to the registry shows up here with no code change.
   Sources load only when a layer is first turned on. */
(() => {
  const $ = s => document.querySelector(s), esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const V = '?v=' + (window.CFG?.DATA_V || 1);
  let REG = null, IDX = {}, SINCE_Y = 2021; const SPEC = {}, IDS = {}, BASEF = {};
  const tpl = (t, p) => String(t || '').replace(/\{(\w+)\}/g, (_, k) => p[k] ?? '').replace(/\s+/g, ' ').replace(/^\s*(and|at|to)\s+|\s+(and|at|to)\s*$/g, '').trim();
  const fmt = (v, f) => v === undefined || v === null || v === '' ? null : f === 'num' ? Number(v).toLocaleString() : f === 'mph' ? `${v} mph` : f === 'money' ? `$${Number(v).toFixed(2)}`
    : f === 'date' && +v > 1e11 ? new Date(+v).toISOString().slice(0, 10) : String(v);
  const label = t => { const parts = []; String(t).split(/(\{\w+\})/).forEach(s => { const m = s.match(/^\{(\w+)\}$/); if (m) parts.push(['to-string', ['coalesce', ['get', m[1]], '']]); else if (s) parts.push(s); });
    return parts.length === 1 ? parts[0] : ['concat', ...parts]; };
  const size = st => { const s = st.stops || [[0, 4]]; if (!st.metric || s.length < 2) return s[0][1];
    return ['interpolate', ['linear'], ['to-number', ['get', st.metric], 0], ...s.flat()]; };
  const zs = (v, z1, a, z2, b) => ['interpolate', ['linear'], ['zoom'], z1, typeof v === 'number' ? v * a : ['*', v, a], z2, typeof v === 'number' ? v * b : ['*', v, b]];
  const colorOf = (st, c) => st.colorBy ? ['match', ['get', st.colorBy], ...Object.entries(st.colors).flat(), c] : st.colorField ? ['coalesce', ['get', st.colorField], c] : c;
  const isOn = id => document.querySelector(`[data-dl="${id}"]`)?.classList.contains('on');
  const ready = l => (IDX[l.id] || {}).count > 0 && (IDX[l.id] || {}).tiles;

  async function init() {
    const get = (u, d) => fetch(u + V).then(r => r.ok ? r.json() : d).catch(() => d);
    [REG, IDX] = await Promise.all([get('data/layers.json', null), get('data/layers/index.json', {})]);
    if (!REG) return;
    SINCE_Y = +REG.since.slice(0, 4);
    const box = $('#data-groups'); if (!box) return;
    for (const l of REG.layers) SPEC[l.id] = l;
    const groups = REG.groups.map(g => ({g, ls: REG.layers.filter(l => l.group === g.id)})).filter(x => x.ls.length);
    $('#views').innerHTML = groups.map(({g, ls}) => `<button data-view="${g.id}" ${ls.some(ready) ? '' : 'disabled'}><i style="--c:${g.color}"></i>${esc(g.title)}</button>`).join('')
      + '<button data-view="" class="clear">Clear</button>';
    box.innerHTML = groups.map(({g, ls}) => `<details data-g="${g.id}"><summary><i style="--c:${g.color}"></i>${esc(g.title.toUpperCase())}<span class="n"></span></summary><div class="chips">${ls.map(l => { const s = IDX[l.id] || {};
      const n = ready(l) ? ` <small>${s.count.toLocaleString()}</small>` : '';
      return `<button data-dl="${l.id}" ${ready(l) ? '' : 'disabled'} title="${esc(ready(l) ? l.source.name : s.error ? 'Build failed: ' + s.error : s.skipped || 'Not built yet')}"><i class="${l.geom === 'line' ? 'ln' : l.geom === 'polygon' ? 'sq' : ''}" style="--c:${g.color}"></i>${esc(l.title)}${n}</button>`; }).join('')}</div></details>`).join('');
    const yrs = []; for (let y = SINCE_Y; y <= new Date().getFullYear(); y++) yrs.push(y);
    $('#since').innerHTML = yrs.map(y => `<option value="${y}">${y}</option>`).join('');
    $('#since').onchange = () => { SINCE_Y = +$('#since').value; for (const id in IDS) filter(id); };
    box.querySelectorAll('[data-dl]').forEach(b => b.onclick = () => { if (!b.disabled) set(b.dataset.dl, !b.classList.contains('on')); });
    $('#views').querySelectorAll('[data-view]').forEach(b => b.onclick = () => {
      const g = b.dataset.view; for (const l of REG.layers) if (ready(l)) set(l.id, l.group === g);
      $('#views').querySelectorAll('[data-view]').forEach(x => x.classList.toggle('on', x === b && !!g));
      box.querySelectorAll('details').forEach(d => d.open = d.dataset.g === g);
    });
    window.dataHit = e => {
      const ids = clickable(); if (!ids.length) return false;
      const f = map.queryRenderedFeatures([[e.point.x - 6, e.point.y - 6], [e.point.x + 6, e.point.y + 6]], {layers: ids})[0];
      if (!f) return false; openData(f, e.lngLat); return true;
    };
    let mvT; map.on('mousemove', e => { clearTimeout(mvT); mvT = setTimeout(() => { const ids = clickable(); if (!ids.length) return;
      const hit = map.queryRenderedFeatures([[e.point.x - 6, e.point.y - 6], [e.point.x + 6, e.point.y + 6]], {layers: ids}).length;
      map.getCanvas().style.cursor = hit ? 'pointer' : ''; }, 40); });
    map.on('zoomend', legend);
    window.dataLayers = {set, ensure, specs: SPEC, index: IDX};      // console and Claude access
  }
  const clickable = () => Object.values(IDS).flat().filter(id => !id.endsWith('-lbl') && !id.endsWith('-edge') && map.getLayoutProperty(id, 'visibility') === 'visible');

  function set(id, v) {
    const b = document.querySelector(`[data-dl="${id}"]`); if (!b || b.disabled) return;
    b.classList.toggle('on', v); if (v) ensure(id);
    (IDS[id] || []).forEach(x => map.setLayoutProperty(x, 'visibility', v ? 'visible' : 'none'));
    document.querySelectorAll('#data-groups details').forEach(d => { const n = d.querySelectorAll('[data-dl].on').length; d.querySelector('.n').textContent = n ? ` · ${n} on` : ''; });
    legend();
  }
  function ensure(id) {
    if (IDS[id]) return;
    const l = SPEC[id], s = IDX[id], g = REG.groups.find(x => x.id === l.group), st = l.style || {}, c = colorOf(st, g.color), minz = st.minzoom || 9;
    const before = map.getLayer('signs-halo') ? 'signs-halo' : undefined;
    map.addSource('dl-' + id, {type: 'vector', url: 'pmtiles://' + new URL(s.tiles, location.href).href});
    const base = {source: 'dl-' + id, 'source-layer': id, minzoom: minz, layout: {visibility: 'none'}}, ids = [];
    const add = o => { BASEF[o.id] = o.filter || null; map.addLayer(Object.assign({}, base, o, {layout: Object.assign({}, base.layout, o.layout || {})}), before); ids.push(o.id); };
    if (l.geom === 'polygon') {
      add({id: `dl-${id}-fill`, type: 'fill', paint: {'fill-color': c, 'fill-opacity': 0.12}});
      add({id: `dl-${id}-edge`, type: 'line', paint: {'line-color': c, 'line-width': 1.2, 'line-opacity': 0.8}});
    }
    if (l.geom === 'line') add({id: `dl-${id}-line`, type: 'line', filter: ['==', ['geometry-type'], 'LineString'], layout: {'line-cap': 'round', 'line-join': 'round'},
      paint: {'line-color': c, 'line-width': zs(size(st), 10, 0.6, 16, 1.6), 'line-opacity': 0.85}});
    if (l.geom !== 'polygon') add({id: `dl-${id}-pt`, type: 'circle', filter: ['==', ['geometry-type'], 'Point'],
      paint: {'circle-color': c, 'circle-radius': zs(size(st), 10, 0.7, 17, 1.5), 'circle-stroke-color': '#fff', 'circle-stroke-width': 1, 'circle-opacity': 0.92}});
    if (st.label) add({id: `dl-${id}-lbl`, type: 'symbol', minzoom: Math.max(minz, 14), layout: {'text-field': label(st.label), 'text-font': ['Noto Sans Bold'], 'text-size': 11,
      'symbol-placement': l.geom === 'line' ? 'line' : 'point', 'text-offset': l.geom === 'line' ? [0, -0.9] : [0, -1.25], 'text-allow-overlap': false, 'text-optional': true},
      paint: {'text-color': st.colorField ? '#00242E' : c, 'text-halo-color': '#fff', 'text-halo-width': 2}});
    IDS[id] = ids; filter(id);
  }
  function filter(id) {
    const y = ['>=', ['to-number', ['get', 'year'], 0], SINCE_Y];
    (IDS[id] || []).forEach(x => map.setFilter(x, BASEF[x] ? ['all', BASEF[x], y] : y));
  }
  const METRIC = {adt: 'daily volume', aadt: 'AADT', p85: '85th percentile speed', total: 'count total'};
  function legend() {
    const el = $('#legend'); if (!el || !REG) return;
    const on = REG.layers.filter(l => isOn(l.id));
    const parts = on.filter(l => l.style?.colorBy).map(l => `<div class="lg"><b>${esc(l.title)}</b>${Object.entries(l.style.colors).map(([k, c]) => `<span><i style="--c:${c}"></i>${esc(k)}</span>`).join('')}</div>`);
    const sized = on.filter(l => l.style?.metric).map(l => `${esc(l.title)}: size shows ${esc(METRIC[l.style.metric] || l.style.metric)}`);
    const minz = on.filter(l => (l.style?.minzoom || 9) > map.getZoom()).map(l => esc(l.title));
    el.innerHTML = parts.join('') + (sized.length ? `<p class="sz">${sized.join('<br>')}</p>` : '') + (minz.length ? `<p class="hint-z">Zoom in to see: ${minz.join(', ')}</p>` : '');
    el.hidden = !el.innerHTML;
  }

  function tmcTable(p) {
    const rows = ['nb', 'sb', 'eb', 'wb'].filter(k => p[k] && p[k] !== '0/0/0');
    if (!rows.length) return '';
    return `<table class="facts tmc"><tr><td>Approach</td><td>Left</td><td>Through</td><td>Right</td></tr>${rows.map(k => `<tr><td>${k.toUpperCase()}</td>${String(p[k]).split('/').map(v => `<td>${Number(v).toLocaleString()}</td>`).join('')}</tr>`).join('')}</table>
      <p class="note-x">Totals over all count hours. Peak 15-minute and hourly movements are in the count report.</p>`;
  }
  function openData(f, ll) {
    const l = SPEC[f.sourceLayer], p = f.properties, s = IDX[l.id] || {}, cd = l.card || {}, g = REG.groups.find(x => x.id === l.group);
    let rows = (cd.fields || []).map(([t, k, fm]) => [t, fmt(p[k], fm)]).filter(r => r[1] !== null);
    if (cd.raw) rows = rows.concat(Object.entries(p).filter(([k]) => !['id', 'layer', 'src', 'year', 'date'].includes(k)).map(([k, v]) => [k.replace(/_/g, ' ').toLowerCase(), String(v)]));
    const files = Object.entries(s.files || {}), lat = ll.lat, lon = ll.lng;
    const pdf = cd.pdf && p[cd.pdf] ? `<a href="${esc(p[cd.pdf])}" target="_blank" rel="noopener">Count report (PDF)</a>` : '';
    $('#card-body').innerHTML = `<div class="dc-head"><span class="badge" style="--c:${g.color}">${esc(g.title.toUpperCase())}</span>
      <div class="sc-code">${esc(tpl(cd.title, p) || l.title)}</div><div class="sc-name">${esc(tpl(cd.sub, p))}</div></div>
      <table class="facts">${rows.map(([t, v]) => `<tr><td>${esc(t)}</td><td>${esc(v)}</td></tr>`).join('')}</table>
      ${cd.tmc ? tmcTable(p) : ''}
      ${cd.live === 'ladot_occupancy' ? '<p class="note-x" id="live">Checking the meter sensor…</p>' : ''}
      ${cd.note ? `<p class="note-x">${esc(tpl(cd.note, p))}</p>` : ''}
      <p class="note-x">Source: <a href="${esc(/^https?:/.test(l.source.url) ? l.source.url : 'data.html')}" target="_blank" rel="noopener">${esc(l.source.agency)}, ${esc(l.source.name)}</a>${s.as_of ? ` · ${s.as_of_note ? 'downloaded' : 'updated'} ${esc(s.as_of)}` : ''}</p>
      <div class="links">${pdf}<a href="https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat.toFixed(6)},${lon.toFixed(6)}" target="_blank" rel="noopener">Street View</a><a href="data.html#${l.id}">Layer details</a></div>
      ${files.length ? `<p class="dl">Download layer: ${files.map(([k, u]) => `<a href="${esc(u)}">${esc(k)}</a>`).join(' · ')}</p>` : ''}`;
    $('#card').hidden = false; if (innerWidth < 700) { $('#panel').classList.add('folded'); $('#fold').textContent = '+'; }
    if (!map.getSource('sel')) { map.addSource('sel', {type: 'geojson', data: {type: 'FeatureCollection', features: []}});
      map.addLayer({id: 'sel', type: 'circle', source: 'sel', paint: {'circle-radius': 22, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#FF6622', 'circle-stroke-width': 3}}); }
    map.getSource('sel').setData({type: 'Feature', geometry: {type: 'Point', coordinates: [lon, lat]}, properties: {}});
    if (cd.live === 'ladot_occupancy' && p.space) fetch(`https://data.lacity.org/resource/e7h6-4a3e.json?spaceid=${encodeURIComponent(p.space)}`).then(r => r.json()).then(d => {
      const x = d[0], el = $('#live'); if (!el) return;
      el.innerHTML = x ? `Meter sensor: <b>${esc(String(x.occupancystate).toLowerCase())}</b> as of ${esc(String(x.eventtime).replace('T', ' ').slice(0, 16))}` : 'This meter has no occupancy sensor.';
    }).catch(() => { const el = $('#live'); if (el) el.textContent = 'Meter sensor status unavailable.'; });
  }

  const start = () => { let ok = false; try { ok = !!map.getLayer('signs-halo'); } catch (e) {} ok ? init() : setTimeout(start, 250); };
  start();
})();
