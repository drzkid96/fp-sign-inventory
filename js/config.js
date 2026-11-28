// Public read-only client token (street-level imagery API). Client tokens are meant for browser use.
window.CFG = {
  MLY: 'MLY|40172474529066594|4d4b4dc682713e58c6ca50d474ea1a98',
  MAX_AREA_DEG2: 0.0006,   // about 6 sq km at LA latitude
  CHUNK_DEG: 0.005,
  DATA_V: '1795900000',   // bump when data files change
  AREAS: [   // scanned areas: results in data/areas/<key>/
    {key: 'burbank-glenoaks', name: 'GLENOAKS BLVD, BURBANK', bbox: [-118.34287, 34.17331, -118.293, 34.20776]},
    {key: 'culver-city', name: 'DOWNTOWN CULVER CITY', bbox: [-118.3995, 34.0197, -118.3925, 34.0253]},
    {key: 'hds', name: 'HUNTINGTON DR, EL SERENO, LOS ANGELES', bbox: [-118.1945, 34.0780, -118.1770, 34.0875]}
  ]
};
