/* Offline Chrome checks using the real stats renderer, demo handlers and CSS.
   Fixtures mirror /api/stats, /api/faceit and demo payloads.
   Only APIs and launching CS2 are stubbed; no user data is read or written. */
const fs=require('fs'),cp=require('child_process'),assert=require('assert'),vm=require('vm'),path=require('path'),url=require('url');
const root=path.resolve(__dirname,'..');process.chdir(root);
const work=path.join(root,'docs/redesign/stats-merge/.work');
fs.mkdirSync(work,{recursive:true});
const html=fs.readFileSync('cs2cfg/web/index.html','utf8');
for(const script of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))new vm.Script(script[1]);
const renderer=fs.readFileSync('cs2cfg/web/assets/faceit/dashboard.js','utf8');new vm.Script(renderer);
const slice=(a,b)=>html.slice(html.indexOf(a),html.indexOf(b,html.indexOf(a)));

// This isolated Stats fixture does not boot the account dock. Its refresh hook
// is covered by docs/redesign/accounts-dock/capture.cjs with the real dock.
let code=['function renderAccountsDock() {}',fs.readFileSync('tests/stats_merge_browser.js','utf8'),renderer,slice('let demoData = null;','/* Crosshair X.'),'runStatsChecks();'].join('\n');
let page=html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'').replace('<head>','<head><base href="'+url.pathToFileURL(path.join(root,'cs2cfg/web/')).href+'">');
if(process.env.FACEIT_RAIL)page=page.replace('<div class="app"','<div style="--rail:'+Number(process.env.FACEIT_RAIL)+'px" class="app"');
// Escaped malicious fixture text must not terminate the harness script element.
code=code.replaceAll('</script','<\\/script');
page=page.replace('</body>','<script>'+code+'</script></body>');fs.writeFileSync(path.join(work,'preview.html'),page);
const chrome=process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe';
// Use real compositor frames rather than --virtual-time-budget: ResizeObserver
// and transitions need to settle before measuring the result of a live resize.
const args=['--headless','--no-sandbox','--disable-gpu','--allow-file-access-from-files','--remote-debugging-port=0','--user-data-dir='+path.join(work,'chrome'),'about:blank'];
if(process.env.FACEIT_REDUCED)args.unshift('--force-prefers-reduced-motion');
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
  const viewport=process.env.FACEIT_VIEWPORT||'1440,1200',scale=Number(process.env.FACEIT_SCALE||1);
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

  const failures=results.filter(c=>c.ok===false||c.error);
  const preview=path.join(root,'docs/redesign/stats-merge/preview');
  fs.mkdirSync(preview,{recursive:true});
  if(failures.length) {
    const shot=await command('Page.captureScreenshot',{format:'png'});
    fs.writeFileSync(path.join(work,'failure.png'),Buffer.from(shot.data,'base64'));
  } else if(process.env.STATS_CAPTURE_PREVIEWS!=='0') {
    for(const name of ['all','faceit','cs2','cs2-empty','faceit-not-linked','daylight']) {
      await command('Runtime.evaluate',{expression:'setStatsPreview('+JSON.stringify(name)+')',awaitPromise:true});
      const shot=await command('Page.captureScreenshot',{format:'png'});
      fs.writeFileSync(path.join(preview,name+'.png'),Buffer.from(shot.data,'base64'));
    }
  }
  console.log(JSON.stringify({viewport,scale,checks:results.length,failures,preview,debug:work}));
  assert(results.length>=50&&!failures.length);
 }finally{if(socket)socket.close();browser.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
