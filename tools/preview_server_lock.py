"""Generate a self-contained, offline preview of the real region-lock widget.

Run with Python, then open build/server-lock-preview.html. Every API response
is synthetic, fetch is disabled and CSP forbids network access. No app/server,
Steam files, processes, probes, elevation or firewall commands are involved.
"""
import base64
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "cs2cfg" / "web"
source = (WEB / "index.html").read_text(encoding="utf-8")
styles = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", source, re.S))
styles += (WEB / "assets/home/server-lock.css").read_text(encoding="utf-8")
widget = source[source.index("const serverPingWidget = (() => {"):source.index('let activeTab = "launcher";')]
controller = (WEB / "assets/home/server-lock.js").read_text(encoding="utf-8")
art = base64.b64encode((WEB / "assets/home/hero.webp").read_bytes()).decode()
boot = r"""
const startup={finished:true};
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function setTab() {}
window.fetch=()=>{throw Error('Preview forbids real requests');};
const rows=[{code:'dxb',codes:['dxb'],city:'Dubai',country:'United Arab Emirates',ping_ms:18,loss:0,status:'good',relays_tried:1},
{code:'dfjr',codes:['dfjr'],city:'Datapacket Fujairah',partner:true,country:'United Arab Emirates',ping_ms:21,loss:0,status:'good',relays_tried:1},
{code:'bom',codes:['bom','bom2'],city:'Mumbai',country:'India',ping_ms:75,loss:0,status:'ok',relays_tried:2},
{code:'fra',codes:['fra'],city:'Frankfurt',country:'Germany',ping_ms:110,loss:33,status:'bad',relays_tried:1},
{code:'iad',codes:['iad'],city:'Sterling',country:'United States',ping_ms:null,loss:100,status:'unknown',relays_tried:2}];
let lock={checking:false,busy:false,firewall:{status:'unlocked',present:false,active:false},can_lock:true,history:[],
processes:[{name:'steam',started:1}],condebug:false,monitor:'Watching new console connections; log format awaits verification on this PC.',
advice:{text:'Saved matchmaking max ping: 150 ms. Consider 23 ms, just above this region’s relay ping. Change it in CS2; this app only reads it.'}};
let selected='dxb';
async function api(path,body) {
 if(path==='/api/servers/lock')return structuredClone(lock);
 if(path.startsWith('/api/servers/ping'))return {regions:rows,running:false,updated_at:Date.now()/1000,preferred_code:'dxb',max_ping:150};
 if(path==='/api/servers/lock/prepare'){selected=body.code;return {plan_id:'fake',city:rows.find(r=>r.code===selected).city,revision:1794268433,relay_count:120,processes:lock.processes,advice:lock.advice};}
 if(path==='/api/servers/lock/change'){lock.firewall=body.action==='unlock'?{status:'unlocked',present:false}:{status:'locked',present:true,active:true,code:selected,city:rows.find(r=>r.code===selected).city};lock.restart_needed=true;return structuredClone(lock);}
 if(path==='/api/servers/log/enable'){lock.condebug=true;return {detail:'PREVIEW: console logging enabled. No files were changed.'};}
 throw Error('Unexpected preview API '+path);
}
"""
controls = r"""
document.querySelector('#preview-theme').onchange=e=>{
 if(e.target.value==='violet')delete document.documentElement.dataset.theme;
 else document.documentElement.dataset.theme=e.target.value;
};
document.querySelector('#preview-state').onchange=e=>{
 const status=e.target.value;
 lock.firewall=status==='unlocked'?{status,present:false}:{status,present:true,active:status==='locked',code:'dxb',city:'Dubai'};
 lock.restart_needed=true;
 lock.notice=status==='wrong'?{id:String(Date.now()),time:Date.now()/1000,region:'bom2',expected:['dxb'],reason:{text:'Likely: Steam or CS2 has not restarted since this lock was applied, so matchmaking may still use cached relay measurements.'}}:null;
 if(status==='wrong')lock.firewall.status='locked';
 document.dispatchEvent(new Event('cs2cfg:ready'));
};
document.dispatchEvent(new Event('cs2cfg:ready'));
"""
themes = ("violet", "ember", "carbon", "acid", "crimson", "frost", "neon", "daylight", "paper", "pro")
html = '<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'; connect-src \'none\'"><title>Offline server lock preview</title><style>' + styles + '</style></head><body style="display:block;overflow:auto">'
html += '<div class="topbar" style="position:static;padding:18px;display:flex;gap:16px"><b>OFFLINE PREVIEW · synthetic data</b><select id="preview-theme" aria-label="Preview theme">' + ''.join(f'<option>{t}</option>' for t in themes) + '</select><select id="preview-state" aria-label="Preview state"><option>unlocked</option><option>locked</option><option>outdated</option><option>missing</option><option>wrong</option></select></div>'
html += '<main class="tab-panel" data-panel="launcher" style="padding:30px"><div id="home-hero" class="home-hero"><div class="hero-art"><img src="data:image/webp;base64,' + art + '"></div><div class="hero-copy"><div class="eyebrow">CS CONFIG AI</div><h2>Make every frame count.</h2><p>Local preview. No real firewall changes or network traffic.</p><button class="btn primary">Play CS2</button></div><button id="sp-toggle" class="sp-chip" aria-expanded="false"><span id="sp-chip-icon"></span><span id="sp-summary"></span><i class="sp-led"></i></button></div></main>'
html += '<script>' + boot + controller + widget + controls + '</script></body></html>'
out = ROOT / "build" / "server-lock-preview.html"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(html, encoding="utf-8")
print(out)
