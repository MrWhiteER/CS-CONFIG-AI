/* Offline Sound fixtures use production markup/renderers. No backend or helper runs. */
const fs=require('fs'),path=require('path'),os=require('os'),cp=require('child_process'),vm=require('vm'),assert=require('assert'),{pathToFileURL}=require('url');
const root=path.resolve(__dirname,'..');process.chdir(root);
const html=fs.readFileSync('cs2cfg/web/index.html','utf8').replace(/\r\n/g,'\n'),before=process.argv.includes('--before');
for(const s of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))new vm.Script(s[1]);
const work=fs.mkdtempSync(path.join(os.tmpdir(),'cs2-sound-')),out=process.env.CS2CFG_TEST_PREVIEWS||path.join(root,'docs/redesign/round3/preview');
fs.mkdirSync(out,{recursive:true});
const slice=(a,b)=>{const i=html.indexOf(a),j=html.indexOf(b,i);assert(i>=0&&j>i,a);return html.slice(i,j)};
let code=`const errors=[];window.addEventListener('error',e=>errors.push(e.message));const $=id=>document.getElementById(id),esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');let activeTab='settings',settingsSub='sound',prefsNow={},audioData=null;const notices=[];function status(...s){notices.push(s)}function applyPrefs(){};const calls=[],routeReplies={};let fixture,reply,hold;async function api(route,body){calls.push({route,body});if(hold)await new Promise(r=>hold=r);const result=routeReplies[route]||reply||fixture;if(result instanceof Error)throw result;return structuredClone(result)};`;
// The existing audio controls retain their real renderer and section 2 hardware icons.
code+=fs.readFileSync('cs2cfg/web/assets/hardware/icons.js','utf8');
code+=slice('function audioOptions(', 'async function saveAudio(');
code+=slice('const THEMES = [','function currentTheme()');
if(!before){const source=fs.readFileSync('cs2cfg/web/assets/goxlr/sound.js','utf8');new vm.Script(source);code+=source+'\n'+slice('/* Named setups.', '/* Saving a setup,');}
code+=`document.documentElement.dataset.boot='ready';document.querySelector('.boot-screen')?.remove();document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('hidden',p.dataset.panel!=='settings'));document.querySelectorAll('.subpane').forEach(p=>p.classList.toggle('hidden',p.dataset.sub!=='sound'));document.querySelectorAll('#settings-subtabs [data-sub]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.sub==='sound')));document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.tab==='settings')));audioData={output:[{id:'headphones',name:'Headphones (GoXLR)',default:true}],input:[{id:'chat',name:'Chat Mic (GoXLR)',default:true}],pinned_output:'headphones',pinned_input:'chat',enforce:true,enforcing:true};renderAudio();`;
const file=path.join(work,'preview.html');fs.writeFileSync(file,html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'').replace('<head>','<head><base href="'+pathToFileURL(path.join(root,'cs2cfg/web/')).href+'">').replace('</body>','<script>'+code+'</script></body>'));
const chrome=process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe';
(async()=>{const browser=cp.spawn(chrome,['--headless','--no-sandbox','--disable-gpu','--allow-file-access-from-files','--remote-debugging-port=0','--user-data-dir='+path.join(work,'chrome'),'about:blank'],{windowsHide:true,stdio:['ignore','ignore','pipe']});let socket;try{
const endpoint=await new Promise((resolve,reject)=>{let log='';browser.stderr.on('data',b=>{log+=b;const m=log.match(/DevTools listening on (ws:\/\/[^\s]+)/);if(m)resolve(m[1])});browser.on('error',reject);setTimeout(()=>reject(Error('Chrome startup')),15000).unref()});socket=new WebSocket(endpoint);await new Promise(r=>socket.onopen=r);let id=0;const pending=new Map();socket.onmessage=e=>{const r=JSON.parse(e.data),p=pending.get(r.id);if(p){pending.delete(r.id);r.error?p.reject(r.error):p.resolve(r.result)}};const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params,sessionId}))});const {targetId}=await send('Target.createTarget',{url:'about:blank'}),{sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});const cmd=(m,p)=>send(m,p,sessionId),evalJS=async expression=>{const r=await cmd('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,replMode:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value};
await cmd('Emulation.setDeviceMetricsOverride',{width:1366,height:900,deviceScaleFactor:1,mobile:false});await cmd('Page.enable');await cmd('Page.navigate',{url:pathToFileURL(file).href});await new Promise(r=>setTimeout(r,400));let checks=0;const check=async(s,label=s)=>{assert(await evalJS(s),label);checks++};
const shot=async name=>{await evalJS(`document.getAnimations().forEach(a=>{a.pause();a.currentTime=1000});document.querySelector('.scroll').scrollTop+=document.getElementById('settings-subtabs').getBoundingClientRect().top-84`);const r=await cmd('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(out,'sec7-'+name+'.png'),Buffer.from(r.data,'base64'))};
await check(`$('audio-output').value==='headphones'&&$('audio-input').value==='chat'`,'existing Sound renderer');
if(before){await shot('before-sound');console.log('Sound before: '+checks+' passed');return;}
const none={ok:true,backend:'none',state:'not_found',can_switch:false,profiles:[],mic_profiles:[],mixers:[],current:{device:'',mic:''},setup_names:[],bindings:{},serial:'',reason:'GoXLR not found'};
const utility={...none,backend:'utility',state:'ready',can_switch:true,serial:'SAMPLE-123',profiles:['Default','Match','Recording'],mic_profiles:['Clean','Broadcast','Quiet'],current:{device:'Default',mic:'Clean'},setup_names:['Match','Practice','Recording'],reason:'',mixers:[{serial:'SAMPLE-123',label:'SAMPLE-123'}]};
const official={...utility,backend:'official',state:'limited',can_switch:false,serial:'',mixers:[],current:{device:'',mic:''},setup_names:[],reason:'Official App profiles are read-only here. Switching needs a supported bridge.'};
const setFixture=async f=>evalJS(`fixture=${JSON.stringify(f)};reply=null;await loadGoxlr(true)`);
const settle=()=>evalJS(`new Promise(r=>setTimeout(r,10))`);
const profile=(kind,name)=>`[...document.querySelectorAll('[data-goxlr-kind="${kind}"]')].find(b=>b.dataset.goxlrName===${JSON.stringify(name)})`;
await check(`calls.length===0`,'no discovery before Sound is opened');
await setFixture(none);
await evalJS(`settingsSub='apply';const n=calls.length;document.dispatchEvent(new Event('cs2cfg:ready'));window.lazySound=calls.length===n;settingsSub='sound';document.dispatchEvent(new Event('cs2cfg:ready'))`);await settle();
await check(`window.lazySound&&calls.at(-1).route==='/api/goxlr'`,'restored Sound loads after ready, other panes skip it');
await check(`$('goxlr-out').textContent.trim()==='GoXLR not found'&&!document.querySelector('[data-goxlr-kind]')`,'calm absent state');
await check(`$('goxlr-refresh').getAttribute('aria-label')==='Refresh GoXLR'&&$('goxlr-feedback').getAttribute('aria-live')==='polite'`,'accessible status/refresh');
await shot('after-notfound');
await setFixture(official);
await check(`$('goxlr-out').textContent.includes('Official App')&&document.querySelectorAll('[data-goxlr-kind]').length===6`,'official profile listing');
await check(`[...document.querySelectorAll('[data-goxlr-kind]')].every(b=>b.disabled&&b.title.includes('supported bridge'))`,'official limits are explicit; no invented command');
await check(`!document.querySelector('[aria-pressed="true"][data-goxlr-kind]')`,'official active profile never guessed');
await shot('after-official');
await setFixture(utility);
await check(`$('goxlr-out').textContent.includes('GoXLR Utility')&&${profile('device','Default')}.getAttribute('aria-pressed')==='true'`,'active device from API');
await check(`${profile('mic','Clean')}.getAttribute('aria-pressed')==='true'`,'active mic from API');
await check(`[...document.querySelectorAll('[data-goxlr-kind]')].every(b=>!b.disabled&&b.getAttribute('aria-label')&&b.title)`,'one click controls labelled');
await check(`$('goxlr-setup').options.length===3&&$('goxlr-bind')&&$('goxlr-unbind')`,'existing Setups offered');
await shot('after-utility');
await evalJS(`reply={...fixture,current:{device:'Match',mic:'Clean'}};${profile('device','Match')}.click()`);await settle();
await check(`calls.at(-1).route==='/api/goxlr/switch'&&JSON.stringify(calls.at(-1).body)===JSON.stringify({backend:'utility',serial:'SAMPLE-123',kind:'device',profile:'Match'})`,'device switch payload');
await check(`goxlrData.current.device==='Match'&&${profile('device','Match')}.getAttribute('aria-pressed')==='true'&&!goxlrBusy`,'confirmed device switch');
await check(`document.activeElement===${profile('device','Match')}`,'focus restored on success');
await evalJS(`reply={...fixture,current:{device:'Match',mic:'Broadcast'}};${profile('mic','Broadcast')}.focus()`);
await cmd('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',text:'\r',windowsVirtualKeyCode:13});await cmd('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await settle();
await check(`calls.at(-1).body.kind==='mic'&&calls.at(-1).body.profile==='Broadcast'&&goxlrData.current.mic==='Broadcast'`,'keyboard mic switch');
await evalJS(`reply={ok:false,error:'Device disconnected; refresh to check its state.'};hold=true;${profile('device','Recording')}.click()`);
await check(`goxlrBusy&&$('goxlr-card').getAttribute('aria-busy')==='true'&&$('goxlr-refresh').disabled&&[...document.querySelectorAll('[data-goxlr-kind]')].every(b=>b.disabled)`,'pending disables duplicate work');
await check(`goxlrData.current.device==='Match'&&${profile('device','Recording')}.getAttribute('aria-pressed')==='false'`,'no optimistic success');
await evalJS(`const count=calls.length;switchGoxlr('mic','Quiet');loadGoxlr(true);window.duplicateGuard=calls.length===count;const release=hold;hold=null;release()`);await settle();
await check(`window.duplicateGuard&&!goxlrBusy&&goxlrStale&&goxlrData.current.device==='Match'`,'error rolls UI data back and marks unknown');
await check(`$('goxlr-feedback').textContent.includes('disconnected')&&[...document.querySelectorAll('[data-goxlr-kind]')].every(b=>b.disabled)&&!document.querySelector('[data-goxlr-kind][aria-pressed="true"]')`,'ambiguous hardware state requires refresh');
await evalJS(`reply=null;$('goxlr-refresh').click()`);await settle();
await check(`!goxlrStale&&${profile('device','Default')}.getAttribute('aria-pressed')==='true'`,'refresh reconciles read-back');
await evalJS(`reply=new Error('<socket failed>');await switchGoxlr('mic','Quiet')`);
await check(`$('goxlr-feedback').textContent==='<socket failed>'&&!$('goxlr-feedback').querySelector('socket')&&goxlrData.current.mic==='Clean'`,'transport error escaped, prior data retained');
await setFixture(utility);
await evalJS(`reply={ok:true,setup_names:fixture.setup_names,bindings:{Match:{backend:'utility',serial:'SAMPLE-123',profiles:{device:'Default',mic:'Clean'}}}};$('goxlr-bind').click()`);await settle();
await check(`calls.at(-1).route==='/api/goxlr/bind'&&calls.at(-1).body.setup==='Match'&&calls.at(-1).body.remove===false&&$('goxlr-setup').selectedOptions[0].textContent.includes('linked')`,'bind current profiles');
await evalJS(`reply={ok:true,setup_names:fixture.setup_names,bindings:{}};$('goxlr-unbind').click()`);await settle();
await check(`calls.at(-1).body.remove===true&&!$('goxlr-setup').selectedOptions[0].textContent.includes('linked')`,'unlink Setup');
await evalJS(`reply={ok:false,error:'Could not save link'};await bindGoxlr(false)`);
await check(`!goxlrData.bindings.Match&&$('goxlr-feedback').textContent==='Could not save link'`,'failed bind retains prior binding');
await evalJS(`reply=null;routeReplies['/api/setups/act']={ok:true,live:'Match',setups:[{name:'Match'}]};routeReplies['/api/goxlr/setup/use']={...fixture,current:{device:'Match',mic:'Quiet'}};await setupsAct({do:'use',name:'Match'})`);
await check(`calls.at(-1).route==='/api/goxlr/setup/use'&&calls.at(-1).body.setup==='Match'&&goxlrData.current.device==='Match'&&goxlrData.current.mic==='Quiet'`,'production Setup action switches bound profiles');
await evalJS(`const n=calls.filter(c=>c.route==='/api/goxlr/setup/use').length;await setupsAct({do:'save',name:'Match'});window.saveDidNotSwitch=calls.filter(c=>c.route==='/api/goxlr/setup/use').length===n`);
await check(`window.saveDidNotSwitch`,'saving never changes mixer');
await evalJS(`routeReplies['/api/setups/act']={ok:false,error:'Setup missing'};const n=calls.length;await setupsAct({do:'use',name:'Missing'});window.failedDidNotSwitch=calls.length===n+1`);
await check(`window.failedDidNotSwitch`,'failed Setup selection never switches mixer');
await evalJS(`routeReplies['/api/setups/act']={ok:true,live:'Match',setups:[{name:'Match'}]};routeReplies['/api/goxlr/setup/use']={ok:false,error:'Mixer disconnected'};setupsData={live:'',setups:[{name:'Match'}]};renderSetups();document.querySelector('[data-setup-use="Match"]').click()`);await settle();
await check(`notices.at(-1)[1]===true&&notices.at(-1)[0].includes('Mixer disconnected')`,'Setup success never hides GoXLR failure');
await evalJS(`const baseApi=api;let firstReply;api=async(route,body)=>{if(route==='/api/setups/act'&&body.name==='Slow')return await new Promise(r=>firstReply=r);return await baseApi(route,body)};const slow=setupsAct({do:'use',name:'Slow'});routeReplies['/api/setups/act']={ok:true,live:'Practice',setups:[{name:'Practice'}]};routeReplies['/api/goxlr/setup/use']={ok:true,skipped:true};await setupsAct({do:'use',name:'Practice'});firstReply({ok:true,live:'Slow',setups:[{name:'Slow'}]});await slow;api=baseApi`);
await check(`setupsData.live==='Practice'&&!calls.some(c=>c.route==='/api/goxlr/setup/use'&&c.body.setup==='Slow')`,'late Setup reply cannot switch an old profile binding');
await setFixture({...utility,mixers:[{serial:'SAMPLE-123',label:'GoXLR'},{serial:'SECOND',label:'GoXLR Mini'}],serial:'',can_switch:false,state:'disconnected',reason:'Choose a mixer.'});
await check(`$('goxlr-mixer').options.length===3&&[...document.querySelectorAll('[data-goxlr-kind]')].every(b=>b.disabled)`,'multiple devices require explicit choice');
await evalJS(`fixture={...fixture,serial:'SECOND',can_switch:true};$('goxlr-mixer').value='SECOND';$('goxlr-mixer').dispatchEvent(new Event('change',{bubbles:true}))`);await settle();
await check(`calls.at(-1).route==='/api/goxlr'&&calls.at(-1).body.serial==='SECOND'`,'chosen mixer forwarded');
await setFixture({...utility,can_switch:false,state:'disconnected',serial:'',mixers:[],reason:'Connect your GoXLR.'});
await check(`[...document.querySelectorAll('[data-goxlr-kind]')].every(b=>b.disabled)&&document.querySelector('.goxlr-help').title==='Connect your GoXLR.'`,'daemon without hardware');
await setFixture({...utility,profiles:[],mic_profiles:[]});
await check(`$('goxlr-out').textContent.includes('No saved profiles')`,'empty profile folders');
await setFixture({...utility,profiles:['<unsafe "profile">', 'A'.repeat(200)]});
await check(`!$('goxlr-out').querySelector('unsafe')&&$('goxlr-out').textContent.includes('<unsafe "profile">')`,'profile names escaped');
const themes=await evalJS(`THEMES.map(t=>t[0])`);
for(const theme of themes){
  for(const [label,state] of [['utility',utility],['official',official],['notfound',none]]){
    await setFixture(state);await evalJS(`applyTheme(${JSON.stringify(theme)});document.activeElement.blur()`);
    await check(`document.documentElement.scrollWidth<=innerWidth&&$('goxlr-card').getBoundingClientRect().width>200`,theme+' '+label+' layout');
    await check(`getComputedStyle($('goxlr-card')).color!==getComputedStyle($('goxlr-card')).backgroundColor`,theme+' '+label+' themed foreground');
  }
}
await setFixture(utility);await evalJS(`applyTheme('paper')`);await shot('after-paper');
for(const width of [820,480,360]){
  await cmd('Emulation.setDeviceMetricsOverride',{width,height:1100,deviceScaleFactor:1,mobile:false});
  await setFixture({...utility,profiles:['A'.repeat(200)]});
  await check(`document.documentElement.scrollWidth<=innerWidth&&$('goxlr-card').scrollWidth<=$('goxlr-card').clientWidth`,width+' narrow long names');
  await check(`getComputedStyle(document.querySelector('.subpane[data-sub="sound"]')).gridTemplateColumns.split(' ').length===1`,width+' stacked Sound cards');
}
await cmd('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
await evalJS(`goxlrBusy=true;renderGoxlr()`);
await check(`getComputedStyle($('goxlr-refresh').querySelector('svg')).animationName==='none'`,'reduced motion');
await cmd('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'no-preference'}]});
await evalJS(`Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'))`);
await check(`getComputedStyle($('goxlr-refresh').querySelector('svg')).animationPlayState==='paused'`,'background pause');
await evalJS(`Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));document.querySelector('.subpane[data-sub="sound"]').classList.add('hidden')`);
await check(`getComputedStyle($('goxlr-refresh').querySelector('svg')).animationPlayState==='paused'`,'hidden pane pause');
await check(`errors.length===0`,'no browser runtime errors');
console.log('Sound browser checks: '+checks+' passed; '+themes.length+' themes; screenshots: '+out);
}finally{socket?.close();browser.kill()}})().catch(e=>{console.error(e);process.exitCode=1});



