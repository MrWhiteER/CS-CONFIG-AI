// A tiny DOM and manual scheduler for the real panel script. No browser packages.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor(id = '') { this.id = id; this.hidden = false; this.disabled = false; this.value = ''; this.children = []; this.dataset = {}; this.listeners = {}; this.attrs = {}; this.textContent = ''; }
  replaceChildren() { this.children = []; }
  appendChild(child) { this.children.push(child); if (this.id && (!this.value || child.selected)) this.value = child.value; return child; }
  insertRow() { return this.appendChild(new Element()); }
  insertCell() { return this.appendChild(new Element()); }
  querySelector() { return this.span ||= new Element(); }
  setAttribute(k,v) { this.attrs[k] = v; }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  click() { return this.onclick?.() || this.listeners.click?.({preventDefault(){}}); }
}

async function run(scenario) {
  const ids = ['fps','average','low','worst','cpu','gpu','temp','shortcut','capture-state','frame-hint','dismiss',
    'notice','graph','range-label','events','setups','layouts','use-setup','use-layout','profile-note','regions',
    'region-controls','region-text','lock-region','unlock-region','close','preview','error','keyboard','setup-link'];
  const elements = Object.fromEntries(ids.map(id => [id,new Element(id)]));
  elements['region-controls'].hidden = true;
  const ranges = [120,300,600].map(n => {const e = new Element(); e.dataset.range = String(n); return e;});
  const timers = new Map(), requests = [], listeners = {}, errors = [];
  let sequence = 0, clock = 0, busy = scenario === 'busy', bound = true, deferred = null;
  const data = {settings:{overlay_panel_hotkey:'Ctrl+Alt+P'}, current:{fps:200,cpu_percent:25,gpu_percent:70,gpu_temp_c:61},
    frame_capture_ready:true, game_running:true, summary:{avg_fps:195,one_percent_low:110,worst_frame_ms:28},
    history:[{at:Date.now()/1000,frame_time_ms:5}], events:[{at:20,duration_ms:15,type:'frame_spike'},
      {at:30,duration_ms:200,type:'not_responding'}]};
  const document = {hidden:false, getElementById:id=>elements[id], createElement:()=>new Element(),
    createElementNS:()=>new Element(), addEventListener:(name,fn)=>listeners[name]=fn,
    querySelectorAll:selector=>selector === '[data-range]' ? ranges : [elements.keyboard,elements['setup-link']]};
  const region = () => scenario === 'missing' ? {ok:true,available:false,text:'Coming soon'} :
    {ok:true,available:true,text:busy?'Updating region lock…':'Locked to Dubai',poll:busy,
      regions:[{code:'dxb',city:'Dubai',country:'AE',ping_ms:12,loss:0,status:'ok'}],status:{busy,firewall:{code:'dxb'}}};
  const context = {document, location:{search:scenario === 'preview' ? '?preview=1' : ''},
    URLSearchParams, AbortController, Date, console, performance:{now:()=>clock},
    setTimeout:(fn,ms)=>{const id=++sequence;timers.set(id,{fn,ms});return id;},
    clearTimeout:id=>timers.delete(id), fetch:async (path,options)=>{
      const body = JSON.parse(options.body); requests.push({path,body,signal:options.signal});
      if (scenario === 'late' && path === '/api/overlay') return new Promise(resolve=>deferred=resolve);
      let result;
      if (path === '/api/overlay') result = data;
      else if (path === '/api/setups') result = {setups:[{name:'Match'}],live:'Match'};
      else if (path === '/api/cfg/layouts/profiles') result = {profiles:[{file:'match.vcfg',label:'Match',active:true}]};
      else if (path === '/api/cfg/layouts/apply') result = {apply_keys:bound?['F8']:[]};
      else if (path === '/api/setups/act') result = {};
      else if (path === '/api/overlay/settings') result = {...data,frame_capture_hint:'',frame_capture_hint_dismissible:false};
      else result = region();
      return {ok:true,json:async()=>result};
    }};
  context.window = {overlayToken:'test-token',addEventListener:(name,fn)=>listeners[name]=fn};
  vm.runInNewContext(fs.readFileSync('cs2cfg/web/assets/overlay/panel.js','utf8'),context);
  const flush = async () => {for(let i=0;i<20;i++) await Promise.resolve();};
  const tick = async () => {const batch=[...timers.values()];timers.clear();clock+=1000;for(const t of batch){assert(t.ms>=100);t.fn();}await flush();};
  const activate = async () => {context.window.overlayPanelActive(true);await flush();};
  const hide = () => context.window.overlayPanelActive(false);
  if (scenario === 'preview') {
    await flush(); assert.equal(requests.length,0); assert.equal(timers.size,0);
    assert.equal(elements.fps.textContent,'287.0'); assert.equal(elements['region-controls'].hidden,true);
    // HTML starts the controls hidden; the preview never enables them or runs region calls.
    assert.equal(elements.setups.disabled,true);
    await elements['use-layout'].click(); assert.equal(requests.length,0);
    ranges[2].click(); await tick(); assert.equal(elements['range-label'].textContent,'10 minutes ago');
    assert.equal(timers.size,0); return;
  }
  assert.equal(requests.length,0); assert.equal(timers.size,0);
  await activate();
  if (scenario === 'busy') {
    assert.equal(timers.size,2); assert.equal(elements['lock-region'].disabled,true);
    await tick(); assert.equal(requests.filter(r=>r.path==='/api/overlay/panel').length,2);
    busy=false; await tick(); assert.equal(timers.size,1);
    const count=requests.filter(r=>r.path==='/api/overlay/panel').length;
    await tick(); assert.equal(requests.filter(r=>r.path==='/api/overlay/panel').length,count);
  } else if (scenario === 'missing') {
    assert.equal(elements['region-text'].textContent,'Coming soon');
    assert.equal(elements['region-controls'].hidden,true); assert.equal(timers.size,1);
    await tick(); assert.equal(requests.filter(r=>r.path==='/api/overlay/panel').length,1);
  } else if (scenario === 'profiles') {
    await elements['use-layout'].click(); await flush();
    assert.equal(elements['profile-note'].textContent,'Press F8 in game to load it');
    assert.equal(requests.at(-1).body.file,'match.vcfg');
    bound=false; await elements['use-layout'].click(); await flush();
    assert.match(elements['profile-note'].textContent,/No Apply Saved Settings key/);
    await elements['use-setup'].click(); await flush();
    assert.equal(requests.at(-1).body.do,'use'); assert.equal(requests.at(-1).body.name,'Match');
    assert.equal(elements.events.children[0].children[2].textContent,'Not responding');
  } else if (scenario === 'permissions') {
    data.frame_capture_ready=false; data.frame_capture_hint='Finish setup to enable frame stats';
    await tick(); assert.equal(elements.fps.textContent,'—'); assert.equal(elements.cpu.textContent,'25.0%');
    assert.equal(elements['frame-hint'].span.textContent,data.frame_capture_hint);
    data.frame_capture_hint='Sign out of Windows and back in once to enable frame stats';
    data.frame_capture_hint_dismissible=true; await tick(); assert.equal(elements.dismiss.hidden,false);
    await elements.dismiss.click(); await flush(); assert.equal(requests.at(-1).body.overlay_sign_out_hint_dismissed,true);
    assert.equal(elements['frame-hint'].hidden,true);
  } else if (scenario === 'late') {
    hide(); assert(requests.every(r=>r.signal.aborted));
    deferred({ok:true,json:async()=>data}); await flush();
    assert.equal(timers.size,0); assert.equal(elements.fps.textContent,''); return;
  } else if (scenario === 'visibility') {
    document.hidden=true; listeners.visibilitychange(); assert.equal(timers.size,0);
    clock+=1000;
    document.hidden=false; listeners.visibilitychange(); await flush(); assert.equal(timers.size,1);
  } else if (scenario === 'graph') {
    const previous = elements.graph.children;
    for (let i=0;i<30;i++) ranges[i%3].click();
    assert.equal(elements.graph.children,previous);
    assert.equal(timers.size,2); // One pending draw, one performance refresh.
    await tick(); assert.notEqual(elements.graph.children,previous);
    assert.equal(elements['range-label'].textContent,'10 minutes ago');
  }
  hide(); assert.equal(timers.size,0);
  const count=requests.length; await tick(); assert.equal(requests.length,count);
  assert(requests.every(r=>!r.signal || r.signal.aborted));
}

run(process.argv[2]).catch(error=>{console.error(error);process.exitCode=1;});
