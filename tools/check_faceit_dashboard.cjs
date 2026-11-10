/* Offline Chrome checks using the real FACEIT renderer, demo handlers and CSS.
   Fixtures mirror demos.player/history/match_stats and webui._demos payloads.
   Only APIs and launching CS2 are stubbed; no user data is read or written. */
const fs=require('fs'),cp=require('child_process'),assert=require('assert'),vm=require('vm'),path=require('path'),url=require('url');
const root=path.resolve(__dirname,'..');process.chdir(root);
const work=path.join(root,'tmp','faceit-check');fs.mkdirSync(work,{recursive:true});
const html=fs.readFileSync('cs2cfg/web/index.html','utf8');
for(const script of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))new vm.Script(script[1]);
const renderer=fs.readFileSync('cs2cfg/web/assets/faceit/dashboard.js','utf8');new vm.Script(renderer);
const slice=(a,b)=>html.slice(html.indexOf(a),html.indexOf(b,html.indexOf(a)));
const themes=vm.runInNewContext(slice('const THEMES = [','function applyTheme(').replace('const THEMES =','')).map(t=>t[0]);
let code=`
const $=id=>document.getElementById(id),esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
const calls=[],checks=[];function check(name,ok){checks.push({name,ok:!!ok});if(!ok)throw Error(name)}
const settle=()=>new Promise(r=>setTimeout(r,20));
let cs2IsRunning=false,whoData={accounts:[{active:true,name:'Test Player'}]},launches=0;
function status(){}function noteChange(){}async function loadWho(){}
const fixture={ok:true,linked:true,player:{player_id:'p1',nickname:'Test Player',avatar:'',country:'GB',elo:1742,level:8},matches:Array.from({length:20},(_,i)=>({match_id:'1-'+String(i).padStart(8,'0')+'-8b31-4f2d-9c77-1a2b3c4d5e6f',map:'de_'+['mirage','inferno','nuke','ancient','anubis','vertigo','overpass','train','cache','dust2'][i%10],won:i%3!==1,score:i%3===1?'9 / 13':'13 / 9',rounds:22,elo:1742-i*5,elo_delta:i%3===1?-25:25,played_at:Math.floor(Date.now()/1000)-3600-i*86400,kills:20+i%6,deaths:14+i%4,assists:6,kd:1.43,adr:85.2+i%9,team:'team_Test Player'}))};
{let elo=fixture.player.elo;for(const m of fixture.matches){m.elo=elo;elo-=m.elo_delta;}}
let answer=structuredClone(fixture),disk={ok:true,folder:'C:/CS2/replays',demos:[{name:'faceit_00000000_demirage.dem',size:184549376,when:Math.floor(Date.now()/1000)-3600},{name:'match730_003839357250947346477_1108066476_161.dem',size:235000000,when:Math.floor(Date.now()/1000)-3600}],picked:'',key:'F9',job:null};
const scoreboard={match_id:fixture.matches[0].match_id,map:'de_mirage',score:'13 / 9',rounds:22,played_at:fixture.matches[0].played_at,mode:'5v5',region:'EU',page:'https://www.faceit.com/en/cs2/room/'+fixture.matches[0].match_id,teams:[{name:'team_Test Player',score:13,first_half:7,second_half:6,won:true,players:[{nickname:'Test Player',kills:20,deaths:14,assists:6,adr:85.2,kd:1.43,kr:.91,headshots:10,hs_percent:50,penta:0,quadro:0,triple:1,double:2,mvps:3}]}]};
async function api(route,body){calls.push({route,body});if(route==='/api/faceit')return structuredClone(answer);if(route==='/api/faceit/forget'){answer={ok:true,linked:false};return answer;}if(route==='/api/demos')return structuredClone(disk);if(route==='/api/demos/stats')return structuredClone(scoreboard);if(route==='/api/demos/pick'){disk.picked=body.name;return {ok:true};}if(route==='/api/demos/waiting')return {waiting:null};if(route==='/api/demos/get')return {already:true,name:disk.demos[0].name};return {ok:true};}
`+renderer+'\n'+slice('let demoData = null;','/* Crosshair X.');
code+=`
document.documentElement.dataset.boot='ready';document.querySelector('.boot-screen')?.remove();$('status')?.remove();
document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('hidden',p.dataset.panel!=='faceit'));
document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.tab==='faceit')));
$('play').addEventListener('click',()=>launches++);
(async()=>{try{
await loadDemos();await loadFaceit();await settle();
$('fc-refresh').click();await settle();check('Refresh requests forced read',calls.some(c=>c.route==='/api/faceit'&&c.body.force));
check('20 match cards',document.querySelectorAll('.fc-match').length===20);
check('computed headline values',[...document.querySelectorAll('.fc-stat strong')].map(e=>e.textContent).join('|')==='1.44|88.9|65%');
showDemoJob({active:true,total:2000,seen:1000});check('download progress visible',$('demo-bar-fill').style.width==='50%'&&!$('demo-prog').classList.contains('hidden'));$('demo-cancel').click();await settle();check('Cancel uses existing endpoint',calls.some(c=>c.route==='/api/demos/cancel'));showDemoJob(null);
check('actual overview data',$('fc-wrap').textContent.includes('1742')&&$('fc-wrap').textContent.includes('85.2'));
check('HS omitted from overview',!$('fc-wrap').textContent.includes('HS%'));
check('downloaded match marked',document.querySelector('.fc-match').textContent.includes('Downloaded'));
check('chronological ELO table',[...document.querySelector('.fc-chart-table tbody').rows][0].textContent.includes(String(fixture.matches.at(-1).elo)));
check('map aggregation 2 matches per map',[...document.querySelectorAll('.fc-map-bar small')].every(e=>e.textContent.endsWith('/2')));
document.querySelector('[data-fc-expand]').click();check('match expands',!$('fc-detail-0').hidden);
await loadFaceit();check('refresh preserves expanded match',!$('fc-detail-0').hidden);
document.querySelector('[data-fc-metric="adr"]').click();check('ADR switches trend',$('fc-trend-plot').querySelector('svg').getAttribute('aria-label').startsWith('ADR'));
document.querySelector('[data-match]').click();await settle();check('Stats opens original scoreboard',!$('mstat-back').classList.contains('hidden')&&calls.some(c=>c.route==='/api/demos/stats'));
$('mstat-close').click();check('scoreboard closes',$('mstat-back').classList.contains('hidden'));
document.querySelector('[data-pick]').click();await settle();check('Choose uses existing endpoint',disk.picked===disk.demos[0].name&&document.querySelector('[data-pick]').textContent==='Clear choice');
document.querySelector('[data-pick]').click();await settle();check('Choose clears existing selection',disk.picked==='');
document.querySelector('[data-watch]').click();await settle();check('Watch picks once and launches',launches===1&&calls.some(c=>c.route==='/api/demos/pick'&&c.body.once));
$('demo-link').value='https://www.faceit.com/en/cs2/room/'+fixture.matches[0].match_id;$('demo-fetch').click();await settle();check('Get demo keeps stats and download calls',calls.some(c=>c.route==='/api/demos/get')&&!$('mstat-back').classList.contains('hidden'));hideStats();
answer={ok:true,linked:false};await loadFaceit();$('fc-nick').value='Unfinished';await loadFaceit();check('poll preserves nickname',$('fc-nick').value==='Unfinished');
answer=structuredClone(fixture);$('fc-nick').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));await settle();check('Enter follows nickname',calls.some(c=>c.route==='/api/faceit'&&c.body.nickname==='Unfinished'));
answer={ok:false,linked:true,error:'FACEIT has no player called Test'};await loadFaceit();check('account error and retry',$('fc-wrap').textContent.includes('FACEIT has no player')&&$('fc-refresh')&&$('fc-forget'));
answer={ok:false,error:'Offline'};await loadFaceit();check('transport error visible',$('fc-wrap').textContent.includes('Offline'));
answer={...structuredClone(fixture),stale:true,error:'Could not reach FACEIT'};await loadFaceit();check('stale payload keeps cards and warning',document.querySelector('.fc-warning')&&document.querySelectorAll('.fc-match').length===20);
answer={...structuredClone(fixture),matches:[]};await loadFaceit();check('empty history has no charts',!document.querySelector('.fc-charts')&&$('fc-wrap').textContent.includes('No CS2 matches'));
answer={...structuredClone(fixture),matches:[{...fixture.matches[0],kills:0,deaths:0,adr:null,elo:0,elo_delta:null,map:'workshop_unknown',played_at:0}]};await loadFaceit();check('zero deaths and missing values remain unknown',!$('fc-wrap').innerHTML.match(/NaN|Infinity|undefined/));check('unknown map fallback',document.querySelector('.fc-map-art').src.endsWith('/fallback.webp'));check('no invented ELO',document.querySelector('.fc-chart').textContent.includes('No ELO readings'));
disk={...disk,folder:'',demos:[]};await loadDemos();check('missing CS2 install message',$('demo-list').textContent.includes('install was not found'));
disk={...disk,folder:'C:/CS2/replays'};await loadDemos();check('empty replay message',$('demo-list').textContent.includes('No demos'));
answer=structuredClone(fixture);answer.matches[3].elo=0;await loadFaceit();check('missing ELO breaks line',document.querySelector('.fc-plot path').getAttribute('d').split('M').length===3);
for(const level of [1,2,3,4,5,6,7,8,9,10]){answer.player.level=level;await loadFaceit();check('level '+level+' badge',document.querySelector('.fc-level').textContent===String(level));}
answer.player.level=8;answer.player.nickname='<img src=x onerror=alert(1)>';answer.matches[0].team='<script>bad</script>';await loadFaceit();check('payload strings escaped',!document.querySelector('.fc-identity img')&&$('fc-wrap').textContent.includes('<script>bad</script>'));
answer=structuredClone(fixture);await loadFaceit();
$('fc-forget').click();await settle();check('Unfollow uses forget endpoint',calls.some(c=>c.route==='/api/faceit/forget')&&$('fc-nick'));answer=structuredClone(fixture);await loadFaceit();
for(const theme of ${JSON.stringify(themes)}){document.documentElement.dataset.theme=theme;await settle();check('theme '+theme+' no overflow',document.documentElement.scrollWidth<=innerWidth);check('theme '+theme+' visible controls',getComputedStyle($('fc-refresh')).display!=='none');}
check('workspace has no internal horizontal overflow',document.querySelector('.scroll').scrollWidth<=document.querySelector('.scroll').clientWidth);
check('match controls fit every card',[...document.querySelectorAll('.fc-match')].every(card=>{const a=card.querySelector('.fc-match-toggle').getBoundingClientRect(),b=card.querySelector('.fc-match-actions').getBoundingClientRect(),c=card.getBoundingClientRect();return a.right<=b.left+1&&b.right<=c.right+1;}));
delete document.documentElement.dataset.theme;
const panel=document.querySelector('[data-panel="faceit"]');panel.classList.add('hidden');fcPauseMotion();check('hidden tab pauses animations',document.documentElement.classList.contains('fc-paused'));panel.classList.remove('hidden');fcPauseMotion();
check('reduced motion CSS present',[...document.styleSheets].some(s=>{try{return [...s.cssRules].some(r=>r.conditionText?.includes('prefers-reduced-motion')&&r.cssText.includes('faceit'))}catch{return false}}));
if(matchMedia('(prefers-reduced-motion: reduce)').matches)check('reduced motion removes chart animation',getComputedStyle(document.querySelector('.fc-draw')).animationName==='none');
Object.defineProperty(document,'hidden',{configurable:true,value:true});fcPauseMotion();check('hidden window pauses chart animation',getComputedStyle(document.querySelector('.fc-draw')).animationPlayState==='paused');delete document.hidden;fcPauseMotion();
for(const name of [...FC_MAPS,'fallback']){await new Promise(resolve=>{const i=new Image();i.onload=()=>{check(name+' WebP loads',i.naturalWidth===560);resolve()};i.onerror=()=>{check(name+' WebP loads',false);resolve()};i.src='assets/maps/'+name+'.webp';});}
check('mask references replaceable logo',getComputedStyle(document.querySelector('.fc-top .fc-logo')).maskImage.includes('faceit-logo.svg'));
check('stamp uses logo mask',getComputedStyle(panel,'::before').maskImage.includes('faceit-logo.svg'));
// Final screenshot has a small realistic library and one expanded match.
disk.demos=[{name:'faceit_00000000_demirage.dem',size:184549376,when:Math.floor(Date.now()/1000)-3600}];await loadDemos();document.querySelector('[data-fc-expand]').click();document.querySelector('.scroll').scrollTop=0;
}catch(e){checks.push({error:e.stack})}document.body.insertAdjacentHTML('beforeend','<pre id="checks">'+JSON.stringify(checks)+'</pre>');})();`;
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
  const viewport=process.env.FACEIT_VIEWPORT||'1440,1000',scale=Number(process.env.FACEIT_SCALE||1);
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
  const {result}=await command('Runtime.evaluate',{expression:'document.documentElement.outerHTML',returnByValue:true});
  fs.writeFileSync(path.join(work,'dom.html'),result.value);
  await new Promise(r=>setTimeout(r,850));
  const shot=await command('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(work,'preview.png'),Buffer.from(shot.data,'base64'));
  await command('Runtime.evaluate',{expression:'document.querySelector(".scroll").scrollTop=document.querySelector(".fc-section-head").offsetTop-30'});
  await new Promise(r=>setTimeout(r,150));
  const history=await command('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(work,'history.png'),Buffer.from(history.data,'base64'));
  await command('Runtime.evaluate',{expression:'document.querySelector(".scroll").scrollTop=document.getElementById("demo-card").offsetTop-30'});
  await new Promise(r=>setTimeout(r,150));
  const library=await command('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(work,'library.png'),Buffer.from(library.data,'base64'));
  if(process.env.FACEIT_CAPTURE_THEMES){
   for(const theme of ['violet','ember','carbon','acid','daylight','paper','pro']){
    await command('Runtime.evaluate',{expression:'document.documentElement.dataset.theme='+JSON.stringify(theme)+';new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))',awaitPromise:true});
    const themed=await command('Page.captureScreenshot',{format:'png'});
    fs.writeFileSync(path.join(work,theme+'.png'),Buffer.from(themed.data,'base64'));
   }
  }
  const failures=results.filter(c=>c.ok===false||c.error||c.geometry);
  console.log(JSON.stringify({viewport,scale,checks:results.length,failures,preview:path.join(work,'preview.png')}));
  assert(results.length>=65&&!failures.length);
 }finally{if(socket)socket.close();browser.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
