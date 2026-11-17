import os from 'node:os';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
const repo=path.resolve(here,'../../../..'),out=here;
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp','.woff2':'font/woff2'};
const server=http.createServer(async(req,res)=>{try{const u=new URL(req.url,'http://localhost');if(u.pathname.startsWith('/api/')){res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({ok:false,error:'Static design preview: desktop API disabled'}));return;}const p=path.resolve(repo,'.'+decodeURIComponent(u.pathname));if(!p.startsWith(repo+path.sep))throw Error('outside workspace');const body=await fs.readFile(p);res.writeHead(200,{'Content-Type':types[path.extname(p)]||'application/octet-stream'});res.end(body);}catch{res.writeHead(404);res.end('Not found');}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;
if(process.argv.includes('--serve')){console.log(`Preview server: http://127.0.0.1:${port}/cs2cfg/web/index.html`);}else{
const profile=await fs.mkdtemp(path.join(os.tmpdir(),'cs2cfg-rail-edge-')); 
const browser=spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',['--headless=new','--no-sandbox','--disable-gpu','--in-process-gpu','--disable-software-rasterizer','--no-first-run','--no-default-browser-check','--disable-extensions','--disable-background-networking','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{windowsHide:true,stdio:['ignore','ignore','pipe']});
let stderr='';browser.stderr.on('data',d=>{stderr+=d.toString();});browser.on('error',e=>console.error('Browser launch:',e));
try{
 let debugPort;for(let i=0;i<100;i++){try{debugPort=(await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break;}catch{await new Promise(r=>setTimeout(r,100));}}
 if(!debugPort)throw Error('Edge did not create DevToolsActivePort. '+stderr);
 const targets=await(await fetch(`http://127.0.0.1:${debugPort}/json/list`,{signal:AbortSignal.timeout(5000)})).json();const ws=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
 let id=0;const pending=new Map();const errors=[];ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text+' '+(m.params.exceptionDetails.exception?.description||''));};
 const call=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});ws.send(JSON.stringify({id:n,method,params}));});
 const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value;};
 await call('Page.enable');await call('Runtime.enable');await call('Emulation.setFocusEmulationEnabled',{enabled:true});
 const viewport=width=>call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});await viewport(1440);
 const navigate=async()=>{await evaluate('document.documentElement.dataset.railRenderOld="true"');await call('Page.navigate',{url:`http://127.0.0.1:${port}/cs2cfg/web/index.html`});for(let i=0;i<100;i++){if(await evaluate('!!document.querySelector("#profile-rail .pd-more") && !document.documentElement.dataset.railRenderOld'))return;await new Promise(r=>setTimeout(r,100));}throw Error('Rail init timeout '+errors.join('\n'));};

