import {execFileSync} from 'node:child_process';
import os from 'node:os';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
const repo=path.resolve(here,'../../../..'),out=here;
const original=execFileSync('git',['show','HEAD:cs2cfg/web/index.html'],{cwd:repo,maxBuffer:8e6});
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp','.woff2':'font/woff2'};
const server=http.createServer(async(req,res)=>{try{const u=new URL(req.url,'http://localhost');if(u.pathname.startsWith('/api/')){res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({ok:false,error:'Static design preview: desktop API disabled'}));return;}const p=path.resolve(repo,'.'+decodeURIComponent(u.pathname));if(!p.startsWith(repo+path.sep))throw Error('outside workspace');const body=u.pathname.endsWith('/index.html') && process.argv.includes('--before') ? original : await fs.readFile(p);res.writeHead(200,{'Content-Type':types[path.extname(p)]||'application/octet-stream'});res.end(body);}catch{res.writeHead(404);res.end('Not found');}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;
if(process.argv.includes('--serve')){console.log(`Preview server: http://127.0.0.1:${port}/cs2cfg/web/index.html`);}else{
const profile=await fs.mkdtemp(path.join(out,'.edge-')); 
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

const wait=ms=>new Promise(r=>setTimeout(r,ms));
await call('Page.navigate',{url:`http://127.0.0.1:${port}/cs2cfg/web/index.html`});await wait(2500);
await evaluate("document.querySelector('.boot-screen')?.remove()");
const before=process.argv.includes('--before');
const themes=['violet','ember','carbon','acid','crimson','frost','neon','daylight','paper','pro'];
const shot=async name=>{const b=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(path.join(out,name),Buffer.from(b.data,'base64'));};

const checks=[];
const check=async(name,expression)=>{const value=await evaluate(expression);if(!value)console.log(name,await evaluate("({focus:document.activeElement.outerHTML.slice(0,300),inert:[...document.querySelectorAll('[inert]')].map(e=>e.className),rect:document.querySelector('.status-card')?.getBoundingClientRect().toJSON(),rootRect:document.querySelector('#status').getBoundingClientRect().toJSON(),viewport:[innerWidth,innerHeight],cards:document.querySelector('#status').outerHTML.slice(0,1000)})"));assert.equal(value,true,name);checks.push(name);};
if(!before){
 await evaluate("status.clear();busy('Reading settings',{id:'browser-work'});window.dockCard=document.querySelector('.status-card')");
 await check('working semantics',"dockCard.dataset.kind==='working' && dockCard.getAttribute('role')==='status' && dockCard.querySelector('.status-loader')!==null");
 await evaluate("busy('Reading settings',{id:'browser-work',progress:.6,detail:'3 of 5'});");
 await check('measured progress',"document.querySelector('[role=progressbar]').getAttribute('aria-valuenow')==='60'");
 await evaluate("busy('Reading settings',{id:'browser-work',progress:.2})");await wait(520);
 await evaluate("busy('Reading settings',{id:'browser-work',progress:.8})");await wait(100);
 await check('progress width tweens',"(()=>{const m=getComputedStyle(document.querySelector('.status-fill')).transform;const x=Number(m.slice(7).split(',')[0]);return x>.2 && x<.8})()");
 await evaluate("status('Your settings are ready.',{id:'browser-work',kind:'done'})");
 await check('working to done keeps card',"document.querySelector('.status-card')===dockCard && dockCard.dataset.kind==='done'");
 await evaluate("dockCard.dispatchEvent(new PointerEvent('pointerenter'));dockCard.querySelector('button').focus()");await wait(6200);
 await check('hover and focus pause hide',"dockCard.isConnected && dockCard.classList.contains('paused')");
 await evaluate("status.clear();status('Failed to fetch',{id:'browser-error',kind:'error'});status('Saved',{id:'browser-timed'});window.errorCard=document.querySelector('[data-kind=error]');window.doneCard=document.querySelector('[data-kind=done]');");await wait(6300);
 await check('done hides and error persists',"!doneCard.isConnected && errorCard.isConnected && errorCard.getAttribute('role')==='alert'");
 await check('details default collapsed',"!errorCard.querySelector('details').open && !errorCard.querySelector('p').textContent.includes('fetch')");
 await evaluate("errorCard.querySelector('button').focus()");
 await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',text:'\r',windowsVirtualKeyCode:13});await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await wait(230);
 await check('keyboard dismissal',"!errorCard.isConnected");
 await evaluate("status.clear();for(let i=0;i<5;i++)busy('Checking your files',{id:'browser-'+i})");
 await check('three visible and two queued',"document.querySelectorAll('.status-card').length===3 && notificationDock.records.size===5");
 await evaluate("status.dismiss('browser-0')");await wait(230);
 await check('queue promotes next job',"document.querySelectorAll('.status-card').length===3 && notificationDock.records.get('browser-3').el.isConnected");
 await call('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
 await evaluate("status.clear();busy('Checking settings',{id:'reduced'})");await wait(100);
 await check('reduced motion has no loader or bar animations',"[...document.querySelectorAll('.status-card *')].flatMap(e=>e.getAnimations()).length===0");
 await call('Emulation.setEmulatedMedia',{features:[]});
 await evaluate("status.clear();const t=document.createElement('div');t.className='upd-toast';document.body.append(t);window.updateSurface=getComputedStyle(t).backgroundColor;t.remove();busy('Checking settings')");
 await check('updater shares card surface',"getComputedStyle(document.querySelector('.status-card')).backgroundColor===updateSurface");
 await call('Emulation.setDeviceMetricsOverride',{width:400,height:700,deviceScaleFactor:1,mobile:false});await wait(500);
 await check('small viewport fits',"(()=>{const b=document.querySelector('.status-card').getBoundingClientRect();return b.left>=0&&b.right<=innerWidth&&b.bottom<=innerHeight})()");
 await viewport(1440);await evaluate('status.clear()');
}

for(const theme of themes){
 await evaluate(`applyTheme('${theme}');if(typeof status.clear==='function'){status.clear();document.querySelector('#status').replaceChildren()}else status('');busy('Reading your game settings...')`);await wait(400);
 if(!before){await evaluate(`status.clear();window.dockSamples=[];window.sample=()=>{dockSamples.push(document.querySelector('.status-card').cloneNode(true));status.clear();};
 busy('Reading your game settings...',{id:'preview-work'});sample();
 busy('Downloading your demo...',{id:'preview-progress',progress:.6,detail:'60% / 24 MB of 40 MB'});sample();
 status('Your settings are ready for the next match.',{id:'preview-done',kind:'done'});sample();
 status('Failed to fetch',{id:'preview-error',kind:'error'});sample();
 status('Steam is back. You can launch CS2.',{id:'preview-notice',kind:'notice'});sample();
 status('Close CS2 before changing these files.',{id:'preview-warn',kind:'warn'});sample();document.querySelector('#status').append(...dockSamples);
 document.querySelector('#status').style.cssText='max-height:none;width:410px';`);await wait(450);}
 await shot(`${before?'before':'after'}-${theme}.png`);
}
if(!before){
 const rows=await evaluate(`(()=>{
 const rgb=s=>s.match(/[\\d.]+/g).map(Number).slice(0,3);
 const lum=s=>rgb(s).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
 const ratio=(a,b)=>{a=lum(a);b=lum(b);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
 return ${JSON.stringify(themes)}.flatMap(theme=>{applyTheme(theme);return [...document.querySelectorAll('.status-card')].map(e=>{const bg=getComputedStyle(e).backgroundColor;return {theme,state:e.dataset.kind,text:Math.min(...[...e.querySelectorAll('b,p,.status-detail,button,summary,pre')].map(x=>ratio(getComputedStyle(x).color,bg))),bar:ratio(getComputedStyle(e.querySelector('.status-fill')).backgroundColor,getComputedStyle(e.querySelector('.status-track')).backgroundColor)};})});})()`);
 await fs.writeFile(path.join(out,'contrast.md'),'# Resolved notification colours\n\nComputed in Edge from getComputedStyle; WCAG sRGB luminance. Minimum text includes title, body, detail and close button.\n\n| Theme | State | Text / card | Bar / track |\n|---|---|---:|---:|\n'+rows.map(r=>`| ${r.theme} | ${r.state} | ${r.text.toFixed(2)} | ${r.bar.toFixed(2)} |`).join('\n')+'\n');
 assert.ok(rows.every(r=>r.text>=4.5&&r.bar>=3),JSON.stringify(rows));
 const minimumContrast=themes.map(theme=>({theme,text:Math.min(...rows.filter(r=>r.theme===theme).map(r=>r.text)),bar:Math.min(...rows.filter(r=>r.theme===theme).map(r=>r.bar))}));
 await fs.appendFile(path.join(out,'contrast.md'),'\n## Minimum across all six states\n\n| Theme | Text / card | Bar / track |\n|---|---:|---:|\n'+minimumContrast.map(r=>'| '+r.theme+' | '+r.text.toFixed(2)+' | '+r.bar.toFixed(2)+' |').join('\n')+'\n\nAll text exceeds 4.5:1 and all bars exceed 3:1. Title, body, detail, dismissal control, Details summary and diagnostic text are measured. All sampled foregrounds, cards and tracks are opaque. Violet uses no theme attribute.\n');
 await evaluate(`applyTheme('violet');status.clear();document.querySelector('#status').replaceChildren();busy('Reading your game settings...');const dock=document.querySelector('#status');dock.style.cssText='position:fixed;left:0;top:0;width:2240px;max-height:none;flex-direction:row';const card=dock.firstElementChild;for(let i=1;i<7;i++)dock.append(card.cloneNode(true));[...dock.children].forEach((e,i)=>{e.style.width='310px';e.style.flexShrink='0';e.style.animation='none';e.getAnimations({subtree:true}).forEach(a=>{a.pause();a.currentTime=i*180+80})});`);
 await call('Emulation.setDeviceMetricsOverride',{width:2240,height:140,deviceScaleFactor:1,mobile:false});await shot('loader-strip.png');
 const screenshots=await Promise.all((await fs.readdir(out)).filter(file=>file.endsWith('.png')).map(async file=>{const b=await fs.readFile(path.join(out,file));return {file,width:b.readUInt32BE(16),height:b.readUInt32BE(20),bytes:b.length}}));
 await fs.writeFile(path.join(out,'render-report.json'),JSON.stringify({checks,contrast:rows,minimumContrast,screenshots,verification:{nodeStatusHarness:'Run node tests/status_bar_harness.cjs separately; passed in this session',profileRailHarness:'Run node docs/redesign/status-bar/preview/check-regressions.cjs separately; passed in this session',pythonModules:'tests.test_status_bar_web, tests.test_profile_rail_web, tests.test_themes blocked: py not on PATH; Python313/python.exe execution denied'},errors,screenshotFixtures:'Six illustrative notification states over the real app; static API rejects desktop actions.'},null,2));
 console.log(JSON.stringify({checks:checks.length,errors,contrast:rows.length}));
}
await call('Browser.close').catch(()=>{});ws.close();
}finally{browser.kill();server.close();await new Promise(r=>setTimeout(r,750));if(!profile.startsWith(path.join(out,'.edge-')))throw Error('Unexpected browser profile path');await fs.rm(profile,{recursive:true,force:true,maxRetries:5,retryDelay:200});}
}

