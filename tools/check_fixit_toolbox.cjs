/* Offline Fix It integration checks. Never starts a server or invokes real fixes.
   All API calls are in-memory mocks; profiles and screenshots stay in OS temp. */
const fs=require('fs'),os=require('os'),path=require('path'),url=require('url'),cp=require('child_process'),vm=require('vm'),assert=require('assert');
const root=path.resolve(__dirname,'..'),work=fs.mkdtempSync(path.join(os.tmpdir(),'cs2-fixit-'));
const html=fs.readFileSync(path.join(root,'cs2cfg/web/index.html'),'utf8');
for(const s of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))new vm.Script(s[1]);
const slice=(a,b)=>html.slice(html.indexOf(a),html.indexOf(b,html.indexOf(a)));
const themes=vm.runInNewContext(slice('const THEMES = [','function applyTheme(').replace('const THEMES =','')).map(t=>t[0]);
const catalogue=fs.readFileSync(path.join(root,'cs2cfg/quickfix.py'),'utf8').split('CATALOGUE: List[Fix] = [')[1].split('\n]\n')[0];
const fixes=[...catalogue.matchAll(/Fix\("([^"]+)", "([^"]+)", "([^"]+)"([\s\S]*?)(?=\n    Fix\(|$)/g)].map(m=>({id:m[1],family:m[2],title:m[3],blurb:'Backend explanation for '+m[3],needs_admin:m[4].includes('needs_admin=True'),disruptive:m[4].includes('disruptive=True'),allowed_in_game:m[4].includes('allowed_in_game=True'),danger:m[4].includes('danger=')?'Full backend caution for '+m[3]:''}));
assert.equal(fixes.length,16);
let code=`
const $=id=>document.getElementById(id),esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
const checks=[],calls=[],messages=[];const check=(name,ok)=>{checks.push({name,ok:!!ok});if(!ok)throw Error(name)};
const settle=()=>new Promise(r=>setTimeout(r,35));function status(message,error){messages.push({message,error})}
let answer={ok:true,fixes:${JSON.stringify(fixes)},adapters:[{name:'Ethernet',speed:'1 Gbps'},{name:'Wi-Fi',speed:'866 Mbps',wireless:true}],devices:[{id:'only',name:'Keyboard',class:'Keyboard',common:true,restartable:false},{id:'audio',name:'GoXLR',class:'AudioEndpoint',common:true,restartable:true},{id:'usb',name:'USB hub',class:'USB',common:false,restartable:true}],sound:{devices:[{name:'TC-HELICON GoXLR',status:'OK'}],special:['TC-HELICON GoXLR']},zombie_cs2:true,defender:{supported:true,excluded:false},fullscreen:{supported:true,disabled:false},power:{supported:true,boosted:false}};
let response={ok:true,detail:'Mock repair completed'},pending=null,surveyWait=null,readError=false,accept=true,confirmations=[],launches=0;
window.confirm=text=>{confirmations.push(text);return accept};$('play').addEventListener('click',()=>launches++);
async function api(route,body){calls.push({route,body});if(route==='/api/fix/survey'){if(surveyWait)return new Promise(r=>surveyWait=r);if(readError)throw Error('mock survey unavailable');return structuredClone(answer)}if(route!=='/api/fix/run')throw Error('Unexpected endpoint '+route);if(pending)return new Promise(r=>pending=r);if(response instanceof Error)throw response;return structuredClone(response)}
`+slice('let fixData = null;','// Horizontal thermal strips')+`
document.documentElement.dataset.boot='ready';document.querySelector('.boot-screen')?.remove();document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('hidden',p.dataset.panel!=='fix'));
const tile=id=>document.querySelector('[data-tool="'+id+'"]'),btn=id=>document.querySelector('[data-fix="'+id+'"]');
(async()=>{try{
await loadFixes();check('16 tools rendered',document.querySelectorAll('.fix-tile').length===16);check('all tools have idle state',document.querySelectorAll('[data-state="idle"]').length===16);
check('literal unique illustrations',new Set([...document.querySelectorAll('.fix-ic svg')].map(s=>s.innerHTML)).size===16);
check('full explanation expandable',tile('net.restart').querySelector('.fix-details p').textContent.includes('Backend explanation'));
check('admin and match chips',tile('net.restart').querySelectorAll('.fix-chip svg').length===2);check('GPU allowed in game',!tile('gpu.restart').querySelector('.fix-chip'));
check('connection target reported',tile('net.restart').textContent.includes('1 Gbps'));check('audio does not claim CS2 routing',tile('sound.apps').textContent.includes('CS2 routing is not reported'));
check('desktop mode not invented',tile('display.restore').textContent.includes('not reported'));
const only=$('fix-device').querySelector('[value="only"]');check('only keyboard stays disabled',only.disabled);check('common devices only',$('fix-device').options.length===2);
$('fix-all-devices').click();$('fix-device').value='usb';$('fix-device').dispatchEvent(new Event('change'));$('fix-adapter').value='Wi-Fi';$('fix-steam-play').checked=false;renderFixes();
check('selections survive render',$('fix-device').value==='usb'&&$('fix-adapter').value==='Wi-Fi'&&$('fix-all-devices').checked&&!$('fix-steam-play').checked);
accept=false;const before=calls.length;await runFix(btn('net.restart'));check('cancel confirmation never calls API',calls.length===before);accept=true;
pending=true;const running=runFix(btn('net.restart'));await settle();check('fixing state and honest progress',tile('net.restart').dataset.state==='fixing'&&!$(fixProgId('net.restart')).hidden&&tile('net.restart').textContent.includes('Restarting the selected connection'));
if(matchMedia('(prefers-reduced-motion: reduce)').matches)check('reduced progress static',getComputedStyle(tile('net.restart').querySelector('.fix-track i')).animationName==='none');
check('running controls locked',$('fix-adapter').disabled&&btn('net.restart').disabled);const count=calls.length;await loadFixes(true);check('survey cannot replace active fix',calls.length===count);await runFix(btn('net.restart'));check('double run blocked',calls.length===count);
pending({ok:true,detail:'Wi-Fi came back up'});pending=null;await running;check('fixed timestamp',tile('net.restart').dataset.state==='fixed'&&/\\d{2}:\\d{2}/.test(tile('net.restart').querySelector('.fix-state').textContent));check('adapter payload',calls.at(-1).body.adapter==='Wi-Fi');
renderFixes();check('result survives render',tile('net.restart').textContent.includes('Wi-Fi came back up'));
for(const fix of answer.fixes){response={ok:true,detail:'Mock '+fix.id,steps:fix.id==='steam.restart'?['asked Steam to close','started Steam','sign-in pending']:undefined,signed_in:false,excluded:true,disabled:true,boosted:true,plan:'High performance'};await runFix(btn(fix.id));check(fix.id+' endpoint',calls.at(-1).route==='/api/fix/run'&&calls.at(-1).body.id===fix.id);check(fix.id+' completion',tile(fix.id).dataset.state==='fixed');}
check('device payload selected',calls.some(c=>c.body.device==='usb'));check('Steam opt out preserved',calls.some(c=>c.body.id==='steam.restart'&&c.body.then_play===false));check('Steam step log shown',tile('steam.restart').querySelector('.fix-said ol').children.length===3);check('Steam pending sign in honest',tile('steam.restart').textContent.includes('sign-in pending')&&launches===0);
check('openers say Opened',tile('steam.verify').querySelector('.fix-state').textContent.startsWith('Opened'));check('toggle label updates',btn('defender.exclude').textContent==='Remove the exclusion'&&btn('fullscreen.exclusive').textContent==='Turn it back on');
response={ok:false,blocked:true,error:'CS2 is running. Close the game first.'};await runFix(btn('sound.restart'));check('backend guard displayed',tile('sound.restart').dataset.state==='failed'&&tile('sound.restart').textContent.includes(response.error)&&btn('sound.restart').textContent.startsWith('Retry'));
response=new Error('<mock transport error>');await runFix(btn('sound.restart'));check('transport failure escaped',tile('sound.restart').textContent.includes('<mock transport error>')&&!tile('sound.restart').querySelector('mock'));
response={ok:false,declined:true,error:'administrator prompt declined'};await runFix(btn('sound.restart'));check('declined returns idle with reason',tile('sound.restart').dataset.state==='idle'&&tile('sound.restart').textContent.includes('Cancelled'));
response={ok:true,detail:'Audio restarted'};await runFix(btn('sound.restart'));check('retry succeeds',tile('sound.restart').dataset.state==='fixed');
$('fix-steam-play').checked=true;response={ok:true,detail:'Steam signed in',then_play:true,signed_in:true};await runFix(btn('steam.restart'));check('Steam uses ordinary launch',launches===1);
surveyWait=true;const checking=loadFixes(true);await settle();check('each card shows checking',document.querySelectorAll('[data-state="checking"]').length===16);check('checking locks actions',btn('net.flush').disabled);surveyWait(structuredClone(answer));surveyWait=null;await checking;check('checking restores durable outcomes',tile('sound.restart').dataset.state==='fixed');
readError=true;await loadFixes(true);check('survey error retryable and outcomes retained',!!document.querySelector('.fix-survey-error')&&!$('fix-refresh').disabled&&tile('sound.restart').dataset.state==='fixed');readError=false;await loadFixes(true);check('survey recovers',!document.querySelector('.fix-survey-error'));
const soundTab=[...document.querySelectorAll('.fix-categories button')].find(b=>b.textContent==='Sound');soundTab.click();check('category filters tools',[...document.querySelectorAll('.fix-tile')].filter(t=>!t.hidden).length===3);document.querySelector('.fix-categories button').click();
for(const theme of ${JSON.stringify(themes)}){document.documentElement.dataset.theme=theme;await settle();check(theme+' no horizontal overflow',document.querySelector('.scroll').scrollWidth<=document.querySelector('.scroll').clientWidth);check(theme+' readable',getComputedStyle(tile('net.restart')).backgroundColor!==getComputedStyle(tile('net.restart').querySelector('h3')).color)}
document.querySelector('[data-panel="fix"]').classList.add('hidden');check('hidden panel pauses gear',getComputedStyle(document.querySelector('.fix-gear')).animationPlayState==='paused');document.querySelector('[data-panel="fix"]').classList.remove('hidden');Object.defineProperty(document,'hidden',{configurable:true,value:true});fixPauseMotion();check('hidden app pauses gear',getComputedStyle(document.querySelector('.fix-gear')).animationPlayState==='paused');delete document.hidden;fixPauseMotion();if(matchMedia('(prefers-reduced-motion: reduce)').matches)check('reduced motion',getComputedStyle(document.querySelector('.fix-gear')).animationName==='none');
answer.devices=[];answer.adapters=[];answer.zombie_cs2=false;answer.defender.supported=false;answer.fullscreen.supported=false;answer.power.supported=false;await loadFixes(true);check('unavailable tools disabled',['net.restart','device.restart','steam.zombie','defender.exclude','fullscreen.exclusive','power.performance'].every(id=>btn(id).disabled));
answer.devices=[{id:'only',name:'Only keyboard',class:'Keyboard',common:true,restartable:false}];await loadFixes(true);check('no restartable device disables action',btn('device.restart').disabled);
// Screenshot a realistic idle bench with one durable repair result.
fixStates.clear();fixStates.set('net.flush',{phase:'fixed',at:Date.now(),text:'DNS cache cleared'});fixData={...answer,adapters:[{name:'Ethernet',speed:'1 Gbps'}],devices:[{id:'audio',name:'GoXLR',class:'AudioEndpoint',common:true,restartable:true}],defender:{supported:true,excluded:false},fullscreen:{supported:true,disabled:false},power:{supported:true,boosted:false}};renderFixes();delete document.documentElement.dataset.theme;document.querySelector('.scroll').scrollTop=0;
}catch(e){checks.push({error:e.stack})}document.body.insertAdjacentHTML('beforeend','<pre id="checks" hidden>'+JSON.stringify(checks)+'</pre>')})();`;
let page=html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'').replace('<head>','<head><base href="'+url.pathToFileURL(path.join(root,'cs2cfg/web/')).href+'">');
page=page.replace('</body>','<script>'+code.replaceAll('</script','<\\/script')+'</script></body>');fs.writeFileSync(path.join(work,'preview.html'),page);
const args=['--headless','--no-sandbox','--disable-gpu','--allow-file-access-from-files','--remote-debugging-port=0','--user-data-dir='+path.join(work,'chrome'),'about:blank'];
if(process.env.FIXIT_REDUCED)args.unshift('--force-prefers-reduced-motion');
(async()=>{
 const browser=cp.spawn(process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',args,{stdio:['ignore','ignore','pipe'],windowsHide:true});let socket;
 try{
 const endpoint=await new Promise((resolve,reject)=>{let err='';const timer=setTimeout(()=>reject(Error('Chrome startup timeout')),15000);browser.stderr.on('data',c=>{err+=c;const m=err.match(/DevTools listening on (ws:\/\/[^\s]+)/);if(m){clearTimeout(timer);resolve(m[1])}});browser.on('error',reject)});
 socket=new WebSocket(endpoint);await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});let id=0;const pending=new Map();
 socket.onmessage=e=>{const r=JSON.parse(e.data);if(r.id){const p=pending.get(r.id);pending.delete(r.id);r.error?p.reject(Error(JSON.stringify(r.error))):p.resolve(r.result)}};
 const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params,sessionId}))});
 const {targetId}=await send('Target.createTarget',{url:'about:blank'}),{sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});const command=(method,params)=>send(method,params,sessionId);
 const [width,height]=(process.env.FIXIT_VIEWPORT||'1440,1000').split(',').map(Number);
 await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await command('Page.enable');await command('Page.navigate',{url:url.pathToFileURL(path.join(work,'preview.html')).href});
 let results;const deadline=Date.now()+25000;while(Date.now()<deadline){const {result}=await command('Runtime.evaluate',{expression:'document.getElementById("checks")?.textContent',returnByValue:true});if(result.value){results=JSON.parse(result.value);break}await new Promise(r=>setTimeout(r,100))}
 assert(results,'browser checks timeout');await new Promise(r=>setTimeout(r,300));
 for(const [name,expression] of [['toolbox','document.querySelector(".scroll").scrollTop=0'],['sound','document.querySelector(".scroll").scrollTop=document.getElementById("fix-device").offsetTop-40'],['daylight','document.documentElement.dataset.theme="daylight";document.querySelector(".scroll").scrollTop=0']]){await command('Runtime.evaluate',{expression});await new Promise(r=>setTimeout(r,100));const shot=await command('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(work,name+'.png'),Buffer.from(shot.data,'base64'))}
 const failures=results.filter(r=>r.ok===false||r.error);console.log(JSON.stringify({checks:results.length,failures,artifacts:work}));assert(!failures.length&&results.length>60);
 }finally{socket?.close();browser.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});


