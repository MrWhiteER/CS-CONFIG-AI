/* Runs the real Keyboard renderers and event handlers in offline headless Chrome.
   Only API responses and unrelated tabs are stubbed; no config files are changed. */
const fs=require('fs'),cp=require('child_process'),assert=require('assert'),vm=require('vm');
const path=require('path'),url=require('url');
const root=path.resolve(__dirname,'..');process.chdir(root);
const work=path.join(require('os').tmpdir(),'cs-config-keyboard-'+require('crypto').createHash('sha1').update(root).digest('hex').slice(0,8));fs.mkdirSync(work,{recursive:true});
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
function key(c){return document.querySelector('[data-kbcode="'+c+'"]')}
function pointer(type,el,x,y){el.dispatchEvent(new PointerEvent(type,{bubbles:true,clientX:x,clientY:y,pointerId:7,button:0}));}
async function drop(command,code,valid=true){const source=document.querySelector('[data-bindcmd="'+command+'"]');const surface=key(code).querySelector('.ms-face')||key(code);surface.scrollIntoView({block:'nearest'});const a=source.getBoundingClientRect(),b=surface.getBoundingClientRect();pointer('pointerdown',source,a.x+10,a.y+10);pointer('pointermove',document,valid?b.x+b.width/2:innerWidth-2,valid?b.y+b.height/2:2);check('drag ghost appears',!!document.querySelector('.kb-drag-ghost'));pointer('pointerup',document,valid?b.x+b.width/2:innerWidth-2,valid?b.y+b.height/2:2);await settle();}
(async()=>{try{
document.querySelector('.boot-screen').remove();document.documentElement.dataset.boot='ready';document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('hidden',p.dataset.panel!=='keyboard'));
await loadKeyboard(true);await settle();
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
const toggle=document.querySelector('[data-kbshow="mouse"]');toggle.checked=false;toggle.dispatchEvent(new Event('change',{bubbles:true}));check('visibility toggle preserves keyboard',!document.querySelector('[data-piece="mouse"]')&&!!key('KeyW'));
document.querySelector('[data-kbsw]').click();await settle();check('profile switch API preserved',calls.some(c=>c.route==='/api/cfg/layouts/apply'));
profileData.profiles[0].missing_defaults=Array.from({length:6},(_,i)=>({key:'scancode'+(4+i),label:'Key '+i,command:'+jump'}));renderKeyboard();check('missing list and count retained',document.querySelectorAll('.kb-missing-row').length===6&&document.querySelector('.kb-missing-count').textContent==='6');
document.querySelector('[data-kbsw-default]').click();await settle();check('default profile API preserved',calls.some(c=>c.route==='/api/cfg/layouts/default'));
document.querySelector('[data-kbsw-add]').click();check('profile create opens naming control',!!$('kbsw-name'));$('kbsw-name').value='Test';$('kbsw-name-go').click();await settle();check('profile create API preserved',calls.some(c=>c.route==='/api/cfg/layouts/create'&&c.body.name==='Test'));
openKbswCopyPopover('warmup.cfg','Warmup');$('kbsw-name').value='Warmup copy';$('kbsw-name-go').click();await settle();check('profile copy API preserved',calls.some(c=>c.route==='/api/cfg/layouts/copy'&&c.body.name==='Warmup copy'));
const reloads=calls.filter(c=>c.route==='/api/cfg/keys').length;$('kb-reload').click();await settle();check('re-read reloads keys',calls.filter(c=>c.route==='/api/cfg/keys').length>reloads);
kbShown.mouse=true;mouseShape='two';renderKeyboard();$('kb-reset').click();check('reset fits both devices',kbLayout.board.x===10&&kbLayout.mouse.y>=300);
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
const args=['--headless','--no-sandbox','--disable-gpu','--allow-file-access-from-files','--user-data-dir='+path.join(work,'chrome'),'--window-size='+(process.env.KEYBOARD_VIEWPORT||'1440,1100'),'--virtual-time-budget=8000',url.pathToFileURL(path.join(work,'preview.html')).href];
if(process.env.KEYBOARD_REDUCED)args.unshift('--force-prefers-reduced-motion');
const out=cp.execFileSync(chrome,[...args,'--dump-dom'],{maxBuffer:5e6,stdio:['ignore','pipe','ignore']}).toString();fs.writeFileSync(path.join(work,'dom.html'),out);
cp.execFileSync(chrome,[...args,'--screenshot='+path.join(work,'preview.png')],{stdio:'ignore'});
const result=[...out.matchAll(/<pre id="checks">(.*?)<\/pre>/gs)].at(-1);console.log(result?result[1]:'NO TEST RESULTS');assert(result&&!result[1].includes('false')&&!result[1].includes('"error"'));
