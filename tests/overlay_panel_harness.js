/* Dependency-free DOM and manual clock for the production shell and renderers. */
const assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm');
class Element{
 constructor(tag='div'){this.tagName=tag.toUpperCase();this.attrs={};this.children=[];this.parentElement=null;this.style={setProperty(k,v){this[k]=v;}};this.dataset={};this._text='';this.listeners={};this.hidden=false;this.disabled=false;this.checked=false;this.selected=false;this._value='';this.classList={add:(...c)=>{this.className=[...new Set([...this.className.split(' '),...c])].join(' ');},remove:(...c)=>{this.className=this.className.split(' ').filter(x=>!c.includes(x)).join(' ');},contains:c=>this.className.split(' ').includes(c)};}
 get nextElementSibling(){const siblings=this.parentElement?.children||[];return siblings[siblings.indexOf(this)+1]||null;}
 before(node){const parent=this.parentElement;node.parentElement=parent;parent.children.splice(parent.children.indexOf(this),0,node);}
 get id(){return this.attrs.id||'';}set id(v){this.attrs.id=v;}
 get className(){return this.attrs.class||'';}set className(v){this.attrs.class=v;}
 get value(){if(this.tagName==='SELECT')return (this.children.find(c=>c.selected)||this.children[0])?.value||'';return this._value;}
 set value(v){this._value=v;if(this.tagName==='SELECT')for(const c of this.children)c.selected=c.value===v;}
 get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
 set textContent(v){this._text=String(v);this.children=[];}
 set innerHTML(html){this.children=[];this._text='';const stack=[this];const voids=['INPUT','BR','META','LINK','HR','PATH','LINE'];
 for(const token of html.matchAll(/<\/?([\w-]+)\b([^>]*?)\/?\s*>|([^<]+)/g)){
 if(token[3]){stack.at(-1)._text+=token[3];continue;}
 if(token[0].startsWith('</')){if(stack.length>1&&stack.at(-1).tagName===token[1].toUpperCase())stack.pop();continue;}
 const child=new Element(token[1]);for(const a of token[2].matchAll(/([\w-]+)(?:="([^"]*)"|='([^']*)'|=([^\s]+))?/g))child.setAttribute(a[1],a[2]??a[3]??a[4]??'');stack.at(-1).appendChild(child);if(!voids.includes(child.tagName)&&!token[0].endsWith('/>'))stack.push(child);
 }}
 appendChild(child){child.parentElement=this;this.children.push(child);return child;}
 replaceChildren(...children){this._text='';this.children=[];for(const c of children)this.appendChild(c);}
 setAttribute(k,v){this.attrs[k]=String(v);if(k.startsWith('data-'))this.dataset[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=String(v);if(k==='value')this._value=String(v);if(['disabled','hidden','checked','selected'].includes(k))this[k]=true;if(k==='type')this.type=v;}
 getAttribute(k){return (k.startsWith('data-')?this.dataset[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]:this.attrs[k])??null;}
 matches(selector){selector=selector.trim();const not=selector.match(/:not\(([^)]+)\)/);if(not){if(this.matches(not[1]))return false;selector=selector.replace(not[0],'');}
 const tag=selector.match(/^[\w-]+/);if(tag&&tag[0].toUpperCase()!==this.tagName)return false;
 for(const m of selector.matchAll(/\.([\w-]+)/g))if(!this.classList.contains(m[1]))return false;
 const id=selector.match(/#([\w-]+)/);if(id&&this.id!==id[1])return false;
 for(const m of selector.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g))if(this.getAttribute(m[1])==null||m[2]!=null&&this.getAttribute(m[1])!==m[2])return false;
 return true;}
 querySelectorAll(selector){const result=[];const walk=node=>{for(const c of node.children){if(selector.split(',').some(s=>c.matches(s)))result.push(c);walk(c);}};walk(this);return result;}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
 closest(selector){return this.matches(selector)?this:this.parentElement?.closest(selector)||null;}
 addEventListener(name,fn){this.listeners[name]=fn;}
 setPointerCapture(){}
 getBoundingClientRect(){return {width:1232,height:535,left:24,top:105};}
 click(){if(this.disabled)return;const event={target:this,preventDefault(){}};return this.onclick?.(event)||this.listeners.click?.(event);}
}
async function run(scenario){
 const document=new Element('document');document.innerHTML=fs.readFileSync('cs2cfg/web/overlay-panel.html','utf8').replace(/<script[\s\S]*?<\/script>/g,'').replace(/<style[\s\S]*?<\/style>/g,'');
 document.documentElement=document.querySelector('html');document.body=document.querySelector('body');document.getElementById=id=>document.querySelector('#'+id);document.createElement=tag=>new Element(tag);document.hidden=false;
 const timers=new Map(),requests=[];let sequence=0,time=0,deferred=null,busy=scenario==='busy';
 const win={overlayRenderers:{},overlayToken:'test-token',addEventListener(){}};
 const context={window:win,document,location:{search:scenario==='preview'?'?preview=1':''},URLSearchParams,AbortController,DOMException,structuredClone,Date,console,performance:{now:()=>time},setTimeout:(fn,ms)=>{const id=++sequence;timers.set(id,{fn,ms});return id;},clearTimeout:id=>timers.delete(id)};
 vm.createContext(context);
 const load=file=>vm.runInContext(fs.readFileSync('cs2cfg/web/assets/overlay/'+file,'utf8'),context,{filename:file});
 load('tools/common.js');for(const id of ['performance','hardware','events','profiles','serverlock','settings'])load('tools/'+id+'.js');load('preview.js');
 const fixture=win.overlayPreview;fixture.manifest.settings.overlay_enabled=true;
 fixture.manifest.settings.overlay_layout={performance:{open:true},hardware:{open:true},profiles:{open:true},serverlock:{open:['busy','missing'].includes(scenario)}};
 const data=fixture.data.performance;data.current.cpu_percent=25;
 const region=()=>scenario==='missing'?{available:false,text:'Coming soon'}:{available:true,text:'Locked to Dubai',poll:busy,regions:[{code:'dxb',city:'Dubai',country:'AE',ping_ms:12,loss:0}],status:{busy,firewall:{code:'dxb'}}};
 context.fetch=async(path,options)=>{
  const body=options.body?JSON.parse(options.body):null;const request={path,body,signal:options.signal};requests.push(request);
  if(scenario==='late'&&path==='/api/overlay/tool'&&body.id==='performance')return new Promise(resolve=>deferred=resolve);
  let result;
  if(path==='/api/overlay/tools')result=structuredClone(fixture.manifest);
  else if(path==='/api/overlay/settings'){Object.assign(fixture.manifest.settings,body);result={settings:fixture.manifest.settings};}
  else if(path==='/api/overlay/tool'){
   if(body.action==='data')result=body.id==='serverlock'?region():structuredClone(fixture.data[body.id]);
   else if(body.action==='layout')result={apply_keys:context.bound===false?[]:['F8']};
   else if(body.action==='setup')result={};
   else if(body.action==='dismiss')result={...data,frame_capture_hint:'',frame_capture_hint_dismissible:false};
   else if(body.action==='save'){Object.assign(fixture.manifest.settings,body.args);result={settings:fixture.manifest.settings};}
  }else result={ok:true};
  return {ok:true,json:async()=>{request.done=true;return result;}};
 };
 load('panel.js');
 const $=id=>document.getElementById(id),tool=id=>document.querySelector('[data-tool="'+id+'"]'),q=(id,s)=>tool(id).querySelector(s);
 const flush=async()=>{for(let i=0;i<100;i++)await Promise.resolve();};
 const tick=async()=>{const batch=[...timers.values()];timers.clear();time+=1000;for(const t of batch){assert(t.ms>=100,'all scheduled work is bounded');t.fn();}await flush();};
 const hide=()=>win.overlayPanelActive(false);
 const count=id=>requests.filter(r=>r.path==='/api/overlay/tool'&&r.body.id===id&&r.body.action==='data').length;
 if(scenario==='preview'){
  await flush();assert.equal(requests.length,0);assert.equal(timers.size,0);assert.equal(q('performance','[data-fps]').textContent,'287.0');
  assert.equal(q('profiles','[data-use-layout]').disabled,true);time+=101;q('performance','[data-range="600"]').click();assert.equal(q('performance','[data-range-label]').textContent,'10 minutes ago');hide();assert.equal(timers.size,0);return;
 }
 assert.equal(requests.length,0);assert.equal(timers.size,0);win.overlayPanelActive(true);await flush();
 if(scenario==='busy'){
  assert.equal(q('serverlock','[data-lock]').disabled,true);await tick();assert.equal(count('serverlock'),2);busy=false;await tick();const n=count('serverlock');await tick();assert.equal(count('serverlock'),n);
 }else if(scenario==='missing'){
  assert.match(tool('serverlock').textContent,/Coming soon/);await tick();assert.equal(count('serverlock'),1);
 }else if(scenario==='profiles'){
  await q('profiles','[data-use-layout]').click();await flush();assert.equal(q('profiles','[data-note]').textContent,'Press F8 in game to load it');assert.equal(requests.at(-1).body.args.file,'competitive');
  context.bound=false;await q('profiles','[data-use-layout]').click();assert.match(q('profiles','[data-note]').textContent,/No Apply Saved Settings key/);
  await q('profiles','[data-use-setup]').click();assert.equal(requests.at(-1).body.action,'setup');
  const before=count('profiles');await tick();assert.equal(count('profiles'),before,'static profiles never poll');
 }else if(scenario==='permissions'){
  data.frame_capture_ready=false;data.frame_capture_hint='Finish setup to enable frame stats';await tick();assert.equal(q('performance','[data-fps]').textContent,'—');assert.match(tool('hardware').textContent,/32.0%/);
  data.frame_capture_hint='Sign out of Windows and back in once';data.frame_capture_hint_dismissible=true;await tick();assert.equal(q('performance','[data-dismiss]').hidden,false);await q('performance','[data-dismiss]').click();assert.equal(q('performance','[data-hint]').textContent,'');
 }else if(scenario==='late'){
  hide();assert(requests.every(r=>r.done||r.signal.aborted));deferred({ok:true,json:async()=>data});await flush();assert.equal(timers.size,0);assert.equal(q('performance','[data-fps]'),null);return;
 }else if(scenario==='visibility'){
  document.hidden=true;document.listeners.visibilitychange();assert.equal(timers.size,0);const n=requests.length;await tick();assert.equal(requests.length,n);document.hidden=false;document.listeners.visibilitychange();await flush();assert(timers.size>0);
 }else if(scenario==='graph'){
  const graph=q('performance','svg.graph'),before=graph.children;for(let i=0;i<30;i++)q('performance','[data-range="600"]').click();assert.equal(graph.children,before);await tick();assert.notEqual(graph.children,before);assert.equal(q('performance','[data-range-label]').textContent,'10 minutes ago');
 }else if(scenario==='layout'){
  tool('performance').querySelector('[data-pin]').click();await flush();assert.equal(requests.at(-1).body.overlay_layout.performance.pinned,true);
  tool('hardware').querySelector('[data-close]').click();await flush();const before=count('hardware');await tick();assert.equal(count('hardware'),before);assert.equal(tool('hardware').hidden,true);hide();win.overlayPanelActive(true);await flush();assert.equal(tool('hardware').hidden,true);assert.equal(tool('performance').querySelector('[data-pin]').getAttribute('aria-pressed'),'true');
  const head=tool('performance').querySelector('.window-head');head.onkeydown({key:'ArrowRight',preventDefault(){}});await flush();assert.equal(requests.at(-1).body.overlay_layout.performance.x,34);
  head.onpointerdown({button:0,target:head,clientX:10,clientY:10,pointerId:1,preventDefault(){}});head.onpointermove({clientX:50,clientY:30});head.onpointerup();await flush();assert.equal(requests.at(-1).body.overlay_layout.performance.x,74);
  const resize=tool('performance').querySelector('.resize');resize.onpointerdown({button:0,target:resize,clientX:0,clientY:0,pointerId:2,preventDefault(){}});resize.onpointermove({clientX:60,clientY:20});resize.onpointerup();await flush();assert.equal(requests.at(-1).body.overlay_layout.performance.width,570);
 }else if(scenario==='close'){
  const before=count('performance');await $('close').click();await flush();assert.equal(timers.size,0);assert.equal(requests.at(-1).path,'/api/overlay/panel');assert.equal(requests.at(-1).body.action,'close');await tick();assert.equal(count('performance'),before);
 }else if(scenario==='opacity'){
  for(const id of ['performance','hardware','events','profiles','serverlock','settings']){
   win.overlayShell.showTool(id);await flush();const input=q(id,'[data-opacity]');assert.equal(Number(input.value),10);
   input.value=0;input.oninput();await input.onchange();await flush();assert.equal(requests.at(-1).body.overlay_layout[id].opacity,0);assert.equal(tool(id).dataset.clear,'true');
   if(id==='settings')assert.equal(q(id,'[data-pin]'),null);else assert(q(id,'[data-pin]'));
  }
  hide();win.overlayPanelActive(true);await flush();assert.equal(Number(q('performance','[data-opacity]').value),0);
  win.overlayShell.showTool('settings');await flush();const slider=q('settings','[data-tool-opacity="hardware"]');slider.value=100;slider.oninput();slider.onchange();await flush();assert.equal(win.overlayShell.layout.hardware.opacity,100);assert.equal(Number(q('hardware','[data-opacity]').value),100);
  const dim=q('settings','[data-setting="overlay_dim_game"]');assert.equal(dim.checked,true);dim.checked=false;await q('settings','[data-save]').click();await flush();assert(document.body.classList.contains('no-dim'));assert.equal(fixture.manifest.settings.overlay_dim_game,false);
  hide();win.overlayPanelActive(true);await flush();assert(document.body.classList.contains('no-dim'));
 }else if(scenario==='settings'){
  win.overlayShell.showTool('settings');await flush();const check=q('settings','[data-tool="hardware"]');check.checked=false;check.onchange();await q('settings','[data-save]').click();await flush();assert.equal(document.querySelector('[data-launch="hardware"]'),null);assert.equal(tool('hardware').hidden,true);
 }
 hide();assert.equal(timers.size,0);const before=requests.length;await tick();assert.equal(requests.length,before);assert(requests.every(r=>r.done||!r.signal||r.signal.aborted));
}
run(process.argv[2]).catch(error=>{console.error(error);process.exitCode=1;});
