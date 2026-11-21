/* Original Round 3 hardware family. 24px grid, 1.5px rounded strokes.
   Inline SVG inherits theme colour; no external symbols or network requests. */
const HW_ART = {
  cpu:'<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9" y="9" width="6" height="6" rx="1"/><path d="M9 3v3m6-3v3M9 18v3m6-3v3M3 9h3m-3 6h3m12-6h3m-3 6h3"/>',
  gpu:'<rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="8" cy="12" r="3"/><circle cx="16" cy="12" r="3"/><path d="m7 11 2 2m6-2 2 2M6 18v3m3-3v2m3-2v2M3 4v2"/>',
  ram:'<rect x="3" y="6" width="18" height="11" rx="1.5"/><path d="M6 10h3v3H6zm6 0h3v3h-3zm6 0v3M6 17v3m3-3v3m3-3v3m3-3v3m3-3v3"/>',
  vram:'<rect x="5" y="5" width="14" height="14" rx="2"/><path d="M8 8h3v3H8zm5 0h3v3h-3zm-5 5h3v3H8zm5 0h3v3h-3zM9 2v3m6-3v3M9 19v3m6-3v3"/>',
  ssd:'<rect x="3" y="7" width="18" height="10" rx="2"/><path d="M7 10h4v4H7zm7 0h3v4h-3zM19 17v3m-3-3v3m-3-3v3"/>',
  hdd:'<rect x="5" y="3" width="14" height="18" rx="2"/><circle cx="12" cy="10" r="4"/><circle cx="12" cy="10" r=".7"/><path d="m16 15-4-5M8 18h4m3 0h1"/>',
  motherboard:'<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M7 7h7v7H7zm10-1v8M7 17h10M7 10H4m6 4v3m0-14v4"/>',
  power:'<rect x="3" y="5" width="18" height="15" rx="2"/><path d="m13 7-5 6h4l-1 5 5-7h-4zM7 2v3m10-3v3"/>',
  display:'<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4M6 7h5"/>',
  network:'<rect x="8" y="3" width="8" height="6" rx="1.5"/><path d="M12 9v5M4 17v-3h16v3"/><rect x="2" y="17" width="5" height="4" rx="1"/><rect x="17" y="17" width="5" height="4" rx="1"/>',
  fan:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2"/><path d="M10 10c-5-5 4-8 4-3 0 2-1 3-1 3m1 1c7-1 5 8 1 5-2-1-2-2-2-2m-2 0c-3 7-9 0-4-2l3-1"/>',
  temperature:'<path d="M10 5a2 2 0 0 1 4 0v9a4 4 0 1 1-4 0zM12 8v9m5-10h2m-2 4h2"/><circle cx="12" cy="17" r="1"/>',
  mouse:'<rect x="6" y="3" width="12" height="18" rx="6"/><path d="M12 3v7M6 11h12"/>',
  keyboard:'<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h1m3 0h1m3 0h1m3 0h.1M6 14h1m3 0h8"/>',
  headset:'<path d="M4 13V11a8 8 0 0 1 16 0v2m0 5v1a2 2 0 0 1-2 2h-4"/><rect x="3" y="11" width="4" height="7" rx="2"/><rect x="17" y="11" width="4" height="7" rx="2"/>',
  mic:'<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M6 11v1a6 6 0 0 0 12 0v-1M12 18v3m-4 0h8"/>',
  lighting:'<rect x="7" y="11" width="10" height="9" rx="2"/><path d="M10 15h4M12 3v3M5 6l2 2m12-2-2 2M3 12h2m14 0h2"/>',
  /* Settings tabs, same grid and stroke. */
  apply:'<path d="M4 7h9m4 0h3M4 17h3m4 0h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/><path d="m14 12.5 2 2 4-4"/>',
  steam:'<rect x="2.5" y="8" width="19" height="10" rx="5"/><path d="M7 11v4m-2-2h4"/><circle cx="16" cy="12" r=".6"/><circle cx="18" cy="14" r=".6"/><path d="M9 8V6.5A1.5 1.5 0 0 1 10.5 5h3A1.5 1.5 0 0 1 15 6.5V8"/>',
  accounts:'<circle cx="9" cy="8" r="3.2"/><path d="M3 20a6 6 0 0 1 12 0"/><path d="M15.5 4.8a3.2 3.2 0 0 1 0 6.4M17 14.2a6 6 0 0 1 4 5.8"/>',
  apps:'<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><path d="M16.75 13.5v6.5M13.5 16.75H20"/>',
  look:'<path d="M12 3a9 9 0 1 0 0 18c1.4 0 2-1 1.6-2.1-.5-1.3.4-2.4 1.8-2.4H18a3 3 0 0 0 3-3c0-5-4-10.5-9-10.5z"/><circle cx="7.5" cy="11" r="1.2"/><circle cx="10" cy="7" r="1.2"/><circle cx="15" cy="7.5" r="1.2"/>',
  sound:'<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9a4 4 0 0 1 0 6m2.5-8.5a7.5 7.5 0 0 1 0 11"/>',
  overlay:'<path d="m12 3.5 9 4.5-9 4.5L3 8z"/><path d="m3 12 9 4.5 9-4.5M3 16l9 4.5 9-4.5"/>',
  config:'<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M9 12h6m-6 3h6m-6 3h3"/>',
  history:'<path d="M3.5 12a8.5 8.5 0 1 0 2.5-6"/><path d="M3 3.5V8h4.5"/><path d="M12 7.5V12l3 2"/>',
  logs:'<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
  nvidia:'<rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="3.2"/><path d="M12 8.8v6.4M8.8 12h6.4M6 18v3m12-3v3"/>',
  ingame:'<path d="M7 8h10a4 4 0 0 1 4 4v2a3 3 0 0 1-5.4 1.8L14.5 14h-5l-1.1 1.8A3 3 0 0 1 3 14v-2a4 4 0 0 1 4-4z"/><path d="M8 10v3m-1.5-1.5h3"/><circle cx="16" cy="11" r=".6"/><circle cx="17.5" cy="13" r=".6"/>',
  picture:'<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="m3.5 17 5-4.5 4 3.5 3-2.5 5 4"/>',
  profiles:'<rect x="3" y="7" width="13" height="13" rx="2"/><path d="M7 4h11a2 2 0 0 1 2 2v11"/><path d="M7 11h5m-5 3h5"/>'
};
const HW_NAMES = {cpu:'CPU',gpu:'GPU',ram:'RAM',vram:'VRAM',ssd:'SSD / NVMe',hdd:'Hard drive',motherboard:'Motherboard',power:'Power supply / power',display:'Display',network:'Network',fan:'Fan / cooling',temperature:'Temperature',mouse:'Mouse',keyboard:'Keyboard',headset:'Headset',mic:'Microphone',lighting:'Lighting',apply:'Apply',steam:'Steam',accounts:'Accounts',apps:'Apps',look:'Look',sound:'Sound',overlay:'Overlay',config:'Config files',history:'Change history',logs:'Logs',nvidia:'NVIDIA',ingame:'In the game',picture:'Picture quality',profiles:'Profiles'};
function hwKey(name) {
  const key = String(name || '').toLowerCase();
  return ({memory:'ram',processor:'cpu',graphics:'gpu',board:'motherboard',system:'motherboard',drive:'ssd',nvme:'ssd',monitor:'display',screen:'display',psu:'power',cooling:'fan',microphone:'mic',speaker:'headset',device:'cpu'})[key] || key;
}
function hwIcon(name, label) {
  const key = hwKey(name), art = HW_ART[key];
  if (!art) return '';
  const title = String(label || HW_NAMES[key]).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  return '<span class="hw-icon" data-hw="'+key+'" role="img" aria-label="'+title+'" title="'+title+'"><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'+art+'</svg></span>';
}
function hwPauseMotion() { document.documentElement.classList.toggle('hw-paused', document.hidden); }
document.addEventListener('visibilitychange', hwPauseMotion);
document.addEventListener('DOMContentLoaded', () => {
  // Existing <use> consumers (settings headings, controls and sound) share the
  // same source. Keep their IDs so existing event and decoration code works.
  const symbols = {gpu:'gpu',device:'display',speaker:'headset',keyboard:'keyboard',mouse:'mouse'};
  Object.entries(symbols).forEach(([id, key]) => {
    const symbol = document.getElementById('i-' + id);
    if (symbol) symbol.innerHTML = HW_ART[key];
  });
  document.querySelectorAll('[data-hardware-icon]').forEach(el => { el.innerHTML = hwIcon(el.dataset.hardwareIcon); });
  hwPauseMotion();
});
