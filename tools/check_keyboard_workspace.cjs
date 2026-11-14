/* Runs the real Keyboard renderers and event handlers in offline headless Chrome.
   Only API responses and unrelated tabs are stubbed; no config files are changed. */
const fs=require('fs'),cp=require('child_process'),assert=require('assert'),vm=require('vm');
const path=require('path'),url=require('url');
const root=path.resolve(__dirname,'..');process.chdir(root);
const viewport=process.env.KEYBOARD_VIEWPORT||'1440,900',scale=Number(process.env.KEYBOARD_SCALE||1);
const work=path.join(require('os').tmpdir(),'cs-config-keyboard-'+require('crypto').createHash('sha1').update(root).digest('hex').slice(0,8)+'-'+viewport.replace(',','x')+'-'+scale);fs.mkdirSync(work,{recursive:true});
const page=fs.readFileSync('cs2cfg/web/index.html','utf8');
for(const x of page.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))new vm.Script(x[1]);
new vm.Script(fs.readFileSync('cs2cfg/web/assets/devices/workspace.js','utf8'));
const slice=(a,b)=>page.slice(page.indexOf(a),page.indexOf(b,page.indexOf(a)));
let code=`const $=id=>document.getElementById(id); const esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
let profileData={default_active:true,profiles:[{file:'warmup.cfg',label:'Warmup',override_count:2,active:false,missing_defaults:[]}]};
let layoutData={profiles:[]},layoutPending={},cloudData=null,kbswPopover=null,kbswMenu=null;
const calls=[],notices=[];const confirm=()=>true;function status(t){notices.push(t)}async function ensureScan(){return true}function noFolderYet(){}
const groups=[{id:'movement',name:'Movement',commands:[{label:'Move forward',command:'+forward',icon:'up',hold:true},{label:'Jump',command:'+jump',icon:'jump',hold:true}]},{id:'shoot',name:'Shooting',commands:[{label:'Attack',command:'+attack',icon:'crosshair',hold:true}]}];
const keys={count:5,scripted:1,bound:{scancode26:{label:'W',command:'+forward',is_default:true,file:'key_binds.cfg',line:2},scancode4:{label:'A',command:'say left',is_default:false,file:'key_binds.cfg',line:3},scancode9:{label:'F',command:'tool',script:'Practice tool',enabled:true,file:'tools.cfg',line:8},mouse1:{label:'Mouse 1',command:'+attack',is_default:true,file:'key_binds.cfg',line:4}},live:{available:true,differences:[{key:'a'}]}};
async function api(route,body){calls.push({route,body});if(route==='/api/cfg/keys')return keys;
if(route==='/api/cfg/layouts/profiles')return profileData;if(route==='/api/cfg/layouts/status')return layoutData;
if(route==='/api/cfg/key/options')return {groups,stock:'+forward',current:{command:body.code==='KeyW'?'+forward':''},hold_note:'Held commands run until released.'};
if(route==='/api/cfg/bind')return {ok:true,command:body.command||''};
if(route==='/api/cfg/layouts/apply'){profileData.default_active=false;profileData.profiles[0].active=true;return {changed:false,label:'Warmup'}};
if(route==='/api/cfg/layouts/default'){profileData.default_active=true;profileData.profiles[0].active=false;return {changed:false}};
if(route==='/api/cfg/layouts/copy'||route==='/api/cfg/layouts/create')return {file:'new.cfg',profiles:profileData.profiles};return {ok:true};}
`;
code+=slice('/* --- the keyboard','/* Match demos.');
code+=slice('async function loadKeyboard(force)','$("plug-reload").addEventListener');
code+=`
const checks=[];function check(name,ok){checks.push({name,ok:!!ok});if(!ok)throw Error(name)}
const settle=()=>new Promise(r=>setTimeout(r,35));
async function waitFor(test){const end=performance.now()+3000;while(!test()&&performance.now()<end)await new Promise(r=>setTimeout(r,50));}
const overlaps=(a,b)=>a.left<b.right-.5&&a.right>b.left+.5&&a.top<b.bottom-.5&&a.bottom>b.top+.5;
function checkLayout(name){
 const scene=$('kb-scene').getBoundingClientRect();
 const devices=[...document.querySelectorAll('.kb-piece')].map(e=>e.getBoundingClientRect());
 if(!devices.every(b=>b.left>=scene.left-1&&b.right<=scene.right+1&&b.top>=scene.top&&b.bottom<=scene.bottom+1))checks.push({geometry:{scene,devices,focus:kbFocus}});
 check(name+' pieces inside stage',devices.every(b=>b.left>=scene.left-1&&b.right<=scene.right+1&&b.top>=scene.top&&b.bottom<=scene.bottom+1));
 check(name+' devices side by side',devices.length<2||devices[0].right<devices[1].left);
 const caps=[...document.querySelectorAll('.kb-key')].map(e=>e.getBoundingClientRect());
 check(name+' keys inside stage',caps.every(b=>b.left>=scene.left&&b.right<=scene.right&&b.top>=scene.top&&b.bottom<=scene.bottom));
 const labels=[...document.querySelectorAll('.ms-label')].map(e=>e.getBoundingClientRect());
 check(name+' callouts do not collide',labels.every((b,i)=>labels.slice(i+1).every(c=>!overlaps(b,c)))&&labels.every(b=>caps.every(c=>!overlaps(b,c))));
 const shell=document.querySelector('.ms-shell')?.getBoundingClientRect();
 check(name+' labels outside silhouette',!shell||labels.every(b=>b.right<=shell.left||b.left>=shell.right));
 check(name+' callouts inside stage',labels.every(b=>b.left>=scene.left&&b.right<=scene.right));
 check(name+' flat board',getComputedStyle(document.querySelector('.kb-board')).transform==='none');
 const cards=[...document.querySelectorAll('.kb-settings > .kb-card')].map(e=>e.getBoundingClientRect());
 check(name+' settings columns',document.querySelector('.kb-workspace').clientWidth>620 ? Math.abs(cards[0].top-cards[1].top)<1&&cards[1].left>cards[0].right : cards[1].top>=cards[0].bottom);
 const toggle=$('kb-focus').getBoundingClientRect(),help=document.querySelector('.kb-focus-row > .kb-help').getBoundingClientRect();
 check(name+' focus below stage and above cards',toggle.top>=scene.bottom&&toggle.bottom<cards[0].top);
 check(name+' focus centered with adjacent help',Math.abs((toggle.left+toggle.right)-(scene.left+scene.right))<2&&help.left>toggle.right&&help.left-toggle.right<12);
 check(name+' dotted stage',getComputedStyle($('kb-scene')).backgroundImage.includes('radial-gradient'));
 check(name+' corner help', [...document.querySelectorAll('.kb-card')].every(card=>{const c=card.getBoundingClientRect(),h=card.querySelector('.kb-help').getBoundingClientRect();return h.right<c.right&&c.right-h.right<14&&h.top>c.top&&h.top-c.top<14;}));

}
function key(c){return document.querySelector('[data-kbcode="'+c+'"]')}
function pointer(type,el,x,y){el.dispatchEvent(new PointerEvent(type,{bubbles:true,clientX:x,clientY:y,pointerId:7,button:0}));}
async function drop(command,code,valid=true){const source=document.querySelector('[data-bindcmd="'+command+'"]');const surface=key(code).querySelector('.ms-face')||key(code);surface.scrollIntoView({block:'nearest'});const a=source.getBoundingClientRect(),b=surface.getBoundingClientRect();pointer('pointerdown',source,a.x+10,a.y+10);pointer('pointermove',document,valid?b.x+b.width/2:innerWidth-2,valid?b.y+b.height/2:2);check('drag ghost appears',!!document.querySelector('.kb-drag-ghost'));pointer('pointerup',document,valid?b.x+b.width/2:innerWidth-2,valid?b.y+b.height/2:2);await settle();}
(async()=>{try{
document.querySelector('.boot-screen').remove();document.querySelector('#status')?.remove();document.documentElement.dataset.boot='ready';document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('hidden',p.dataset.panel!=='keyboard'));
document.querySelectorAll('.rail [data-tab]').forEach(tab=>tab.setAttribute('aria-selected',String(tab.dataset.tab==='keyboard')));
await loadKeyboard(true);await document.fonts.ready;await new Promise(r=>setTimeout(r,450));
// Synthetic legacy payloads; never read user preferences.
const fixtures=[null,
 {board:{x:10,y:46,s:1},mouse:{x:720,y:20,s:1}},
 {board:{x:10,y:150,s:1.3},mouse:{x:400,y:65,s:1}},
 {board:{x:136,y:123,s:.981},mouse:{x:1280,y:57,s:1}},
 {version:2,board:{x:-90,y:200,s:2.6},mouse:{x:400,y:70,s:1}},
 {version:2,board:{x:8,y:65,s:.8},mouse:{x:80,y:65,s:1}},
 {version:2,board:{x:8,y:65,s:null},mouse:{x:80,y:65,s:-1}}];
const geometry=()=>{
 const scene=$('kb-scene').getBoundingClientRect();
 return [...document.querySelectorAll('.kb-piece')].map(e=>{const b=e.getBoundingClientRect();return [b.left-scene.left,b.top-scene.top,b.width,b.height];});
};
const sameGeometry=(a,b)=>a.every((row,i)=>row.every((v,j)=>Math.abs(v-b[i][j])<.1));
for(const theme of ['violet','ember','carbon','acid','daylight','paper','pro']){
 document.documentElement.dataset.theme=theme;
 const palette=['script','custom','bound','free','missing','adrift','selected'].map(state=>getComputedStyle(document.querySelector('.kb-legend .dot.'+state)).borderColor+' '+getComputedStyle(document.querySelector('.kb-legend .dot.'+state)).backgroundColor);
 check(theme+' seven distinct legend colors',new Set(palette).size===7);
 for(const rail of [186,340]){
  document.querySelector('.app').style.setProperty('--rail',rail+'px');
  for(const shape of ['two','four']){
   mouseShape=shape;renderKeyboard();await settle();const baseline=geometry();
   for(const [i,saved] of fixtures.entries()){
    kbLoadFocus({kb_layout:saved});renderKeyboard();await settle();checkLayout(theme+'/'+rail+'/'+i+'/'+shape);
    check('legacy geometry ignored',sameGeometry(baseline,geometry()));
   }
  }
 }
}
check('positions never saved',!calls.some(c=>c.route==='/api/prefs'&&(c.body?.kb_layout||c.body?.kb_shown)));
for(const [saved,expected] of [[{kb_shown:{board:false,mouse:true}},'mouse'],[{kb_shown:{board:true,mouse:false}},'board'],[{kb_shown:{board:false,mouse:false}},'both'],[{kb_focus:'both',kb_shown:{board:false}},'both'],[{kb_focus:'invalid'},'both']]){
 kbLoadFocus(saved);check('focus preference migration',kbFocus===expected);
}
kbSetFocus('both');document.querySelector('.kb-workspace').style.width='420px';
await waitFor(()=>{const scene=$('kb-scene').getBoundingClientRect();return [...document.querySelectorAll('.kb-piece')].every(el=>{const b=el.getBoundingClientRect();return b.left>=scene.left&&b.right<=scene.right;});});
checkLayout('narrowed stage');
document.querySelector('.kb-workspace').style.removeProperty('width');document.querySelector('.app').style.removeProperty('--rail');delete document.documentElement.dataset.theme;
mouseShape='two';renderKeyboard();await settle();
check('104 individually interactive keys',document.querySelectorAll('.kb-key').length===104);
check('seven bindable mouse controls',document.querySelectorAll('.ms-zone').length===7);
check('one key per code',new Set([...document.querySelectorAll('.kb-key')].map(k=>k.dataset.kbcode)).size===104);
check('numpad plus and enter span two rows',key('NumpadAdd').offsetHeight>key('KeyW').offsetHeight*1.8&&key('NumpadEnter').offsetHeight>key('KeyW').offsetHeight*1.8);
const board=document.querySelector('.kb-board').getBoundingClientRect(),scene=$('kb-scene').getBoundingClientRect();check('keyboard fits desk',board.left>=scene.left-2&&board.right<=scene.right+2);
check('state colors are under neutral caps',getComputedStyle(key('KeyW')).backgroundImage===getComputedStyle(key('KeyA')).backgroundImage&&getComputedStyle(key('KeyW')).boxShadow!==getComputedStyle(key('KeyA')).boxShadow);
key('KeyW').click();await settle();check('selection opens inspector and library',document.querySelector('.kb-detail-key').textContent==='W'&&!!$('kb-search'));
check('source link retained',document.querySelector('[data-open-file]').dataset.openFile==='key_binds.cfg');
key('KeyW').dispatchEvent(new PointerEvent('pointerover',{bubbles:true}));await new Promise(r=>setTimeout(r,230));check('hover preview shows command',document.querySelector('.kb-hover-preview')?.textContent.includes('+forward'));key('KeyW').dispatchEvent(new PointerEvent('pointerout',{bubbles:true,relatedTarget:document.body}));
$('kb-search').value='attack';$('kb-search').dispatchEvent(new Event('input',{bubbles:true}));check('search spans categories',document.querySelectorAll('[data-bindcmd]').length===1&&!!document.querySelector('[data-bindcmd="+attack"]'));
document.querySelector('[data-kbgroup="movement"]').click();await settle();
document.querySelector('[data-bindcmd="+jump"]').click();await settle();check('click uses bind API',calls.some(c=>c.route==='/api/cfg/bind'&&c.body.code==='KeyW'&&c.body.command==='+jump'));
await new Promise(r=>setTimeout(r,450));await drop('+forward','KeyE');check('pointer drop binds destination',calls.some(c=>c.route==='/api/cfg/bind'&&c.body.code==='KeyE'&&c.body.command==='+forward'));
check('successful assignment animation',key('KeyE').classList.contains('kb-assigned'));
document.documentElement.classList.add('kb-motion-paused');check('hidden-window assignment animation pauses',getComputedStyle(key('KeyE'),'::after').animationPlayState==='paused');document.documentElement.classList.remove('kb-motion-paused');
if(matchMedia('(prefers-reduced-motion: reduce)').matches)check('reduced motion disables assignment ripple',getComputedStyle(key('KeyE'),'::after').animationName==='none');
const cancelSource=document.querySelector('[data-bindcmd]');pointer('pointerdown',cancelSource,10,10);pointer('pointermove',document,30,30);document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));check('Escape cancels pointer drag',!document.querySelector('.kb-drag-ghost'));
const cancelCount=calls.filter(c=>c.route==='/api/cfg/bind').length;cancelSource.click();await settle();check('cancelled drag cannot click-assign',calls.filter(c=>c.route==='/api/cfg/bind').length===cancelCount);
pointer('pointerdown',cancelSource,10,10);pointer('pointermove',document,30,30);document.dispatchEvent(new PointerEvent('pointercancel',{pointerId:7,bubbles:true}));check('pointer cancellation cleans up',!document.querySelector('.kb-drag-ghost'));
await new Promise(r=>setTimeout(r,450));await drop('+jump','mouse2');check('mouse accepts pointer drop',calls.some(c=>c.route==='/api/cfg/bind'&&c.body.code==='mouse2'&&c.body.command==='+jump'));
await new Promise(r=>setTimeout(r,450));const before=calls.filter(c=>c.route==='/api/cfg/bind').length;await drop('+jump','KeyQ',false);check('drop outside cancels',calls.filter(c=>c.route==='/api/cfg/bind').length===before&&!document.querySelector('.kb-drag-ghost'));
await new Promise(r=>setTimeout(r,450));document.querySelector('[data-mouseshape="four"]').click();check('four-side mouse exposes M6 and M7',!!key('mouse6')&&!!key('mouse7'));check('variant persisted',calls.some(c=>c.route==='/api/prefs'&&c.body.mouse_shape==='four'));
key('mouse6').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));await settle();check('mouse keyboard accessible',pickedKey.code==='mouse6');
const beforeFocus=geometry();
for(const mode of ['board','mouse']){
 document.querySelector('[data-kbfocus="'+mode+'"]').click();await new Promise(r=>setTimeout(r,350));
 const ghost=document.querySelector('.is-ghost'),body=ghost.querySelector('.kb-device-body');
 await waitFor(()=>+getComputedStyle(body).opacity<=.2);
 check(mode+' focus fades other device',ghost.dataset.piece!==mode&&+getComputedStyle(body).opacity<=.2);
 check(mode+' ghost is inert and unfocusable',body.inert&&[...body.querySelectorAll('[data-kbcode]')].every(e=>e.tabIndex===-1));
 const old=pickedKey.code,control=body.querySelector('[data-kbcode]');control.dispatchEvent(new MouseEvent('click',{bubbles:true}));control.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
 check('ghost cannot select',pickedKey.code===old);
 control.dispatchEvent(new PointerEvent('pointerover',{bubbles:true}));await new Promise(r=>setTimeout(r,230));check('ghost has no preview',!document.querySelector('.kb-hover-preview'));
 check('focus keeps geometry',sameGeometry(beforeFocus,geometry()));
}
kbSetFocus('both');await new Promise(r=>setTimeout(r,450));kbSetFocus('mouse');
const ghostBinds=calls.filter(c=>c.route==='/api/cfg/bind').length;await drop('+jump','KeyW');check('ghost rejects drops',calls.filter(c=>c.route==='/api/cfg/bind').length===ghostBinds);kbSetFocus('both');await new Promise(r=>setTimeout(r,450));
check('one focus control only',document.querySelectorAll('[data-kbghost],[data-kbghost-toggle],.kb-eye').length===0&&document.querySelectorAll('#kb-focus').length===1);
check('one shape picker only',document.querySelectorAll('.ms-pick').length===1&&!document.querySelector('.kb-piece .ms-pick'));
document.querySelector('[data-kbfocus="mouse"]').click();check('toggle ghosts keyboard',kbFocus==='mouse');kbSetFocus('both');
check('focus preference persisted',calls.some(c=>c.route==='/api/prefs'&&c.body.kb_focus==='mouse'));
document.querySelector('[data-kbsw]').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true}));check('profile context menu retained',document.querySelectorAll('[data-kbsw-menu]').length===4);kbswMenu=null;renderKbSwitcher();
document.querySelector('[data-kbsw]').click();await settle();check('profile switch API preserved',calls.some(c=>c.route==='/api/cfg/layouts/apply'));
profileData.profiles[0].missing_defaults=Array.from({length:6},(_,i)=>({key:'scancode'+(4+i),label:'Key '+i,command:'+jump'}));renderKeyboard();check('missing list and count retained',document.querySelectorAll('.kb-missing-row').length===6&&document.querySelector('.kb-missing-count').textContent==='6');
document.querySelector('[data-kbsw-default]').click();await settle();check('default profile API preserved',calls.some(c=>c.route==='/api/cfg/layouts/default'));
document.querySelector('[data-kbsw-add]').click();check('profile create opens naming control',!!$('kbsw-name'));$('kbsw-name').value='Test';$('kbsw-name-go').click();await settle();check('profile create API preserved',calls.some(c=>c.route==='/api/cfg/layouts/create'&&c.body.name==='Test'));
openKbswCopyPopover('warmup.cfg','Warmup');$('kbsw-name').value='Warmup copy';$('kbsw-name-go').click();await settle();check('profile copy API preserved',calls.some(c=>c.route==='/api/cfg/layouts/copy'&&c.body.name==='Warmup copy'));
const reloads=calls.filter(c=>c.route==='/api/cfg/keys').length;$('kb-reload').click();await settle();check('re-read reloads keys',calls.filter(c=>c.route==='/api/cfg/keys').length>reloads);
mouseShape='two';kbSetFocus('both');renderKeyboard();checkLayout('final');
check('removed layout UI absent',!document.querySelector('.kb-grip,.kb-edge,#kb-reset,[data-kbshow]'));
profileData.profiles[0].active=true;profileData.profiles[0].missing_defaults=[{key:'scancode4',label:'A',command:'+left'},{key:'mouse2',label:'Mouse 2',command:'+attack2'}];keys.bound.scancode4.agrees=false;renderKeyboard();
check('missing defaults highlight keys and mouse',key('KeyA').classList.contains('kb-missing')&&key('mouse2').classList.contains('kb-missing'));
check('live drift highlight retained',key('KeyA').classList.contains('adrift'));
check('missing and live drift colors differ',getComputedStyle(key('KeyA'),'::before').borderColor!==getComputedStyle(key('KeyA'),'::after').backgroundColor);
profileData.profiles[0].active=false;keys.bound.scancode4.agrees=true;renderKeyboard();
key('KeyE').click();await settle();document.querySelector('[data-bindstock]').click();await settle();check('restore default uses force',calls.some(c=>c.route==='/api/cfg/bind'&&c.body.force===true));
for(const theme of ['violet','ember','carbon','acid','daylight','paper','pro']){document.documentElement.dataset.theme=theme;check('theme '+theme+' keeps device and text',getComputedStyle(key('KeyW')).color!==getComputedStyle(key('KeyW')).backgroundColor&&getComputedStyle(document.querySelector('.kb-inspector')).display!=='none');}
delete document.documentElement.dataset.theme;
if(${JSON.stringify(process.env.KEYBOARD_THEME||'')})document.documentElement.dataset.theme=${JSON.stringify(process.env.KEYBOARD_THEME||'')};
check('no horizontal overflow',document.documentElement.scrollWidth<=innerWidth);
key('KeyW').click();await new Promise(r=>setTimeout(r,350));document.querySelector('.scroll').scrollTop=0;

}catch(e){checks.push({error:e.stack})}document.body.insertAdjacentHTML('beforeend','<pre id="checks">'+JSON.stringify(checks)+'</pre>');})();`;
let html=page.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'');
html=html.replace('<head>','<head><base href="'+url.pathToFileURL(path.join(root,'cs2cfg/web/')).href+'">');
html=html.replace('</body>','<script src="assets/devices/workspace.js"></script><script>'+code+'</script></body>');
fs.writeFileSync(path.join(work,'preview.html'),html);
const chrome=process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe';
// Use real compositor frames rather than --virtual-time-budget: ResizeObserver
// and transitions need to settle before measuring the result of a live resize.
const args=['--headless','--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows','--no-sandbox','--disable-gpu','--allow-file-access-from-files','--remote-debugging-port=0','--user-data-dir='+path.join(work,'chrome'),'about:blank'];
if(process.env.KEYBOARD_REDUCED)args.unshift('--force-prefers-reduced-motion');
(async()=>{
 const browser=cp.spawn(chrome,args,{stdio:['ignore','ignore','pipe'],windowsHide:true});let socket;
 try{
  const endpoint=await new Promise((resolve,reject)=>{
   let stderr='';const timer=setTimeout(()=>reject(Error('Chrome startup timed out')),15000);
   browser.stderr.on('data',chunk=>{stderr+=chunk;const match=stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);if(match){clearTimeout(timer);resolve(match[1]);}});
   browser.on('error',reject);
  });
  socket=new WebSocket(endpoint);await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  let id=0;const pending=new Map();
  socket.onmessage=e=>{const result=JSON.parse(e.data);if(result.id){const p=pending.get(result.id);pending.delete(result.id);if(result.error)p.reject(Error(JSON.stringify(result.error)));else p.resolve(result.result);}};
  const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params,sessionId}));});
  const {targetId}=await send('Target.createTarget',{url:'about:blank'});
  const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
  const command=(method,params)=>send(method,params,sessionId);
  const [width,height]=viewport.split(',').map(Number);
  await command('Emulation.setDeviceMetricsOverride',{width:Math.round(width/scale),height:Math.round(height/scale),deviceScaleFactor:scale,mobile:false});
  await command('Page.enable');
  await command('Page.navigate',{url:url.pathToFileURL(path.join(work,'preview.html')).href});
  let results;const deadline=Date.now()+45000;
  while(Date.now()<deadline){
   const {result}=await command('Runtime.evaluate',{expression:'document.getElementById("checks")?.textContent',returnByValue:true});
   if(result.value){results=JSON.parse(result.value);break;}
   await new Promise(r=>setTimeout(r,100));
  }
  assert(results,'browser checks timed out');
  const {result}=await command('Runtime.evaluate',{expression:'document.documentElement.outerHTML',returnByValue:true});
  fs.writeFileSync(path.join(work,'dom.html'),result.value);
  const shot=await command('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(work,'preview.png'),Buffer.from(shot.data,'base64'));
  for(const mode of ['board','mouse']){
   await command('Runtime.evaluate',{expression:"kbSetFocus('"+mode+"');new Promise(r=>setTimeout(r,350))",awaitPromise:true});
   const focused=await command('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(work,'focus-'+mode+'.png'),Buffer.from(focused.data,'base64'));
  }
  await command('Runtime.evaluate',{expression:"kbSetFocus('both');new Promise(r=>setTimeout(r,350))",awaitPromise:true});
  if(process.env.KEYBOARD_CAPTURE_THEMES){
   for(const theme of ['violet','ember','carbon','acid','daylight','paper','pro']){
    await command('Runtime.evaluate',{expression:'document.documentElement.dataset.theme='+JSON.stringify(theme)+';new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))',awaitPromise:true});
    const themed=await command('Page.captureScreenshot',{format:'png'});
    fs.writeFileSync(path.join(work,theme+'.png'),Buffer.from(themed.data,'base64'));
   }
  }
  const failures=results.filter(c=>c.ok===false||c.error||c.geometry);
  console.log(JSON.stringify({viewport,scale,checks:results.length,failures,preview:path.join(work,'preview.png')}));
  assert(results.length>1500&&!failures.length);
 }finally{if(socket)socket.close();browser.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
