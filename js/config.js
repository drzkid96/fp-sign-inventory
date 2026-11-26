// Public read-only client token (street-level imagery API). Client tokens are meant for browser use.
window.CFG = {
  MLY: 'MLY|40172474529066594|4d4b4dc682713e58c6ca50d474ea1a98',
  MAX_AREA_DEG2: 0.0006,   // about 6 sq km at LA latitude
  CHUNK_DEG: 0.005,
  DATA_V: '1795669913',   // bump when data files change
  TEST: {
    key: 'hds',
    name: 'HUNTINGTON DR S, EL SERENO, LOS ANGELES',
    bbox: [-118.1945, 34.0780, -118.1770, 34.0875]
  }
};
