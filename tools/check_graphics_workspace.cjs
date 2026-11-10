/* Offline integration checks of the real Graphics renderer and action handlers.
   Chrome profiles, fixture HTML and screenshots are created only in OS temp.
   No real display/driver API is invoked. Run: node tools/check_graphics_workspace.cjs */
const fs=require('fs'), os=require('os'), path=require('path'), url=require('url'), cp=require('child_process'), vm=require('vm'), assert=require('assert');
const root=path.resolve(__dirname,'..');
const work=fs.mkdtempSync(path.join(os.tmpdir(),'cs2-graphics-'));
const html=fs.readFileSync(path.join(root,'cs2cfg/web/index.html'),'utf8');
for(const s of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)) new vm.Script(s[1]);
const slice=(a,b)=>html.slice(html.indexOf(a),html.indexOf(b,html.indexOf(a)));
const themes=vm.runInNewContext(slice('const THEMES = [','function applyTheme(').replace('const THEMES =','')).map(t=>t[0]);
let code=`
const $=id=>document.getElementById(id), esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
const checks=[],calls=[],messages=[]; const check=(name,ok)=>{checks.push({name,ok:!!ok});if(!ok)throw Error(name)};
const settle=()=>new Promise(r=>setTimeout(r,40));function status(message,error){messages.push({message,error})}
const setting=(name,predefined,id='0x12345678',value='0x00000011')=>({name,predefined,id,value,known:!!name});
const fixture={displays:{displays:[240,165].map((refresh,i)=>({device:'Display'+(i+1),name:'NVIDIA GeForce RTX 3090 Ti',primary:!i,width:2560,height:1440,refresh,rates:[refresh,120,60],best:refresh,at_best:true}))},scaling:{available:true,displays:[240,165].map((refresh,i)=>({id:'0x8006108'+i,primary:!i,width:2560,height:1440,refresh,scaling:2,name:'full-screen',fills:true,bars:false}))},nvidia:{available:true,driver:'621.01',branch:'r620_97',profiles:8045,catalogue:128,catalogue_3d:[{id:'0x1',name:'Power management mode',overridden:false,value:''},{id:'0x2',name:'Maximum pre-rendered frames',overridden:true,value:'0x00000002'},{id:'0x3',name:'Driver built-in entry',overridden:true,value:'0x00000001'}],global:{settings:[setting('Maximum pre-rendered frames',false,'0x2'),setting('Driver built-in entry',true,'0x3')]},apps:{'cs2.exe':{name:'Counter-Strike 2',settings:[setting('Enable application for Optimus',true),setting('Enable Streamline override',false,'0x4'),setting('',false,'0x9999')]},'csgo.exe':{name:'Counter-Strike: Global Offensive',settings:[setting('Maximum pre-rendered frames',true)]}}}};
let answer=structuredClone(fixture), failure='',readFailure=false;
async function api(route,body){calls.push({route,body});if(route==='/api/gpu'){if(readFailure)throw Error('read failed');return structuredClone(answer)}if(failure)return {ok:false,error:failure};return {ok:true,note:'applied',previous:'old mode',was:'aspect ratio'}}
`+slice('let gpuData = null;','function renderHardware(d) {')+`
$('gpu-reload').addEventListener('click',loadGpu);
document.addEventListener('change',e=>{if(e.target.id==='gpu-only-changed'){show3dAll=!e.target.checked;renderGpu();$('gpu-only-changed')?.focus({preventScroll:true})}});
document.documentElement.dataset.boot='ready'; document.querySelector('.boot-screen')?.remove();
document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('hidden',p.dataset.panel!=='gpu'));
document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.tab==='gpu')));
(async()=>{try{
await loadGpu();await settle();
check('two monitor cards',document.querySelectorAll('.gfx-monitor').length===2);
check('actual current readouts',[...document.querySelectorAll('.gfx-readout strong')].map(e=>e.textContent).join('|')==='240 Hz|165 Hz');
check('primary display badge',document.querySelector('.gfx-monitor header').textContent.includes('Primary'));
check('three scaling illustrations',document.querySelectorAll('.gfx-scaling-guide figure').length===3);
check('each known scaling policy has a preview',document.querySelectorAll('.gfx-policy-preview').length===2);
check('no guessed native resolution',$('gpu-out').textContent.includes('native panel size is not reported'));
check('CS2 opens by default',document.querySelector('[data-gfx-group="cs2.exe"]').open);
check('CSGO collapsible',!document.querySelector('[data-gfx-group="csgo.exe"]').open);
check('raw values start hidden',[...document.querySelectorAll('.gfx-raw')].every(d=>!d.open));
const raw=document.querySelector('[data-gfx-group="cs2.exe"] .gfx-raw');raw.open=true;
check('Details reveals exact driver data',raw.textContent.includes('0x00000011')&&raw.textContent.includes('Enable Streamline override'));raw.open=false;
check('default filter removes predefined CS2 entry',!document.querySelector('[data-gfx-group="cs2.exe"]').textContent.includes('Laptop GPU routing'));
check('stored predefined global value excluded',!document.querySelector('[data-gfx-group="global"]').textContent.includes('Driver built-in entry'));
const select=document.querySelector('[data-display="Display2"]');select.value='120';select.dispatchEvent(new Event('change',{bubbles:true}));
check('picker updates its own comparison',select.closest('article').querySelector('.gfx-motion').textContent.includes('Selected 120 Hz'));
check('picker alone has no API call',calls.length===1);
document.querySelector('[data-apply-display="Display2"]').click();await settle();
const refresh=calls.filter(c=>c.route==='/api/display/refresh');
check('refresh validates then commits',refresh.length===2&&!refresh[0].body.apply&&refresh[1].body.apply&&refresh.every(c=>c.body.device==='Display2'&&c.body.refresh===120));
check('apply re-reads current state',document.querySelectorAll('.gfx-readout strong')[1].textContent==='165 Hz');
$('gpu-only-changed').click();await settle();
check('all-settings filter shows defaults',document.querySelector('[data-gfx-group="cs2.exe"]').textContent.includes('Laptop GPU routing'));
check('predefined stored global gets default badge',[...document.querySelectorAll('.gfx-setting')].find(e=>e.textContent.includes('Driver built-in entry')).querySelector('.flag').textContent==='NVIDIA default');
document.querySelector('[data-gfx-group="csgo.exe"]').open=true;await settle();$('gpu-only-changed').click();await settle();
check('filter preserves accordion state',document.querySelector('[data-gfx-group="csgo.exe"]').open);
answer.scaling.displays[1]={...answer.scaling.displays[1],scaling:5,name:'aspect ratio',fills:false,bars:true};await loadGpu();
document.querySelector('[data-fill-display]').click();await settle();
const fill=calls.filter(c=>c.route==='/api/display/fill');check('Fix validates then saves permanently',fill.length===2&&!fill[0].body.apply&&fill[1].body.apply&&fill[1].body.persist&&fill[0].body.display_id===answer.scaling.displays[1].id);
failure='administrator access denied';document.querySelector('[data-fill-display]').click();await settle();check('scaling failure retains error',messages.at(-1).error&&messages.at(-1).message.includes(failure));
failure='CS2 is running';const count=calls.filter(c=>c.route==='/api/display/refresh').length;document.querySelector('[data-apply-display]').click();await settle();
check('refresh failure never commits',calls.filter(c=>c.route==='/api/display/refresh').length===count+1&&messages.at(-1).message.includes(failure));
check('failed Apply enabled again',!document.querySelector('[data-apply-display]').disabled);failure='';
for(const mode of [0,3,7,8,255,42]){answer.scaling.displays[1]={...answer.scaling.displays[1],scaling:mode,name:'mode '+mode,fills:false};await loadGpu();check('scaling '+mode+' avoids false aspect claim',!document.querySelectorAll('.gfx-scaling-row')[1].textContent.includes('leaving side bars'))}
answer.displays.displays[0]={device:'unreadable',name:'AMD',rates:[],width:0,height:0,refresh:0};await loadGpu();
check('missing mode disables Apply',document.querySelector('[data-apply-display]').disabled&&!document.querySelector('.gfx-monitor').textContent.includes('null Hz'));
answer.displays.displays[0]={...fixture.displays.displays[0],rates:[240]};await loadGpu();check('single rate remains selectable',document.querySelector('[data-display]').options.length===1);
for(const reason of ['No NVIDIA driver found','NVIDIA driver call failed','administrator access denied']){answer.nvidia={available:false,reason};answer.scaling={available:false,reason};await loadGpu();check(reason+' keeps displays',document.querySelectorAll('.gfx-monitor').length===2&&$('gpu-out').textContent.includes(reason))}
answer={displays:{displays:[]},scaling:{available:true,displays:[]},nvidia:{available:true,apps:{},global:{settings:[]}}};await loadGpu();
check('empty states readable',$('gpu-out').textContent.includes('No displays reported')&&$('gpu-out').textContent.includes('No scaling displays')&&$('gpu-out').textContent.includes('No application profile'));
answer=structuredClone(fixture);answer.nvidia.apps['cs2.exe'].error='profile unreadable';await loadGpu();check('per-profile error retained',$('gpu-out').textContent.includes('profile unreadable'));
answer.nvidia.apps['cs2.exe'].error='';answer.nvidia.apps['cs2.exe'].settings.push(setting('<img src=x onerror=alert(1)>',false));await loadGpu();check('driver names escaped',!$('gpu-out').querySelector('img'));
readFailure=true;await loadGpu();check('whole read failure shown',$('gpu-out').textContent.includes('Could not read'));readFailure=false;answer=structuredClone(fixture);$('gpu-reload').click();await settle();check('Re-read recovers',!!document.querySelector('.gfx-monitor'));
for(const theme of ${JSON.stringify(themes)}){document.documentElement.dataset.theme=theme;await settle();check(theme+' no horizontal overflow',document.querySelector('.scroll').scrollWidth<=document.querySelector('.scroll').clientWidth);check(theme+' monitor readable',getComputedStyle(document.querySelector('.gfx-readout strong')).color!==getComputedStyle(document.querySelector('.gfx-monitor')).backgroundColor)}
document.querySelector('[data-panel="gpu"]').classList.add('hidden');check('hidden tab pauses motion',getComputedStyle(document.querySelector('.gfx-mover')).animationPlayState==='paused');document.querySelector('[data-panel="gpu"]').classList.remove('hidden');
Object.defineProperty(document,'hidden',{configurable:true,value:true});gfxPauseMotion();check('hidden app pauses motion',getComputedStyle(document.querySelector('.gfx-mover')).animationPlayState==='paused');delete document.hidden;gfxPauseMotion();
if(matchMedia('(prefers-reduced-motion: reduce)').matches)check('reduced motion static',getComputedStyle(document.querySelector('.gfx-mover')).animationName==='none');
delete document.documentElement.dataset.theme;show3dAll=true;renderGpu();document.querySelector('.scroll').scrollTop=0;
}catch(e){checks.push({error:e.stack})}document.body.insertAdjacentHTML('beforeend','<pre id="checks" hidden>'+JSON.stringify(checks)+'</pre>')})();`;
let page=html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'').replace('<head>','<head><base href="'+url.pathToFileURL(path.join(root,'cs2cfg/web/')).href+'">');
page=page.replace('</body>','<script>'+code.replaceAll('</script','<\\/script')+'</script></body>');fs.writeFileSync(path.join(work,'preview.html'),page);
const args=['--headless','--no-sandbox','--disable-gpu','--allow-file-access-from-files','--remote-debugging-port=0','--user-data-dir='+path.join(work,'chrome'),'about:blank'];
if(process.env.GRAPHICS_REDUCED)args.unshift('--force-prefers-reduced-motion');
(async()=>{
 const browser=cp.spawn(process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',args,{stdio:['ignore','ignore','pipe'],windowsHide:true});let socket;
 try{
 const endpoint=await new Promise((resolve,reject)=>{let err='';const timer=setTimeout(()=>reject(Error('Chrome startup timeout')),15000);browser.stderr.on('data',c=>{err+=c;const m=err.match(/DevTools listening on (ws:\/\/[^\s]+)/);if(m){clearTimeout(timer);resolve(m[1])}});browser.on('error',reject)});
 socket=new WebSocket(endpoint);await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});let id=0;const pending=new Map();
 socket.onmessage=e=>{const r=JSON.parse(e.data);if(r.id){const p=pending.get(r.id);pending.delete(r.id);r.error?p.reject(Error(JSON.stringify(r.error))):p.resolve(r.result)}};
 const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params,sessionId}))});
 const {targetId}=await send('Target.createTarget',{url:'about:blank'}),{sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});const command=(method,params)=>send(method,params,sessionId);
 const [width,height]=(process.env.GRAPHICS_VIEWPORT||'1440,1000').split(',').map(Number);
 await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await command('Page.enable');await command('Page.navigate',{url:url.pathToFileURL(path.join(work,'preview.html')).href});
 let results;const deadline=Date.now()+25000;while(Date.now()<deadline){const {result}=await command('Runtime.evaluate',{expression:'document.getElementById("checks")?.textContent',returnByValue:true});if(result.value){results=JSON.parse(result.value);break}await new Promise(r=>setTimeout(r,100))}
 assert(results,'browser checks timeout');await new Promise(r=>setTimeout(r,300));
 for(const [name,expression] of [['displays','document.querySelector(".scroll").scrollTop=0'],['driver','document.querySelector(".scroll").scrollTop=document.querySelector(".gfx-driver").offsetTop-30'],['daylight','document.documentElement.dataset.theme="daylight";document.querySelector(".scroll").scrollTop=document.querySelector(".gfx-scaling-guide").offsetTop-30']]){await command('Runtime.evaluate',{expression});await new Promise(r=>setTimeout(r,100));const shot=await command('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(work,name+'.png'),Buffer.from(shot.data,'base64'))}
 const failures=results.filter(r=>r.ok===false||r.error);console.log(JSON.stringify({checks:results.length,failures,artifacts:work}));assert(!failures.length&&results.length>40);
 }finally{socket?.close();browser.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});