const shots=[], checks=[];
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const check=async(name,expression)=>{const value=await evaluate(expression);assert.equal(value,true,name+': '+JSON.stringify(value)+' JS errors:'+JSON.stringify(errors)+' '+JSON.stringify(await evaluate("({focus:document.activeElement.outerHTML.slice(0,180),intent,hidden:$('profile-shelf').hidden,errors:typeof railTest==='undefined'?null:railTest.calls})")));checks.push(name);};
const screenshot=async name=>{await evaluate("[...document.querySelectorAll('#profile-rail *')].flatMap(e=>e.getAnimations()).forEach(a=>a.finish())");const b=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});const bytes=Buffer.from(b.data,'base64');await fs.writeFile(path.join(out,name),bytes);shots.push({file:name,width:bytes.readUInt32BE(16),height:bytes.readUInt32BE(20),bytes:bytes.length});};
await navigate();await wait(700);
await evaluate("document.querySelector('.boot-screen')?.remove();intent='competitive';paintIntent(intent)");
await wait(20);
await check('three direct radios',"document.querySelectorAll('.pd-direct [role=radio]').length===3");
await check('initial unknown is honest',"document.querySelector('#profile-rail').dataset.verify==='unknown'");
await evaluate("document.querySelector('.pd-direct [aria-checked=true]').focus();document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'End',bubbles:true}))");
await check('End focuses without selecting',"document.activeElement.dataset.pick==='quality' && intent==='competitive'");
await evaluate("document.querySelector('.pd-more').click()");
await check('shelf focuses selected radio',"!document.querySelector('#profile-shelf').hidden && document.activeElement.dataset.pick===intent && document.querySelector('.pd-more').getAttribute('aria-expanded')==='true'");
await evaluate("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))");
await check('Escape restores trigger',"document.querySelector('#profile-shelf').hidden && document.activeElement===document.querySelector('.pd-more')");
await evaluate("document.querySelector('.pd-more').click();document.querySelector('[data-tab=launcher]').focus()");
await check('Tab out dismisses shelf',"document.querySelector('#profile-shelf').hidden");
await evaluate("document.querySelector('.pd-more').click();document.body.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}))");
await check('outside dismisses shelf',"document.querySelector('#profile-shelf').hidden");
// Delayed hover uses real events, without changing verification.
await evaluate("document.activeElement.blur();document.querySelector('#profile-rail').dispatchEvent(new PointerEvent('pointerenter'))");
await check('hover does not open immediately',"document.querySelector('#profile-caption').hidden");await wait(170);
await check('hover opens after delay',"!document.querySelector('#profile-caption').hidden");
await evaluate("document.querySelector('#profile-rail').dispatchEvent(new PointerEvent('pointerleave'))");
await check('hover leaves cleanly',"document.querySelector('#profile-caption').hidden");
// Isolated read-only fixtures exercise plan races and Apply lifetime. No desktop API is reachable.
await evaluate(`window.railTest={api,presetBegin,calls:[],begins:0};
api=async(url,body)=>{railTest.calls.push([url,body]);if(url==='/api/plan')return {intent:body.intent,settings:[],changed_count:0};return railTest.api(url,body);};
presetBegin=()=>{railTest.begins++};
document.querySelector('[data-panel=launcher]').classList.add('hidden');
document.querySelector('.pd-direct [data-pick=balanced]').click();`);
await wait(100);
await check('off Home safe selection and plan',"intent==='balanced' && railTest.begins===0 && railTest.calls.some(([u,b])=>u==='/api/plan'&&b.intent==='balanced') && planned.intent==='balanced' && !$('apply').disabled && pendingChanges.length===1");
await evaluate("pendingChanges[0].revert()");await wait(100);
await check('undo refreshes background plan',"intent==='competitive' && planned.intent==='competitive' && railTest.begins===0");
await evaluate("document.querySelector('[data-panel=launcher]').classList.remove('hidden');document.querySelector('.pd-direct [data-pick=quality]').click()");await wait(100);
await check('Home preserves preset path',"intent==='quality' && railTest.begins===1 && planned.intent==='quality'");
// Native button keyboard activation, including Space's key-up click.
for(const [key,code,vk,name] of [['Enter','Enter',13,'balanced'],[' ','Space',32,'quality']]){
 await evaluate(`document.querySelector('.pd-direct [data-pick=${name}]').focus()`);
 await call('Input.dispatchKeyEvent',{type:'keyDown',key,code,text:key==='Enter'?'\r':' ',windowsVirtualKeyCode:vk});
 await call('Input.dispatchKeyEvent',{type:'keyUp',key,code,windowsVirtualKeyCode:vk});await wait(50);
 await check('native '+code+' selects',`intent==='${name}' && planned.intent==='${name}'`);
}
await evaluate("document.querySelector('.pd-more').click()");
await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
await check('native Tab dismisses shelf',"$('profile-shelf').hidden");
// Verification changes update status without rebuilding focused controls.
for(const state of ['verified','changed','failed']){
 await evaluate(`$('verification').hidden=false;$('verification').dataset.state='${state}';document.querySelector('.pd-more').focus()`);await wait(20);
 await check('verification '+state,`$('profile-rail').dataset.verify==='${state}' && document.activeElement===document.querySelector('.pd-more')`);
}
await evaluate(`$('verification').hidden=true;window.confirm=()=>true;
api=async(url,body)=>{if(url==='/api/apply')return new Promise((resolve,reject)=>railTest.reject=reject);return railTest.api(url,body)};
$('apply').click();`);
await check('Apply busy is actual request lifetime',"$('profile-rail').dataset.verify==='applying' && [...document.querySelectorAll('#profile-rail [data-pick]')].every(b=>b.disabled)");
await evaluate("railTest.reject(Error('Controlled offline failure'))");await wait(50);
await check('Apply failure clears busy',"!profileApplyBusy && $('profile-rail').getAttribute('aria-busy')==='false' && [...document.querySelectorAll('#profile-rail [data-pick]')].every(b=>!b.disabled)");
await evaluate(`api=async(url,body)=>url==='/api/apply'?{steps:[],skipped:[],verification:null}:railTest.api(url,body);$('apply').click()`);await wait(50);
await check('Apply success clears busy without inventing verification',"!profileApplyBusy && $('profile-rail').dataset.verify==='unknown'");
await call('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});await call('Page.captureScreenshot',{format:'png'});await wait(80);
await evaluate("document.querySelector('.pd-more').click()");
await check('reduced motion is plain fades',"[...document.querySelectorAll('#profile-rail *')].flatMap(e=>e.getAnimations()).every(a=>a.effect.getTiming().duration<=80 && a.effect.getKeyframes().every(k=>!('transform' in k)))");
await call('Emulation.setEmulatedMedia',{features:[]});
await evaluate("document.querySelector('.pd-more').click();$('profile-rail').hidden=true");await wait(60);
await check('hidden control cancels motion',"[...document.querySelectorAll('#profile-rail *')].flatMap(e=>e.getAnimations()).length===0 && $('profile-shelf').hidden");
await evaluate("$('profile-rail').hidden=false");
await viewport(860);await wait(60);await evaluate("document.querySelector('.pd-more').click()");
await check('860 rail and shelf fit without chip collision',`(()=>{const r=$('profile-rail').getBoundingClientRect(),s=$('profile-shelf').getBoundingClientRect(),ram=$('chip-ram').getBoundingClientRect(),sync=$('sync-control').getBoundingClientRect();return r.width>150&&s.left>=0&&s.right<=innerWidth&&ram.right<r.left&&r.right<sync.left})()`);
await evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'))");
await check('hidden window cancels all rail motion',"$('profile-shelf').hidden && [...document.querySelectorAll('#profile-rail *')].flatMap(e=>e.getAnimations()).length===0");
await evaluate("delete document.hidden;document.dispatchEvent(new Event('visibilitychange'))");
// Restore the untouched real page for captures: no sample receipts, readings or simulated state.
await viewport(1440);await navigate();await wait(500);await evaluate("document.querySelector('.boot-screen')?.remove()");
const themes=await evaluate('THEMES.map(t=>t[0])');const contrast=[];
for(const theme of themes){
 await evaluate(`applyTheme('${theme}');document.querySelector('.pd-more').click()`);await wait(280);await evaluate("[...document.querySelectorAll('#profile-rail *')].flatMap(e=>e.getAnimations()).forEach(a=>a.finish())");
 const result=await evaluate(`(()=>{const root=$('profile-rail'),pop=$('profile-shelf');
 const rgb=s=>s.match(/[\\d.]+/g).map(Number);
 const lum=c=>c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
 const ratio=(a,b)=>{a=rgb(a);b=rgb(b);a=lum(a.slice(0,3).map((v,i)=>v*(a[3]??1)+b[i]*(1-(a[3]??1))));b=lum(b.slice(0,3));return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
 const bg=getComputedStyle(pop).backgroundColor;
 return {theme:'${theme}',ink:ratio(getComputedStyle(pop.querySelector('b')).color,bg),muted:ratio(getComputedStyle(pop.querySelector('small')).color,bg),rect:pop.getBoundingClientRect().width};})()`);
 contrast.push(result);assert.ok(result.ink>=4.5&&result.muted>=4.5,JSON.stringify(result));
 await screenshot(`theme-${theme}.png`);
 await evaluate("document.querySelector('.pd-more').click();document.activeElement.blur()");
}
for(const theme of ['dark','daylight']){
 await evaluate(`applyTheme('${theme==='dark'?'violet':theme}');document.activeElement.blur()`);await wait(120);
 await screenshot(`profile-rail-idle-${theme}.png`);
 await evaluate("document.querySelector('#profile-rail').dispatchEvent(new PointerEvent('pointerenter'))");await wait(260);
 await screenshot(`profile-rail-hover-${theme}.png`);
 await evaluate("document.querySelector('.pd-more').click()");await wait(300);
 await screenshot(`profile-rail-shelf-${theme}.png`);
 await evaluate("document.querySelector('.pd-more').click();document.activeElement.blur();document.querySelector('#profile-rail').dispatchEvent(new PointerEvent('pointerleave'))");
}
await fs.writeFile(path.join(out,'render-report.json'),JSON.stringify({renderer:'Edge headless / CDP; real index.html; desktop API disabled; no screenshot state fixtures',shots,checks,contrast,errors},null,2));
assert.deepEqual(errors,[]);console.log(JSON.stringify({shots:shots.length,checks:checks.length,contrast,errors},null,2));

 await call('Browser.close').catch(()=>{});ws.close();
}finally{browser.kill();server.close();await new Promise(r=>setTimeout(r,750));if(path.dirname(profile)!==os.tmpdir()||!path.basename(profile).startsWith('cs2cfg-rail-edge-'))throw Error('Unexpected browser profile path');await fs.rm(profile,{recursive:true,force:true,maxRetries:5,retryDelay:200}).catch(e=>console.error('Temporary profile cleanup:',e.message));}
}
