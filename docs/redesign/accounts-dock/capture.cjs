/* No npm dependencies. Node 22+ and a local Chrome installation.
   Run: node docs/redesign/accounts-dock/capture.cjs
   Set CHROME_PATH if needed. All browser data stays in this repository. */
const fs=require('fs'),path=require('path'),http=require('http'),cp=require('child_process'),assert=require('assert');
const root=path.resolve(__dirname,'../../..'),work=path.join(__dirname,'.work'),out=path.join(__dirname,'preview');
fs.mkdirSync(work,{recursive:true});fs.mkdirSync(out,{recursive:true});
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp','.woff2':'font/woff2'};
const server=http.createServer((req,res)=>{
  const file=path.resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
  if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
  fs.readFile(file,(err,data)=>{if(err){res.writeHead(404).end();return;}res.setHeader('Content-Type',mime[path.extname(file)]||'application/octet-stream');res.end(data);});
});
let browser,socket;
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  browser=cp.spawn(process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',[
    '--headless','--no-sandbox','--disable-gpu','--no-first-run','--remote-debugging-port=0','--user-data-dir='+path.join(work,'chrome'),'about:blank'
  ],{stdio:['ignore','ignore','pipe'],windowsHide:true});
  const endpoint=await new Promise((resolve,reject)=>{
    let stderr='';const timer=setTimeout(()=>reject(Error('Chrome startup timed out: '+stderr)),15000);
    browser.stderr.on('data',data=>{stderr+=data;const found=stderr.match(/DevTools listening on (ws:\/\/\S+)/);if(found){clearTimeout(timer);resolve(found[1]);}});
    browser.on('error',error=>{clearTimeout(timer);reject(error);});
  });
  socket=new WebSocket(endpoint);await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j;});
  let id=0;const pending=new Map(),errors=[];
  socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}else if(m.method==='Runtime.consoleAPICalled')console.log(m.params.args.map(a=>a.value).join(' '));else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text+': '+m.params.exceptionDetails.exception?.description);};
  const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params,sessionId}));});
  const {targetId}=await send('Target.createTarget',{url:'about:blank'});
  const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
  const command=(method,params={})=>send(method,params,sessionId);
  const evaluate=async expression=>{
    const result=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);
    return result.result.value;
  };
  await command('Page.enable');await command('Runtime.enable');
  await command('Emulation.setDeviceMetricsOverride',{width:1280,height:900,deviceScaleFactor:1,mobile:false});
  await command('Page.navigate',{url:'http://127.0.0.1:'+server.address().port+'/docs/redesign/accounts-dock/preview.html'});
  const deadline=Date.now()+20000;
  while(!await evaluate('document.documentElement.dataset.previewReady')&&Date.now()<deadline)await new Promise(r=>setTimeout(r,100));
  assert(await evaluate('document.documentElement.dataset.previewReady'),'Preview did not initialize');
  let checks=0;
  const check=async(name,expression)=>{assert(await evaluate(expression),name);checks++;};
  const pause=ms=>new Promise(r=>setTimeout(r,ms));
  const shot=async name=>{const {data}=await command('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(out,name+'.png'),Buffer.from(data,'base64'));};
  for(const [state,name,open] of [['ember','closed-ember',false],['ember','open-ember',true],['violet','open-violet',true],['reading','steam-web-reading',true],['collapsed','collapsed-rail-closed',false],['collapsed','collapsed-open',true],['daylight','daylight-open',true]]){
    await evaluate('previewState('+JSON.stringify(state)+')');
    await pause(800);
    if(open) await evaluate("$('dock-main').click()");
    await pause(1150);
    await check(state+' accessible rows',"document.querySelectorAll('#dock-rows .dock-row[aria-label]').length==="+(state==='violet'?4:6));
    await check(state+' fits the rail',"(()=>{const rail=document.querySelector('.rail').getBoundingClientRect(),dock=$('accounts-dock').getBoundingClientRect(),update=$('updc').getBoundingClientRect();return dock.top>rail.top && update.bottom<=rail.bottom && dock.bottom<=update.top;})()");
    await check(state+' menu never scrolls at 900px',"document.querySelector('.tabs').scrollHeight<=document.querySelector('.tabs').clientHeight");
    await check(state+' no horizontal overflow',"$('accounts-dock').scrollWidth<=$('accounts-dock').clientWidth");
    if(state==='collapsed'){
      await check('collapsed main shows only avatar',"getComputedStyle($('dock-main').querySelector('.dock-copy')).display==='none'&&getComputedStyle($('dock-main').querySelector('.dock-cluster')).display==='none'");
      if(open) await check('collapsed flyout has names and sits right of rail',"getComputedStyle($('dock-steam').querySelector('.dock-copy')).display==='flex'&&$('dock-panel').getBoundingClientRect().left>document.querySelector('.rail').getBoundingClientRect().right");
    }
    await shot(name);
  }
  await evaluate("previewState('ember')");await pause(800);
  await evaluate("previewCalls.length=0;$('dock-main').click()");
  await check('toggle opens without launching switcher',"dockExpanded&&$('dock-main').getAttribute('aria-expanded')==='true'&&!previewCalls.some(c=>c[0]==='switcher'&&c[1])&&document.activeElement.id==='dock-steam'");
  for(let i=1;i<=3;i++){await pause(i===1?70:160);await shot('open-anim-'+i);}
  const frameFiles=[1,2,3].map(i=>'data:image/png;base64,'+fs.readFileSync(path.join(out,'open-anim-'+i+'.png')).toString('base64'));
  const strip=await evaluate('(async()=>{const urls='+JSON.stringify(frameFiles)+';const c=document.createElement("canvas");c.width=1020;c.height=410;const ctx=c.getContext("2d");for(let i=0;i<urls.length;i++){const im=new Image();im.src=urls[i];await im.decode();ctx.drawImage(im,2,325,340,410,i*340,0,340,410);}return c.toDataURL("image/png").split(",")[1];})()');
  fs.writeFileSync(path.join(out,'open-anim-strip.png'),Buffer.from(strip,'base64'));
  await evaluate("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))");
  await check('Escape closes and returns focus',"!dockExpanded&&document.activeElement.id==='dock-main'&&$('dock-panel').inert");
  await evaluate("$('dock-main').click()");await pause(1150);
  await check('open rows finish unfolding',"[...document.querySelectorAll('#dock-rows .dock-row')].every(r=>getComputedStyle(r).opacity==='1')");
  await evaluate("$('dock-main').click()");
  await check('closing panel stays rendered for reverse animation',"$('dock-panel').matches(':popover-open')&&!$('dock-panel').classList.contains('is-open')");
  await pause(800);
  await check('closed panel leaves top layer',"!$('dock-panel').matches(':popover-open')");
  await check('main row toggles closed',"!dockExpanded");
  await command('Page.bringToFront');
  await evaluate("$('dock-main').focus()");
  await command('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',text:'\r',unmodifiedText:'\r',windowsVirtualKeyCode:13});
  await command('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await check('Enter opens and focuses first row',"dockExpanded&&document.activeElement.id==='dock-steam'");
  await command('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
  await command('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
  await check('Tab reaches the next Steam account',"document.activeElement.id==='dock-local-0'");
  await evaluate("document.body.click()");
  await check('outside click closes and returns focus',"!dockExpanded&&document.activeElement.id==='dock-main'");
  await evaluate("$('dock-main').click();$('dock-local-0').click();new Promise(r=>setTimeout(r,20))");
  await check('other Steam account uses existing switch and reload',"previewCalls.some(c=>c[0]==='/api/profile/use'&&c[1].account==='200')&&previewCalls.some(c=>c[0]==='reload-account')&&whoData.accounts.find(a=>a.active)?.account==='200'&&!dockExpanded");
  await evaluate(`previewState('violet')`);
  await check('Stats Steam card removed',`!$('fc-steam-signin')&&!document.querySelector('.fc-follow-card .fc-cs2-logo')`);
  await check('Connect and Follow actions visible',`$('dock-web').textContent.includes('Connect')&&$('dock-faceit').textContent.includes('Follow')`);
  await evaluate(`previewCalls.length=0;$('dock-main').click();$('dock-steam').click()`);
  await check('dock opening survives the existing click-away handler',`previewCalls.filter(c=>c[0]==='switcher').at(-1)?.[1]===true`);
  await evaluate(`$('dock-steam').click();$('dock-cloud').click();$('dock-faceit').click()`);
  await check('existing destinations reused',`previewCalls.some(c=>c[0]==='switcher')&&previewCalls.some(c=>c[0]==='settings'&&c[1]==='account')&&document.activeElement.id==='fc-nick'`);
  await evaluate(`previewCalls.length=0;$('dock-web').click();$('dock-web').click();new Promise(r=>setTimeout(r,20))`);
  await check('one login window and pending status',`previewCalls.filter(c=>c[0]==='/api/stats/steam'&&c[1].action==='signin').length===1 && $('dock-web').dataset.state==='waiting'`);
  await evaluate(`fcSteamReply={linked:true,available:true,state:'reading'};loadDockSteam()`);
  await check('login completes into reading',`!dockSteamWaiting&&$('dock-web').textContent.includes('Reading match history')`);
  await check('reading session remains linked',`$('dock-summary').textContent==='1 / 4'`);
  await evaluate(`fcSteamReply={linked:true,available:true,state:'done',found:256,updated:1794902400};loadDockSteam()`);
  await check('count and update timestamp reflected',`$('dock-web').textContent.includes('256 matches')&&$('dock-web').title.includes('Updated')`);
  await evaluate(`dockSteamWaiting=Date.now()-1;fcSteamReply={linked:false,available:true,state:'idle'};loadDockSteam()`);
  await check('login times out and offers retry',`!dockSteamWaiting&&$('dock-web').textContent.includes('timed out')&&$('dock-web').textContent.includes('Connect')`);
  await evaluate(`dockSteamNotice='';fcSteamReply={linked:false,available:false,state:'unavailable'};loadDockSteam()`);
  await check('unavailable desktop login disabled',`$('dock-web').disabled&&$('dock-web').textContent.includes('desktop app')`);
  await evaluate(`fcSteamReply={linked:false,available:true,state:'signed_out'};loadDockSteam()`);
  await check('expired session offers reconnect',`!$('dock-web').disabled&&$('dock-web').textContent.includes('Session expired')&&$('dock-web').textContent.includes('Connect')`);
  await evaluate(`api=async()=>{throw Error('Offline fixture')};loadDockSteam()`);
  await check('API error remains visible',`$('dock-web').dataset.state==='error'&&$('dock-web').title.includes('Offline fixture')`);
  await evaluate(`api=async()=>fcSteamReply;previewState('ember');dockToggle(true);$('dock-steam').focus();renderAccountsDock()`);
  await check('refresh preserves keyboard focus',`document.activeElement.id==='dock-steam'`);
  await check('polling uses 3 seconds for sign-in/reading and 30 seconds at rest',`(()=>{const original=window.setTimeout,delays=[];window.setTimeout=(fn,delay)=>{delays.push(delay);return null;};try{clearTimeout(dockSteamTimer);dockSteamWaiting=Date.now()+600000;dockScheduleSteam();dockSteamWaiting=0;dockSteam.state='reading';dockScheduleSteam();dockSteam.state='done';dockScheduleSteam();return JSON.stringify(delays)==='[3000,3000,30000]';}finally{window.setTimeout=original;}})()`);
  // Finish theme transitions deterministically for token comparisons. Motion
  // behavior is checked separately below; preview PNGs retain normal motion.
  await command('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  for(const theme of ['violet','ember','carbon','acid','crimson','frost','neon','daylight','paper','pro']){
    await evaluate(`document.documentElement.dataset.theme='${theme}'`);
    await new Promise(r=>setTimeout(r,450));
    await check(theme+' uses theme text and surface',`(()=>{const reference=document.createElement('span');reference.style.cssText='color:var(--ink);background:var(--panel-2)';document.body.append(reference);const expected=getComputedStyle(reference),actual=getComputedStyle($('dock-steam')),face=getComputedStyle($('dock-steam').querySelector('.dock-face'));const ok=actual.color===expected.color&&face.backgroundColor===expected.backgroundColor;reference.remove();return ok;})()`);
  }
  await command('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  await check('reduced motion makes unfold instant',"getComputedStyle($('dock-panel')).transitionDuration==='0s'&&getComputedStyle($('dock-steam')).transitionDuration==='0s'");
  await check('reduced motion disables linked glow',`getComputedStyle(document.querySelector('.dock-face')).animationName==='none'`);
  await command('Emulation.setEmulatedMedia',{features:[]});
  await evaluate(`Object.defineProperty(document,'hidden',{value:true,configurable:true});document.dispatchEvent(new Event('visibilitychange'))`);
  await check('hidden window pauses motion',`getComputedStyle(document.querySelector('.dock-face')).animationPlayState==='paused'`);
  await command('Emulation.setDeviceMetricsOverride',{width:1024,height:768,deviceScaleFactor:1,mobile:false});
  await evaluate(`previewState('ember')`);
  await evaluate("Object.defineProperty(document,'hidden',{value:false,configurable:true});dockPauseMotion();dockToggle(true)");
  await check('small laptop panel stays inside viewport',"$('dock-panel').getBoundingClientRect().top>=12");
  await check('small laptop keeps dock and updates visible',`$('updc').getBoundingClientRect().bottom<=768 && document.querySelector('.tabs').clientHeight>76`);
  assert.deepEqual(errors,[],'Uncaught browser errors');
  console.log('Passed '+checks+' browser checks; preview PNGs saved to '+out);
  await send('Browser.close');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{socket?.close();browser?.kill();server.close();});
