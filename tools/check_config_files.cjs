/* Offline fixtures: production Config files markup and handlers, no Python/server/helper. */
const fs=require('fs'),path=require('path'),os=require('os'),cp=require('child_process'),vm=require('vm'),assert=require('assert'),{pathToFileURL}=require('url');
const root=path.resolve(__dirname,'..');process.chdir(root);
const html=fs.readFileSync('cs2cfg/web/index.html','utf8').replace(/\r\n/g,'\n'),before=process.argv.includes('--before');
const work=fs.mkdtempSync(path.join(os.tmpdir(),'cs2-config-')),out=process.env.CS2CFG_TEST_PREVIEWS||path.join(root,'docs/redesign/round3/preview');
fs.mkdirSync(out,{recursive:true});
const slice=(a,b)=>{const i=html.indexOf(a),j=html.indexOf(b,i);assert(i>=0&&j>i,a);return html.slice(i,j)};
for(const s of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))new vm.Script(s[1]);
let code=`const errors=[];window.addEventListener('error',e=>errors.push(e.message));const $=id=>document.getElementById(id),esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');let prefsNow={},scannedFolder=null,treeData=null,plugData=null,keyData=null;const calls=[],notices=[],opened=[];function status(...s){notices.push(s)};let reply={},hold;async function api(route,body){calls.push({route,body});if(hold)await new Promise(r=>hold=r);if(reply instanceof Error)throw reply;return structuredClone(reply)};function openSetupWizard(s){opened.push(s)}function rememberPrefs(){}function busy(){}async function loadCfgSettings(){}window.confirm=()=>true,appAsk=async()=>true,appTell=async()=>true;`;
code+=slice('const THEMES = [','function currentTheme()');
if(!before){const asset=fs.readFileSync('cs2cfg/web/assets/config/files.js','utf8');new vm.Script(asset);code+=asset+'\n'+slice('let cfgScan = null;', 'function currentAlias()')+'function showAlias(){}\n'+slice('$("cfg-scan").addEventListener(', '$("cfg-alias").addEventListener(');}
code+=`document.documentElement.dataset.boot='ready';document.querySelector('.boot-screen')?.remove();document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('hidden',p.dataset.panel!=='settings'));document.querySelectorAll('.subpane').forEach(p=>p.classList.toggle('hidden',p.dataset.sub!=='config'));document.querySelectorAll('#settings-subtabs [data-sub]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.sub==='config')));document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.tab==='settings')));`;
const file=path.join(work,'preview.html');fs.writeFileSync(file,html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'').replace('<head>','<head><base href="'+pathToFileURL(path.join(root,'cs2cfg/web/')).href+'">').replace('</body>','<script>'+code+'</script></body>'));
const chrome=process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe';
(async()=>{const browser=cp.spawn(chrome,['--headless','--no-sandbox','--disable-gpu','--allow-file-access-from-files','--remote-debugging-port=0','--user-data-dir='+path.join(work,'chrome'),'about:blank'],{windowsHide:true,stdio:['ignore','ignore','pipe']});let socket;try{
const endpoint=await new Promise((resolve,reject)=>{let log='';browser.stderr.on('data',b=>{log+=b;const m=log.match(/DevTools listening on (ws:\/\/[^\s]+)/);if(m)resolve(m[1])});browser.on('error',reject);setTimeout(()=>reject(Error('Chrome startup')),15000).unref()});socket=new WebSocket(endpoint);await new Promise(r=>socket.onopen=r);let id=0;const pending=new Map();socket.onmessage=e=>{const r=JSON.parse(e.data),p=pending.get(r.id);if(p){pending.delete(r.id);r.error?p.reject(r.error):p.resolve(r.result)}};const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params,sessionId}))});const {targetId}=await send('Target.createTarget',{url:'about:blank'}),{sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});const cmd=(m,p)=>send(m,p,sessionId),evalJS=async expression=>{const r=await cmd('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,replMode:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value};
await cmd('Emulation.setDeviceMetricsOverride',{width:1366,height:900,deviceScaleFactor:1,mobile:false});await cmd('Page.enable');await cmd('Page.navigate',{url:pathToFileURL(file).href});for(let n=0;n<100;n++){if(await evalJS(`typeof errors!=='undefined'`))break;await new Promise(r=>setTimeout(r,50))}let checks=0;const check=async(s,label=s)=>{assert(await evalJS(s),label);checks++};
const shot=async(name,target='settings-subtabs')=>{await evalJS(`document.getAnimations().forEach(a=>{a.pause();a.currentTime=1000});document.querySelector('.scroll').scrollTop+=document.getElementById(${JSON.stringify(target)}).getBoundingClientRect().top-84`);const r=await cmd('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(out,'sec8-'+name+'.png'),Buffer.from(r.data,'base64'))};
if(before){await shot('before-config-files');console.log('Config files before captured');return;}
await check(`errors.length===0`,'fixture loads');
const ready={ok:true,root:'C:/App data/generated/account/cfg/custom',folder:'C:/App data/generated/account/cfg/custom',installed:false,state:'ready',reason:'Ready in the app. Allow config files to send them to CS2.'};
await evalJS(`reply=${JSON.stringify(ready)};await prepareConfigs({choose:true})`);
await check(`calls[0].route==='/api/configs/prepare'&&$('cfg-folder').value===configsData.root`,'startup prepares and selects an app copy');
await check(`$('configs-title').textContent==='Your configs are ready in the app'&&$('configs-state').textContent.includes('Allow config files')&&!$('configs-allow').hidden`,'permission waiting is clear');
await check(`!$('config-advanced').open&&!$('cfg-scan').checkVisibility()`,'Advanced starts closed');
await check(`document.querySelectorAll('.config-guide article').length===6&&document.querySelectorAll('.config-guide svg').length===6`,'six short file guides and icons');
await check(`$('setup-save').getClientRects().length&&$('setup-open').getClientRects().length`,'portable setup remains directly accessible');
await evalJS(`$('configs-import').click();$('configs-allow').click()`);
await check(`JSON.stringify(opened)===JSON.stringify([{step:'import'},{step:'permission'}])`,'actions enter the right wizard steps');
await shot('after-config-files');
const installed={...ready,folder:'C:/Games/CS2/game/csgo/cfg/custom',state:'installed',installed:true,reason:'Ready in CS2. Existing files were backed up before changes.'};
await evalJS(`reply=${JSON.stringify(installed)};prefsNow.cfg_write_ok=true;await prepareConfigs({choose:true})`);
await check(`$('configs-title').textContent==='Your configs are ready in CS2'&&$('configs-allow').hidden&&$('cfg-folder').value===configsData.folder`,'installed result selects CS2 copy');
await evalJS(`$('cfg-folder').value='D:/My personal configs';await prepareConfigs({choose:true})`);
await check(`$('cfg-folder').value==='D:/My personal configs'`,'explicit personal collection stays selected');
await evalJS(`reply={...configsData,installed:false,state:'waiting',reason:'Ready in the app. Close CS2, then refresh to send them.'};await prepareConfigs()`);
await check(`$('configs-state').textContent.includes('Close CS2')&&$('configs-title').textContent.includes('in the app')`,'running game is waiting, never installed');
await evalJS(`hold=true;const refresh=prepareConfigs();window.pendingRefresh=refresh`);
await check(`configsBusy&&$('config-ready').getAttribute('aria-busy')==='true'&&$('configs-refresh').disabled`,'pending refresh disables duplicate work');
await evalJS(`const n=calls.length;await prepareConfigs();window.noDuplicate=calls.length===n;const release=hold;hold=null;release();await pendingRefresh`);
await check(`window.noDuplicate&&!configsBusy&&!$('configs-refresh').disabled`,'pending requests settle');
await evalJS(`reply=new Error('<read failed>');await prepareConfigs()`);
await check(`$('configs-title').textContent==='Configs need another try'&&$('configs-state').textContent==='<read failed>'&&!$('configs-state').querySelector('read')`,'error never claims readiness and escapes content');
await evalJS(`reply=${JSON.stringify(ready)};prefsNow={};await prepareConfigs()`);
await evalJS(`$('config-advanced').querySelector('summary').focus()`);
await cmd('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',text:'\r',windowsVirtualKeyCode:13});await cmd('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
await check(`$('config-advanced').open&&$('cfg-card').getClientRects().length&&$('cfg-scan').getClientRects().length`,'keyboard opens the production studio');
for(const id of ['cfg-suggest','cfg-folder','cfg-browse','cfg-browse-file','cfg-scan','cfg-apply-polish','starter-make','cfg-rename-preview','cfg-rename-apply','cfg-behaviour'])await check(`!!$('${id}')`,'existing control retained: '+id);
const scan={files:[{relative:'custom/autoexec.vcfg',role:'entry point',order:0,polish:{safe:true,changed:false}},{relative:'custom/mainsettings/imported.vcfg',role:'settings',order:1,polish:{safe:true,changed:true,lines_touched:3}}],counts:{aliases:2,binds:8,settings:18},exec_chain:[{file:'custom/autoexec.vcfg',depth:0},{file:'custom/mainsettings/imported.vcfg',depth:1}],issues:[],overrides:[],binds:[],aliases:[]};
await evalJS(`reply=${JSON.stringify(scan)};$('cfg-scan').disabled=false;$('cfg-scan').click();await new Promise(r=>setTimeout(r,20))`);
await check(`calls.at(-1).route==='/api/cfg/scan'&&$('cfg-out').textContent.includes('Load order')&&!$('cfg-apply-polish').classList.contains('hidden')`,'existing scan handler and renderer still work');
await shot('after-advanced','config-advanced');
await evalJS(`$('cfg-apply-polish').click();await new Promise(r=>setTimeout(r,20))`);
await check(`calls.some(c=>c.route==='/api/cfg/polish'&&c.body.files[0]==='custom/mainsettings/imported.vcfg')`,'formatting remains reachable');
await evalJS(`$('config-advanced').open=false`);
const themes=await evalJS(`THEMES.map(t=>t[0])`);
for(const theme of themes){
  for(const state of [ready,installed]){
    await evalJS(`applyTheme(${JSON.stringify(theme)});configsData=${JSON.stringify(state)};renderConfigs()`);
    await check(`document.documentElement.scrollWidth<=innerWidth&&$('config-ready').scrollWidth<=$('config-ready').clientWidth`,theme+' ready layout');
    await check(`getComputedStyle($('configs-title')).color!==getComputedStyle($('config-ready')).backgroundColor`,theme+' themed foreground');
  }
}
await evalJS(`applyTheme('paper');configsData=${JSON.stringify(ready)};renderConfigs()`);await shot('after-paper');
for(const width of [820,480,360]){
  await cmd('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
  await evalJS(`configsData={...configsData,root:'C:/'+ 'long-folder/'.repeat(30)};renderConfigs();$('config-advanced').open=true`);
  await check(`document.documentElement.scrollWidth<=innerWidth&&$('config-ready').scrollWidth<=$('config-ready').clientWidth`,width+' narrow long path');
}
await cmd('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});await evalJS(`configsBusy=true;renderConfigs()`);
await check(`getComputedStyle(document.querySelector('.config-ready-top > svg')).animationName==='none'`,'reduced motion');
await cmd('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'no-preference'}]});
await evalJS(`Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'))`);
await check(`getComputedStyle(document.querySelector('.config-ready-top > svg')).animationPlayState==='paused'`,'background motion pauses');
await evalJS(`Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));document.querySelector('.subpane[data-sub="config"]').classList.add('hidden')`);
await check(`getComputedStyle(document.querySelector('.config-ready-top > svg')).animationPlayState==='paused'`,'hidden pane motion pauses');
await check(`errors.length===0`,'no runtime errors');
console.log('Config files: '+checks+' passed');
}finally{socket?.close();browser.kill();}})().catch(e=>{console.error(e);process.exitCode=1});
