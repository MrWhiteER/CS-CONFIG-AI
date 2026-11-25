/* Offline Apps checks: real markup/renderers, stubbed API and process launches. */
const fs=require('fs'),path=require('path'),os=require('os'),cp=require('child_process'),vm=require('vm'),assert=require('assert'),{pathToFileURL}=require('url');
const root=path.resolve(__dirname,'..');process.chdir(root);
const html=fs.readFileSync('cs2cfg/web/index.html','utf8'),before=process.argv.includes('--before');
for(const s of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))new vm.Script(s[1]);
const work=fs.mkdtempSync(path.join(os.tmpdir(),'cs2-apps-')),out=process.env.CS2CFG_TEST_PREVIEWS||path.join(root,'docs/redesign/round3/preview');
fs.mkdirSync(out,{recursive:true});
const slice=(a,b)=>html.slice(html.indexOf(a),html.indexOf(b,html.indexOf(a)));
// Use the production theme list and switcher so newly added themes are checked too.
let code=`const $=id=>document.getElementById(id),esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');let activeTab='settings',settingsSub='apps',prefsNow={};const calls=[];function status(){}function startCrosshairWatch(){};async function api(route,body){calls.push({route,body});if(route==='/api/apps')return {ok:true,apps:{discord:{installed:true,running:true,with_game:false},teamspeak:{installed:false,running:false,with_game:false}},teamspeak:{host:'',port:9987,nickname:'',enabled:false}};if(route==='/api/faceit/apps')return {ok:true,apps:{'faceit-client':{installed:true,running:false},'faceit-ac':{installed:true,running:false}}};if(route==='/api/match/settings')return {ok:true,enabled:true};if(route==='/api/crosshairx')return {ok:true,installed:true,running:false};return {ok:true};}`;
if(!before)code+=slice('/* Crosshair X.','/* Inventory watches')+'\n'+fs.readFileSync('cs2cfg/web/assets/apps/apps.js','utf8')+'\n'+slice('function sayCrosshair(outcome)', '/* Named setups.');
code+=slice('const THEMES = [','function currentTheme()');
code+=`
function logoLuminance(color) {
  const rgb=color.match(/[\\d.]+/g).slice(0,3).map(v=>{v=Number(v)/255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});
  return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
}
function lightAppsTheme() {
  const probe=document.createElement('span');probe.style.color='var(--bg)';document.body.append(probe);
  const light=logoLuminance(getComputedStyle(probe).color)>.5;probe.remove();return light;
}
function visibleAppLogos(selector) {
  return [...document.querySelectorAll(selector+' img')].filter(i=>i.getClientRects().length&&getComputedStyle(i).visibility==='visible'&&Number(getComputedStyle(i).opacity)>0);
}
function teamSpeakLogoCorrect(selector) {
  const logos=visibleAppLogos(selector),expected=lightAppsTheme()?'teamspeak-logo-dark.svg':'teamspeak-logo.svg';
  return logos.length===1&&logos[0].getAttribute('src')==='assets/apps/'+expected&&logos[0].complete&&logos[0].naturalWidth>0;
}
function crosshairPlateCorrect(selector) {
  const logos=visibleAppLogos(selector);if(logos.length!==1)return false;
  const logo=logos[0],plate=logo.parentElement,style=getComputedStyle(plate),image=getComputedStyle(logo);
  if(logo.getAttribute('src')!=='assets/apps/crosshairx-logo.png'||!logo.complete||!logo.naturalWidth||image.filter!=='none'||image.objectFit!=='contain')return false;
  if(!lightAppsTheme())return style.display==='contents'&&style.backgroundColor==='rgba(0, 0, 0, 0)';
  const rgb=style.backgroundColor.match(/[\\d.]+/g).map(Number),outer=plate.getBoundingClientRect(),inner=logo.getBoundingClientRect();
  return style.display==='flex'&&(rgb.length===3||rgb[3]===1)&&1.05/(logoLuminance(style.backgroundColor)+.05)>=7&&parseFloat(style.borderRadius)>=6&&
    inner.left-outer.left>=11.99&&outer.right-inner.right>=11.99&&inner.top-outer.top>=7.99&&outer.bottom-inner.bottom>=7.99;
}
`;
code+=`document.documentElement.dataset.boot='ready';document.querySelector('.boot-screen')?.remove();document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('hidden',p.dataset.panel!=='settings'));document.querySelectorAll('.subpane').forEach(p=>p.classList.toggle('hidden',p.dataset.sub!=='apps'));document.querySelectorAll('#settings-subtabs [data-sub]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.sub==='apps')));document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.tab==='settings')));`;
if(before)code+=`$('companions-out').innerHTML='<p class="sub">Nothing added yet.</p><button class="btn">Add a companion…</button>';`;
else code+=`loadAppTiles();loadCrosshairX();renderCompanions();`;
const file=path.join(work,'preview.html');
const freezeMotion='<style>*, *::before, *::after { transition: none !important; animation: none !important }</style>';
fs.writeFileSync(file,html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'').replace('<head>','<head><base href="'+pathToFileURL(path.join(root,'cs2cfg/web/')).href+'">'+freezeMotion).replace('</body>',()=>'<script>'+code+'</script></body>'));
const chrome=process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe';
(async()=>{const browser=cp.spawn(chrome,['--headless','--no-sandbox','--disable-gpu','--allow-file-access-from-files','--remote-debugging-port=0','--user-data-dir='+path.join(work,'chrome'),'about:blank'],{windowsHide:true,stdio:['ignore','ignore','pipe']});let socket;try{
const endpoint=await new Promise((resolve,reject)=>{let log='';browser.stderr.on('data',b=>{log+=b;const m=log.match(/DevTools listening on (ws:\/\/[^\s]+)/);if(m)resolve(m[1])});browser.on('error',reject);setTimeout(()=>reject(Error('Chrome startup')),15000).unref()});socket=new WebSocket(endpoint);await new Promise(r=>socket.onopen=r);let id=0;const pending=new Map();socket.onmessage=e=>{const r=JSON.parse(e.data),p=pending.get(r.id);if(p){pending.delete(r.id);r.error?p.reject(r.error):p.resolve(r.result)}};const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params,sessionId}))});const {targetId}=await send('Target.createTarget',{url:'about:blank'}),{sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});const cmd=(m,p)=>send(m,p,sessionId),evalJS=async expression=>{const r=await cmd('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value};
await cmd('Emulation.setDeviceMetricsOverride',{width:1366,height:768,deviceScaleFactor:1,mobile:false});await cmd('Page.enable');await cmd('Page.navigate',{url:pathToFileURL(file).href});await new Promise(r=>setTimeout(r,700));let checks=0;const check=async(s,label=s)=>{assert(await evalJS(s),label);checks++};const shot=async(name,prefix='sec6')=>{if(!before)await evalJS(`document.querySelector('.scroll').scrollTop+=document.getElementById('settings-subtabs').getBoundingClientRect().top-90`);await new Promise(r=>setTimeout(r,100));const r=await cmd('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(out,prefix+'-'+name+'.png'),Buffer.from(r.data,'base64'))};
await shot(before?'before-apps':'after-apps');if(!before){await check(`document.querySelectorAll('[data-app-tile]').length===4`);for(const app of ['faceit','discord','teamspeak','crosshairx']){await evalJS(`document.querySelector('[data-app-tile="${app}"]').click()`);await check(`!$('app-detail').hidden && $('app-detail-title').textContent.includes('${app==='crosshairx'?'Crosshair X':app==='faceit'?'FACEIT':app==='teamspeak'?'TeamSpeak':'Discord'}')`);await shot('after-'+app);await evalJS(`$('app-back').click()`)}
const themes=await evalJS(`THEMES.map(t=>t[0])`),lightThemes=[];
for(const theme of themes){
  await evalJS(`applyTheme(${JSON.stringify(theme)});document.activeElement.blur()`);
  const light=await evalJS(`lightAppsTheme()`);if(light)lightThemes.push(theme);
  await check(`document.documentElement.scrollWidth<=innerWidth && [...document.querySelectorAll('[data-app-tile]')].every(e=>e.getBoundingClientRect().width>100)`,theme+': tile layout');
  await check(`(getComputedStyle(document.documentElement).colorScheme==='light')===lightAppsTheme()`,theme+': background and color scheme agree');
  await check(`teamSpeakLogoCorrect('[data-app-tile="teamspeak"]')`,theme+': visible official TeamSpeak variant');
  await check(`crosshairPlateCorrect('[data-app-tile="crosshairx"]')`,theme+': Crosshair X plate, 7:1 white contrast and clear space');
  await check(`[...document.querySelectorAll('.app-tile img')].every(i=>getComputedStyle(i).filter==='none'&&getComputedStyle(i).objectFit==='contain'&&getComputedStyle(i).width==='112px'&&getComputedStyle(i).height==='80px')`,theme+': logo presentation unchanged');
  await check(`[...document.querySelectorAll('.app-tile b')].every(e=>e.getBoundingClientRect().top===document.querySelector('[data-app-tile="discord"] b').getBoundingClientRect().top)`,theme+': logo plates preserve title alignment');
  if(['paper','daylight','violet'].includes(theme))await shot('after-'+theme,'sec6b');
}
// Keep each detail header mounted while switching every theme, including light -> dark.
for(const app of ['teamspeak','crosshairx']){
  await evalJS(`document.querySelector('[data-app-tile="${app}"]').click()`);
  for(const theme of themes){
    await evalJS(`applyTheme(${JSON.stringify(theme)})`);
    await check(`${app==='teamspeak'?'teamSpeakLogoCorrect':'crosshairPlateCorrect'}('#app-detail-brand')`,theme+': '+app+' detail follows live theme changes');
  }
  await evalJS(`$('app-back').click()`);
}
console.log('Apps themes: '+themes.length+' checked; light backgrounds: '+lightThemes.join(', '));
await evalJS(`applyTheme('paper');document.activeElement.blur()`);await shot('after-paper');await cmd('Emulation.setDeviceMetricsOverride',{width:820,height:1000,deviceScaleFactor:1,mobile:false});await check(`document.documentElement.scrollWidth<=innerWidth`);await check(`teamSpeakLogoCorrect('[data-app-tile="teamspeak"]')&&crosshairPlateCorrect('[data-app-tile="crosshairx"]')`);await shot('after-narrow');await evalJS(`document.querySelector('[data-app-tile="teamspeak"]').click();$('app-ts-host').value='voice.example.com';$('app-ts-nickname').value='Player & One';$('app-ts-save').click()`);await check(`calls.some(c=>c.route==='/api/apps/set'&&c.body.server.host==='voice.example.com'&&c.body.server.nickname==='Player & One')`);
await evalJS(`$('app-back').click();document.querySelector('[data-app-tile="discord"]').click();document.querySelector('[data-app-launch="discord"]').click()`);await check(`calls.some(c=>c.route==='/api/apps/launch'&&c.body.app==='discord')`);await evalJS(`document.querySelector('[data-app-with="discord"]').click()`);await check(`calls.some(c=>c.route==='/api/apps/set'&&c.body.app==='discord'&&c.body.with_game===true)`);
await evalJS(`$('app-back').click();document.querySelector('[data-app-tile="faceit"]').click();document.querySelector('[data-app-launch="faceit-ac"]').click()`);await check(`calls.some(c=>c.route==='/api/faceit/apps/launch'&&c.body.app==='faceit-ac')`);
await evalJS(`document.querySelector('[data-app-with="faceit-client"]').click();$('app-alert-sound').click()`);await check(`calls.some(c=>c.route==='/api/faceit/apps/set'&&c.body.app==='faceit-client'&&c.body.with_game===true)`);await check(`calls.some(c=>c.route==='/api/match/settings'&&c.body.sound===false&&c.body.enabled===true)`);
await evalJS(`document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))`);await check(`$('app-detail').hidden&&document.activeElement.dataset.appTile==='faceit'`);
await evalJS(`document.querySelector('[data-app-tile="crosshairx"]').click();$('xhair-open').click();document.querySelector('[data-app-launch="gamebar"]').click();$('xhair-launch').click()`);await check(`calls.some(c=>c.route==='/api/crosshairx/start')`);await check(`calls.some(c=>c.route==='/api/apps/launch'&&c.body.app==='gamebar')`);await check(`calls.some(c=>c.route==='/api/prefs'&&c.body.crosshairx_launch===true)`);
await evalJS(`$('app-back').click();document.querySelector('[data-app-tile="teamspeak"]').click();$('app-ts-host').value='unsaved.example.com';loadAppTiles()`);await check(`$('app-ts-host').value==='unsaved.example.com'`);
await check(`[...document.querySelectorAll('.app-tile img')].every(i=>i.complete&&i.naturalWidth>0)`);await check(`parseFloat(getComputedStyle(document.querySelector('.app-tile')).borderTopWidth)>0`);
await evalJS(`document.querySelector('[data-panel="settings"]').classList.add('hidden');pauseAppsMotion()`);await check(`document.documentElement.classList.contains('apps-paused')`);await evalJS(`document.querySelector('[data-panel="settings"]').classList.remove('hidden');pauseAppsMotion()`);await check(`!document.documentElement.classList.contains('apps-paused')`);
await check(`[...document.querySelectorAll('.app-tile img')].every(i=>getComputedStyle(i).animationName==='none'&&getComputedStyle(i).transform==='none'&&getComputedStyle(i).filter==='none')`);
await evalJS(`$('app-back').click();companionsData=[{id:'recorder',name:'Recorder',installed:true,with_game:true},{id:'discord',name:'Discord',integration:'discord'}];renderCompanions()`);await check(`$('companions-add')&&document.querySelector('[data-companion-start="recorder"]')&&!document.querySelector('[data-companion-start="discord"]')`);
await evalJS(`document.querySelector('[data-app-tile="discord"]').click();const realApi=api;api=async()=>({ok:false,error:'Offline'});document.querySelector('[data-app-with="discord"]').click();new Promise(r=>setTimeout(r,30))`);await check(`document.querySelector('[data-app-with="discord"]').checked===false&&$('app-feedback').textContent==='Offline'`);
await evalJS(`api=async()=>{throw Error('Offline')};loadAppTiles()`);await check(`document.querySelector('[data-app-status="discord"]').textContent==='Status unavailable'`);await evalJS(`api=realApi`);
await cmd('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});await check(`getComputedStyle(document.querySelector('.app-tile'),'::before').animationName==='none'`);await evalJS(`Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'))`);await check(`document.documentElement.classList.contains('apps-paused')`);
}console.log('Apps browser checks: '+checks+' passed; screenshots: '+out);
}finally{socket?.close();browser.kill()}})().catch(e=>{console.error(e);process.exitCode=1});
