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
  mic:'<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M6 11v1a6 6 0 0 0 12 0v-1M12 18v3m-4 0h8"/>'
};
const HW_NAMES = {cpu:'CPU',gpu:'GPU',ram:'RAM',vram:'VRAM',ssd:'SSD / NVMe',hdd:'Hard drive',motherboard:'Motherboard',power:'Power supply / power',display:'Display',network:'Network',fan:'Fan / cooling',temperature:'Temperature',mouse:'Mouse',keyboard:'Keyboard',headset:'Headset',mic:'Microphone'};
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
