const fs=require('fs'),cp=require('child_process'),assert=require('assert');
const path=require('path'),url=require('url');
const root=path.resolve(__dirname,'..');process.chdir(root);
const work=path.join(require('os').tmpdir(),'cs-config-home-'+require('crypto').createHash('sha1').update(root).digest('hex').slice(0,8));fs.mkdirSync(work,{recursive:true});
const s=fs.readFileSync('cs2cfg/web/index.html','utf8').replace(/\r\n/g,'\n');
for(const x of s.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))new (require('vm').Script)(x[1]);
const themes=require('vm').runInNewContext(s.slice(s.indexOf('const THEMES = [')+'const THEMES = '.length,s.indexOf('function applyTheme(')).trim().replace(/;$/, '')).map(t=>t[0]);
const slice=(a,b)=>{const start=s.indexOf(a),end=s.indexOf(b,start);assert(start>=0&&end>start,'Missing source boundary: '+a+' to '+b);return s.slice(start,end)};
let code=fs.readFileSync(path.join(root,'cs2cfg/web/assets/hardware/icons.js'),'utf8')+'\n'+fs.readFileSync(path.join(root,'cs2cfg/web/assets/fixit/icons.js'),'utf8')+'\n'+`const $=id=>document.getElementById(id); const esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');let intent='balanced',planned={},prefs=0,previews=0;function applyProfile(){previews++}function previewPlan(){previews++}const INTENTS=['competitive','balanced','quality'];function paintModeBadge(){} function rememberPrefs(){prefs++} function noteChange(){} function requestBody(){return {intent,target_fps:240}};let netApi;async function api(url,b){if(url.startsWith("/api/net"))return netApi(url,b);return {intent:b.intent,estimated_fps:{competitive:410,balanced:340,quality:230}[b.intent]}};const tempAlarm={};function status(){};`;
code+=slice("function renderHardware(d) {","/* The machine's scores,");
code+=`let prefsNow={},audioData=null;`;
code+=slice('function audioOptions(list, pinned)', 'async function saveAudio');
code+=slice('let wgData = null;','/* What the launch did about the crosshair.');
code+=slice('const CHIPS = { CPU:', '// -- 2. the gradient');
code+=slice('/* Launcher motion:','function renderPlan(');
code+=`function setTab(name){activeTab=name;document.querySelectorAll('.tab-panel').forEach(panel=>panel.classList.toggle('hidden',panel.dataset.panel!==name))};`;
code+=slice('/* Every card uses','const APPLY_WHAT =');
code+=slice('const APPLY_WHAT =','/* Profile Rail:').replace('async function applyProfile(', 'async function applyProfileForCheck(');
code+='const profileRail={syncStatus(){}};function settleChanges(){};';
code+='function busy(){};';
code+=`let fpsEffect='';function renderFps(){}function markPending(){};`;
code+=slice('function renderPlan(', '// The last detection,');
code+=slice('let netTimer = null;', '/* Three scene cards');
const side=process.env.HOME_AGENT_SIDE==='t'?'t':'ct';
code+='const sceneRandom=Math.random;Math.random=()=>'+(side==='ct'?.25:.75)+';\n';
code+=fs.readFileSync(path.join(root,'cs2cfg/web/assets/home/launcher-scene.js'),'utf8')+'\n';
code+='Math.random=sceneRandom;\n';
code+=`const prefsReady=false,startup={finished:false};function moveSegThumb(){};`;
code+=slice('let settingsSub = "nvidia";', '/* ---------------------------------------------------------------------------\n   Sound devices');
code+='let cloudData=null, whoData={ok:true,accounts:[]}, activeTab="launcher"; function loadCloud(){} function loadFaceit(){} function paintFace(){}';
code+=fs.readFileSync(path.join(root,'cs2cfg/web/assets/accounts/dock.js'),'utf8')+'\n';
code+=slice('const WAY_ICONS = {', 'async function loadCloud()');
code+=slice('function cloudWay(', 'function showPasswordForm(');
code+=slice('function ring(value','function meter(');
code+=slice('/* Administrator helper status','/* ------');
code+=slice('// Horizontal thermal strips','// --- live system readout');
code+=`document.documentElement.dataset.boot='ready';document.querySelector('.boot-screen').remove();$('steam-preview').addEventListener('click',()=>previews++);
const checks=[];function check(name,ok){checks.push({name,ok});document.documentElement.dataset.lastCheck=name;if(!ok)throw Error(name)}
(async()=>{try{
check('hero controls remain inside hero', $('home-hero').contains($('play')) && $('home-hero').contains($('launch-modes')));
const hero=$('home-hero'),scene=hero.querySelector('.hero-scene');
const screen=scene.querySelector('.hero-banner'),agent=scene.querySelector('.hero-background'),keypress=scene.querySelector('.hero-keypress');
const side=${JSON.stringify(side)};
const still=screen.getAttribute('src');
await Promise.all([screen,agent,keypress].map(image=>new Promise((resolve,reject)=>{
  if (image.complete) return image.naturalWidth ? resolve() : reject(Error(image.src));
  image.addEventListener('load',resolve,{once:true});
  image.addEventListener('error',()=>reject(Error(image.src)),{once:true});
})));
check('Launcher loads both static banner and selected original agent',
  still.endsWith('hero-steam-banner.png')&&screen.naturalWidth===800&&screen.naturalHeight===450&&
  agent.getAttribute('src').endsWith('hero-agent-'+side+'.webp')&&agent.naturalWidth===2172&&keypress.naturalWidth===234&&
  scene.dataset.side===side&&!hero.querySelector('video'));
check('Launcher keyboard and handheld have no RGB overlays',
  !hero.querySelector('.launcher-desk-keys,.launcher-desk-handheld'));
check('hero waits for CS2 process status before animating hands',hero.classList.contains('scene-paused'));
launcherScene.activity(false);
if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
  check('reduced motion keeps the banner and leaves the hands still',
    screen.getAttribute('src')===still&&hero.classList.contains('scene-paused')&&getComputedStyle(keypress).animationName==='none');
} else {
  check('hands animate while Launcher is idle',getComputedStyle(keypress).animationPlayState==='running');
  launcherScene.launching(true);
  check('Play immediately freezes hands and keeps the same banner',
    screen.getAttribute('src')===still&&getComputedStyle(keypress).animationPlayState==='paused');
  check('Play freezes the desk accent animation',getComputedStyle(hero.querySelector('.launcher-desk-light')).animationPlayState==='paused');
  launcherScene.activity(true);launcherScene.launching(false);
  check('running CS2 keeps the hands still',hero.classList.contains('scene-paused'));
  launcherScene.activity(false);
  check('Launcher resumes hand motion after CS2 closes',!hero.classList.contains('scene-paused')&&screen.getAttribute('src')===still);
}
launcherScene.activity(true);
$('intents').querySelector('[data-intent="quality"]').click();check('card selection saves and previews',intent==='quality'&&prefs===1&&previews===1);
$('intents').dispatchEvent(new KeyboardEvent('keydown',{key:'Home',bubbles:true}));check('keyboard selects competitive',intent==='competitive'&&prefs===2&&previews===2);
const markup=n=>ring(n,'CPU',null)+ring(42,'GPU','56\\u00b0C')+ring(55,'RAM','16 / 32 GB')+ring(null,'VRAM',null);
homePatchReadouts($('live-gauges'),markup(25));const node=$('live-gauges').firstElementChild;homePatchReadouts($('live-gauges'),markup(80));check('gauge nodes persist',node===$('live-gauges').firstElementChild);check('unknown reading remains unknown',$('live-gauges').lastElementChild.querySelector('.val').textContent==='—');
renderScores({headroom:1.4,target_fps:240,cpu_score:88,gpu_score:75,cpu_ceiling:500,gpu_ceiling:450},70,'var(--good)');
renderTemps({parts:[{part:'gpu',label:'GPU',known:true,celsius:56,state:'fine'},{part:'board',label:'System',known:false,unavailable:'needs administrator'}],can_elevate:true});check('administrator state and unlock preserved',!!$('temps-unlock')&&$('live-temps').textContent.includes('needs administrator'));
const history={cpu:[],gpu:[],ram:[],vram:[]};for(let i=0;i<60;i++){history.cpu.push(25+12*Math.sin(i/3));history.gpu.push(55+15*Math.sin(i/5));history.ram.push(52+4*Math.sin(i/6));history.vram.push(18+9*Math.sin(i/4))}
const userMotion=homeMotion.reduced;homeMotion.reduced={matches:false};
hardwareUpdate({at:100,history,gpu:{temperature:56},temps:{parts:[{part:'system',known:true,celsius:38}]}});
check('four real usage series',document.querySelectorAll('#hardware-scroll>g').length===4);
hardwareInspect(400);check('shared tooltip includes every series',['CPU','GPU','RAM','VRAM'].every(x=>$('hardware-tooltip').textContent.includes(x)));
$('hardware-legend').querySelector('[data-hardware="gpu"]').click();check('chip isolates GPU',hardwareGraph.selected==='gpu'&&document.querySelectorAll('#hardware-scroll>.hardware-muted').length===3);
$('hardware-legend').querySelector('[data-hardware="gpu"]').click();check('repeat chip restores all',hardwareGraph.selected===null);
$('hardware-chart').querySelector('[data-hardware-line="ram"]').dispatchEvent(new MouseEvent('click',{bubbles:true}));check('line isolates RAM',hardwareGraph.selected==='ram');
$('hardware-chart').querySelector('[data-hardware-line="ram"]').dispatchEvent(new MouseEvent('click',{bubbles:true}));check('repeat line restores all',hardwareGraph.selected===null);hardwareSelect('cpu');
$('hardware-all').click();check('All restores every series',hardwareGraph.selected===null&&!document.querySelector('#hardware-scroll>.hardware-muted'));
$('hardware-plot').dispatchEvent(new KeyboardEvent('keydown',{key:'Home',bubbles:true}));check('keyboard inspects first sample',hardwareGraph.cursor===0&&$('hardware-tooltip').textContent.includes('118s'));
$('hardware-plot').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));check('Escape clears crosshair',$('hardware-tooltip').hidden);
const focusedChip=$('hardware-legend').firstElementChild;focusedChip.focus();
hardwareUpdate({at:102,history,gpu:{temperature:57},temps:{parts:[{part:'system',known:false}]}});check('polling preserves legend focus',document.activeElement===focusedChip);check('new sample starts translation',hardwareGraph.offset>0);check('scroll retains point leaving the left edge',hardwareGraph.data.cpu.length===61);check('fills allow line hit testing',getComputedStyle(document.querySelector('.hardware-area')).pointerEvents==='none');hardwareFrame(hardwareGraph.started+1000);check('linear half-step scroll',Math.abs(hardwareGraph.offset-300/59)<.01);hardwareFrame(hardwareGraph.started+2000);check('scroll ends without path rebuild',hardwareGraph.offset===0);
$('hardware-temperature').click();check('temperature toggle uses Celsius scale',$('hardware-axis').textContent.includes('120°C')&&hardwareGraph.mode==='temperature');hardwareInspect(600);check('unknown temperature is not zero',$('hardware-tooltip').textContent.includes('System—'));
$('hardware-temperature').click();hardwareClearCursor();
const cpu=history.cpu;history.cpu=[10,null,40];hardwareUpdate({at:104,history,gpu:{}});check('missing samples split geometry',$('hardware-chart').querySelector('[data-hardware="cpu"] .hardware-line').getAttribute('d').split('M').length===3);history.cpu=cpu;
hardwareUpdate({at:106,history,gpu:{temperature:57}});hardwarePause();homeMotion.reduced=userMotion;
check('mode cards have no performance promises',!document.querySelector('[data-mode-fps]')&&!$('intents').textContent.includes('EST. FPS'));
$('history-stats').innerHTML='<div class="stat"><b>16</b><span>sessions</span></div><div class="stat"><b>5.5</b><span>hours played</span></div><div class="stat"><b>7.41s</b><span>alt-tab back</span></div>';
renderHardware({cpu:{name:'Intel Core i9-12900K',cores:16,threads:24},gpu:{name:'NVIDIA GeForce RTX 3090 Ti',vram_gb:24,driver:'621.01'},ram_gb:32,ram_speed:6000,displays:[{width:2560,height:1440,refresh:240,primary:true,confident:true}],power_plan:'Balanced'});
$('assessment-out').innerHTML='<div class="assess">Selected settings ? Competitive</div>';
homeFrame(performance.now()+2200);check('gauge reaches its target',node.querySelector('.val').textContent==='80');check('smooth combined area chart',$('hardware-chart').querySelector('.hardware-line').getAttribute('d').includes(' C'));
const errors=[...document.images].filter(i=>i.getAttribute('src')&&(!i.complete||!i.naturalWidth));check('all home image assets load',errors.length===0);
check('no horizontal overflow',document.documentElement.scrollWidth<=innerWidth);
const media=homeMotion.reduced;homeMotion.reduced={matches:true};homeNumber(node.querySelector('.val'),31);check('reduced motion sets final reading immediately',node.querySelector('.val').textContent==='31');homeMotion.reduced=media;
const panel=document.querySelector('[data-panel="launcher"]');panel.classList.add('hidden');homePause();hardwarePause();check('hidden graph stops frames',!hardwareGraph.raf);check('hidden Launcher pauses animation scheduler',!homeMotion.raf && document.documentElement.classList.contains('home-paused'));panel.classList.remove('hidden');homePause();
for(const theme of ${JSON.stringify(themes)}){if(theme==='violet')delete document.documentElement.dataset.theme;else document.documentElement.dataset.theme=theme;check('theme '+theme+' keeps controls visible',getComputedStyle($('play')).display!=='none' && getComputedStyle(node.querySelector('.val')).fill!=='none');const tones=[...document.querySelectorAll('.hardware-line')].map(el=>getComputedStyle(el).stroke);check('theme '+theme+' keeps chart series distinct',new Set(tones).size===4&&!tones.includes('none'));}delete document.documentElement.dataset.theme;
const wasReduced=homeMotion.reduced;homeMotion.reduced={matches:true};hardwareUpdate({at:108,history,gpu:{}});check('reduced motion skips chart scrolling',hardwareGraph.offset===0&&!hardwareGraph.raf);homeMotion.reduced=wasReduced;
const lineX=key=>{const n=$('hardware-chart').querySelector('[data-hardware="'+key+'"] .hardware-line').getAttribute('d').replace(/[MC]/g,' ').split(' ').filter(Boolean).map(Number);return [n[0],n.at(-2)]};
hardwareUpdate({at:110,history:{cpu:[30],gpu:[40],ram:[50],vram:[20]},gpu:{}});check('first reading already spans the graph',JSON.stringify(lineX('cpu'))==='[0,600]');
hardwareUpdate({at:112,history:{cpu:[30,35,32],gpu:[40,44,41],ram:[50,50,51],vram:[20,21,22]},gpu:{}});check('short history spreads across the full width',JSON.stringify(lineX('gpu'))==='[0,600]'&&hardwareGraph.offset===0&&!hardwareGraph.raf);
hardwareInspect(0);check('spread history keeps real sample ages',$('hardware-tooltip').textContent.includes('~4s ago'));hardwareClearCursor();
const tempHistory={...history,'temp-cpu':history.cpu.map(v=>v+30),'temp-gpu':history.gpu.map(v=>v+5),'temp-system':history.ram.map(()=>36)};
hardwareUpdate({at:114,history:tempHistory,gpu:{temperature:60},temps:{parts:[{part:'cpu',known:true,celsius:60}]}});check('temperatures use the app history',hardwareGraph.temperatures['temp-cpu'].length===60);
hardwareUpdate({at:116,history:tempHistory,gpu:{temperature:60}});hardwarePause();

check('hardware and settings glyphs are distinct', Object.keys(HW_ART).length>=16&&new Set(Object.values(HW_ART)).size===Object.keys(HW_ART).length);
const specimen=document.createElement('div');specimen.innerHTML=Object.keys(HW_ART).map(k=>hwIcon(k)).join('');document.body.append(specimen);
if(matchMedia('(prefers-reduced-motion: reduce)').matches)check('reduced motion disables hardware animation',getComputedStyle(specimen.querySelector('svg')).animationName==='none');
check('every glyph has tooltip and accessible name',[...specimen.children].every(el=>el.title&&el.getAttribute('aria-label')&&el.querySelector('svg')));
check('glyphs inherit theme tokens',[...specimen.children].every(el=>getComputedStyle(el).color===getComputedStyle(node.querySelector('.hw-icon')).color));
check('icon labels escape HTML',hwIcon('cpu','<unsafe>"').includes('&lt;unsafe&gt;&quot;'));
Object.defineProperty(document,'hidden',{configurable:true,value:true});hwPauseMotion();check('background app pauses icon motion',(getComputedStyle(specimen.querySelector('svg')).animationPlayState==='paused'||getComputedStyle(specimen.querySelector('svg')).animationName==='none'));delete document.hidden;hwPauseMotion();
specimen.classList.add('hidden');check('hidden content pauses icon motion',(getComputedStyle(specimen.querySelector('svg')).animationPlayState==='paused'||getComputedStyle(specimen.querySelector('svg')).animationName==='none'));specimen.remove();
check('gauge labels use family',document.querySelectorAll('#live-gauges .cap [data-hw]').length===4);
check('legend uses family',document.querySelectorAll('#hardware-legend [data-hw]').length===4);
check('detected hardware uses icons',document.querySelectorAll('#hw [data-hw]').length===5);
syncChips();check('topbar still mirrors readings after replacing labels',$('chip-cpu').querySelector('b').textContent==='31%'&&$('chip-gpu').querySelector('b').textContent==='42%');
const beforeThermal=$('live-temps').firstElementChild;
renderTemps({parts:[{part:'gpu',label:'GPU',known:true,celsius:92,state:'hot',floor:30,hot:90},{part:'board',label:'System',known:false,unavailable:'needs administrator'}],can_elevate:true});
check('thermal nodes persist',beforeThermal===$('live-temps').firstElementChild);
check('hot sensor uses semantic state',beforeThermal.classList.contains('hot')&&beforeThermal.getAttribute('aria-label').includes('92'));
check('unknown value stays a dash',$('live-temps').lastElementChild.querySelector('.t-read').textContent==='\u2014');
check('unknown reason stays outside value',$('live-temps').lastElementChild.querySelector('.t-reason').textContent==='needs administrator');
renderTemps({parts:[{part:'gpu',label:'GPU',known:true,celsius:56,state:'fine'},{part:'board',label:'System',known:false,unavailable:'needs administrator'}],can_elevate:true});
wgData={supported:true,high_performance:false,windowed_optimised:false,parts:{cpu:{name:'Intel Core i9-12900K',detail:'16 cores / 24 threads',ceiling:500},gpu:{name:'NVIDIA GeForce RTX 3090 Ti',detail:'24 GB VRAM',ceiling:450}}};renderMachine();
check('Machine shares CPU and GPU family',!!$('machine-out').querySelector('[data-hw="cpu"]')&&!!$('machine-out').querySelector('[data-hw="gpu"]'));
audioData={output:[{id:'out',name:'Headset'}],input:[{id:'in',name:'Microphone'}],pinned_output:'out',pinned_input:'in'};renderAudio();
check('sound selects retain their selected devices',$('audio-output').value==='out'&&$('audio-input').value==='in');
check('sound icon labels remain associated with selects',!!document.querySelector('label[for="audio-output"] [data-hw="headset"]')&&!!document.querySelector('label[for="audio-input"] [data-hw="mic"]'));
check('Machine controls preserved',$('machine-out').querySelectorAll('[data-bias]').length===3&&!!$('wg-apply')&&!!$('wg-auto'));
const thumb=$('machine-out').querySelector('.bias-thumb');
for(const [id,index] of [['gpu',1],['cpu',2],['auto',0]]){const pick=$('machine-out').querySelector('[data-bias="'+id+'"]');pick.click();await Promise.resolve();check('bias '+id+' saves and slides',prefsNow.load_bias===id&&thumb===$('machine-out').querySelector('.bias-thumb')&&thumb.parentElement.style.getPropertyValue('--bias-index')===String(index)&&pick.getAttribute('aria-pressed')==='true');check('bias '+id+' tooltip explains choice',pick.title.length>20);}
if(matchMedia('(prefers-reduced-motion: reduce)').matches)check('reduced motion disables bias slide',getComputedStyle(thumb).transitionDuration==='0s');

check('Detected moved exclusively into This PC',!!$('hw-card').closest('[data-sub="this-pc"]')&&!document.querySelector('[data-panel="launcher"] #hw-card'));
check('connection card removed from Play',!document.querySelector('[data-panel="launcher"] #net-card'));
setSettingsSub('this-pc',true);check('This PC navigation reveals hardware',!$('hw-card').closest('.subpane').classList.contains('hidden')&&document.querySelector('[data-sub="this-pc"][role="tab"]').getAttribute('aria-selected')==='true');setSettingsSub('nvidia',true);
const probe={label:'The internet',host:'1.1.1.1',sent:20,received:20,reachable:true,average:18,jitter:2,loss:0,times:[17,18,19],misses:[]};
const measured={done:true,running:false,adapter:{name:'Ethernet',speed:'1 Gbps',wireless:false},download:{mbps:245.3,bytes:25000000,seconds:.815,error:''},internet:probe,gateway:{...probe,label:'Your router',host:'192.168.1.1',average:1},findings:[{severity:'good',title:'Steady connection',detail:'No packets lost.'}]};
let calls=[];netApi=async route=>{calls.push(route);return route.endsWith('/start')?{...measured,done:false,running:true}:measured};
const job=runNetCheck();check('duplicate tests share one job',job===runNetCheck());check('re-test disabled while measuring',$('net-run').disabled);await job;
check('startup job waits for polling result',calls.join(',')==='/api/net/start,/api/net'&&netData.done&&netJob===null);
check('speed and ping chip uses actual download result',$('net-summary').textContent==='245.3 Mbps · 18 ms'&&$('chip-net').title.includes('Download: 245.3 Mbps'));
check('adapter has whitespace before wired',$('net-out').textContent.includes('1 Gbps wired'));
check('router dial uses same average as stats',$('net-out').querySelector('.pingdial-num').textContent==='1');
check('details retain diagnostics',['Your router','The internet','jitter','% loss','Steady connection','Link speed','Download: 245.3 Mbps','25 MB'].every(t=>$('net-out').textContent.includes(t)));
$('chip-net').click();check('chip opens details',$('chip-net').getAttribute('aria-expanded')==='true'&&!$('net-card').hidden);
const popup=$('net-card').getBoundingClientRect();check('details fit viewport',popup.left>=0&&popup.right<=innerWidth&&popup.bottom<=innerHeight);
check('details are painted above content',popup.width>300&&popup.height>100&&!!document.elementFromPoint(popup.left+30,popup.top+30)?.closest('#net-card'));
document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));check('Escape closes and restores focus',$('net-card').hidden&&document.activeElement===$('chip-net'));
$('chip-net').click();$('live-card').click();check('outside click closes details',$('net-card').hidden);
netApi=async()=>{throw new Error('<offline>')};await runNetCheck();check('failed start settles and permits retry',!$('net-run').disabled&&netJob===null&&$('net-summary').textContent==='Unavailable'&&$('net-out').textContent==='<offline>'&&!$('net-out').querySelector('offline'));
netApi=async route=>{if(route.endsWith('/start'))return {...measured,running:true,done:false};throw new Error('Poll failed')};await runNetCheck();check('failed polling settles and permits retry',netJob===null&&!$('net-run').disabled&&$('net-out').textContent==='Poll failed');
netApi=()=>new Promise(()=>{});await runNetCheck();check('hung request times out and releases startup',netJob===null&&!$('net-run').disabled&&$('net-out').textContent.includes('timed out'));
renderNet({done:true,internet:{reachable:false},adapter:null});check('offline readings are unknown not zero',$('net-summary').textContent==='— · — ms');
renderNet({...measured,download:{mbps:null,error:'offline'}});check('download failure preserves ping without substituting link speed',$('net-summary').textContent==='— · 18 ms'&&$('net-out').textContent.includes('Download unavailable')&&$('net-out').textContent.includes('1 Gbps'));
renderNet({...measured,download:{mbps:0.24,error:''}});check('slow download retains precision',$('net-summary').textContent==='0.24 Mbps · 18 ms');
renderNet({...measured,download:{mbps:Infinity,error:''}});check('invalid download is unknown',$('net-summary').textContent==='— · 18 ms');
netApi=async()=>measured;await runNetCheck();check('re-test recovers after failure',$('net-summary').textContent==='245.3 Mbps · 18 ms'&&!$('net-run').disabled);
for(const theme of ${JSON.stringify(themes)}){document.documentElement.dataset.theme=theme;$('chip-net').click();check('connection works in theme '+theme,getComputedStyle($('net-card')).display!=='none'&&getComputedStyle($('chip-net')).color!=='transparent');closeNetDetails()}delete document.documentElement.dataset.theme;
const receipt={total:9,verified:9,account:'42',intent:'balanced',items:[]};
await refreshVerification();check('read-back waits for gated startup',!verificationStarted&&!verificationBusy);
renderVerification(receipt);
check('a valid receipt updates the existing profile status without a Launcher banner',verificationState==='verified'&&!$('verification')&&!panel.querySelector('.verification'));
renderVerification({...receipt,verified:8});check('a partial receipt prompts review',verificationState==='failed');
verificationDirty=true;renderVerification(receipt);check('pending edits invalidate saved verification',verificationState==='changed');verificationDirty=false;
renderVerification({...receipt,selection:{intent:'quality'}});check('a different selected profile invalidates saved verification',verificationState==='changed');
const readApi=api;
api=async()=>{throw Error('offline')};await refreshVerification();check('read failure clears verified status',verificationState==='unknown');
api=()=>new Promise(()=>{});await refreshVerification();check('hung read-back releases the refresh guard',!verificationBusy&&verificationState==='unknown');
api=async()=>receipt;await refreshVerification();check('a successful refresh restores verified status',verificationState==='verified');
api=readApi;
renderPlan({intent:'balanced',tier:'S',headroom:5.7,estimated_fps:342,settings:[{name:'GPU level',after:'High',changed:true,reason:'Tier S headroom'}],launch_current:'',launch_new:'',launch_added:[],launch_removed:[],advisories:[{title:'Estimated 342 fps',detail:'Tier S',level:'warn'}],changed_count:1});
check('plan keeps picture guidance without estimates',!/(342|headroom|Tier S)/.test($('assessment-out').textContent)&&fpsEffect.includes('High')&&$('assessment-out').textContent.includes('1 picture settings reviewed'));
check('Machine has no estimated FPS',!$('machine-out').textContent.includes('FPS')&&!$('machine-out').querySelector('.part-vs'));
check('launch controls moved once',['w-launch','steam-launch-out','who','who-menu'].every(id=>document.querySelectorAll('#'+id).length===1&&!!$(id).closest('[data-sub="steam"]')));
check('Steam contains the only account pane and Steam login control',['account-card','account-out','steam-connect'].every(id=>document.querySelectorAll('#'+id).length===1&&!!$(id).closest('.subpane[data-sub="steam"]'))&&!document.querySelector('#settings-subtabs [data-sub="account"]'));
dockSteam={available:true,linked:false,state:'idle',connection:{connected:false}};
renderAccountsDock();
check('dock links to Steam settings and only the pane has Connect',
  !$('steam-connect').hidden&&$('dock-steam').textContent.includes('Manage')&&!$('dock-steam').querySelector('[data-sign-in]'));
const oldSteamApi=api;
api=async route=>route==='/api/stats/steam'?{available:true,linked:false,state:'idle',connection:{connected:false}}:oldSteamApi(route,{});
$('dock-steam').click();
check('dock Steam row opens the shared pane',activeTab==='settings'&&settingsSub==='steam');
check('setup return stays hidden during ordinary use',getComputedStyle($('setup-steam-return')).display==='none');
await loadDockSteam();
clearTimeout(dockSteamTimer);
api=oldSteamApi;
setTab('launcher');
check('Steam preview follows mode switches',$('steam-launch-out').textContent.includes('After the next mode switch'));
check('advisories do not become performance promises',!$('assessment-out').textContent.includes('Estimated'));
setSettingsSub('account',true);check('old Account preference opens Steam',settingsSub==='steam'&&!$('account-card').closest('.subpane').classList.contains('hidden')&&document.querySelector('#settings-subtabs [data-sub="steam"]').getAttribute('aria-selected')==='true');setSettingsSub('nvidia',true);
const settingsPanel=document.querySelector('[data-panel="settings"]');panel.classList.add('hidden');settingsPanel.classList.remove('hidden');
for(const name of ['nvidia','this-pc','lighting','mouse','steam','apps','look','sound','overlay','maps','config','editing','logs','tools']){setSettingsSub(name,true);const pane=settingsPanel.querySelector('.subpane[data-sub="'+name+'"]');check('shared grid '+name,getComputedStyle(pane).gap==='16px'&&getComputedStyle(pane).display==='grid');}
setSettingsSub('nvidia',true);check('NVIDIA workspace replaces old Apply layout',!!settingsPanel.querySelector('.subpane[data-sub="nvidia"]')&&!settingsPanel.querySelector('.subpane[data-sub="apply"]'));
settingsPanel.classList.add('hidden');panel.classList.remove('hidden');
const sample={intent:'balanced',settings:[{name:'Texture quality',before:'Low',after:'High',changed:true},{name:'Shadows',before:'Off',after:'On',changed:true},{name:'GPU level',before:'Quality',after:'Quality',before_raw:1,after_raw:3,same_label:true,changed:true}]};
for(const mode of INTENTS){presetBegin(mode);presetReveal({...sample,intent:mode});check(mode+' uses real preview values',document.querySelector('.preset-row').textContent.includes('Low → High'));check(mode+' dims behind selected card',!!document.querySelector('.preset-veil')&&presetSession.card.dataset.intent===mode);if(!matchMedia('(prefers-reduced-motion: reduce)').matches){check(mode+' reveals sequentially',document.querySelectorAll('.preset-row').length===1);await new Promise(r=>setTimeout(r,780));}check(mode+' displays every changed value',document.querySelectorAll('.preset-row').length===3&&document.querySelector('.preset-rows').textContent.includes('Quality (1) → Quality (3)'));presetClose();}
presetBegin('quality');presetReveal(sample);check('stale preset response ignored',!document.querySelector('.preset-row'));presetReveal({...sample,intent:'quality',settings:[]});check('unchanged preset honest',document.querySelector('.preset-rows').textContent==='Everything already matches.');document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));check('Escape clears dimming',!presetSession&&!document.querySelector('.preset-veil'));
presetBegin('balanced');Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));check('background cancels reveal and timer',!presetSession&&!document.querySelector('.preset-veil'));delete document.hidden;
presetBegin('balanced');panel.classList.add('hidden');await Promise.resolve();check('leaving Play cancels reveal',!presetSession);panel.classList.remove('hidden');
const oldApi=api;const queue=[];api=(route,body)=>new Promise((resolve,reject)=>queue.push({route,body,resolve,reject}));
const planFor=name=>({...sample,intent:name,launch_current:'-old',launch_new:'-new',launch_removed:[],launch_added:[],changed_count:3});
intent='competitive';const first=previewPlan();intent='quality';const second=previewPlan();queue[1].resolve(planFor('quality'));await second;queue[0].resolve(planFor('competitive'));await first;check('late plan cannot overwrite latest selection',planned.intent==='quality'&&$('assessment-out').textContent.includes('quality'));
check('Steam launch options use latest same plan',$('steam-launch-out').textContent.includes('-new')&&!$('assessment-out').textContent.includes('-new'));
presetBegin('quality');const failed=previewPlan();queue[2].reject(Error('Offline'));await failed;check('plan failure releases dimmer and preview button',!presetSession&&!$('steam-preview').disabled);
api=oldApi;intent='balanced';paintIntent(intent);renderPlan(planFor('balanced'));
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const selectedCard=$('intents').querySelector('[aria-pressed="true"]');
api=async route=>route==='/api/apply'?{
  ok:true,verification:receipt,video:[{name:'Ambient Occlusion',before:'High',after:'Low'}],
  nvidia:{ok:true,changed:[{name:'Texture filtering',before:'Quality',after:'Performance'}]},
  steps:[{what:'Steam launch options',skipped:true,ok:false}],
}:planFor(intent);
const applying=applyProfileForCheck('mode');
const feed=selectedCard.querySelector('.profile-apply');
check('apply starts inside the selected profile card',!!feed&&feed.textContent.includes('Applying')&&!document.querySelector('.apply-feed,.preset-veil'));
await applying;
check('first change shows former and new values',feed.querySelectorAll('.profile-apply-line').length===1&&feed.textContent.includes('High → Low'));
const cardRect=selectedCard.getBoundingClientRect(),feedRect=feed.getBoundingClientRect();
check('apply animation stays within the profile card',feedRect.left>cardRect.left&&feedRect.right<=cardRect.right&&feedRect.top>=cardRect.top&&feedRect.bottom<=cardRect.bottom);
check('apply feed has a transparent background',getComputedStyle(feed).backgroundColor==='rgba(0, 0, 0, 0)'&&getComputedStyle(feed).backgroundImage==='none');
const cards=$('intents');cards.style.maxWidth='520px';
const narrowCard=selectedCard.getBoundingClientRect(),narrowFeed=feed.getBoundingClientRect();
const narrowTitle=selectedCard.querySelector('.mode-copy').getBoundingClientRect();
check('compact cards keep the change feed above the profile title',narrowFeed.width>100&&narrowFeed.left>=narrowCard.left&&narrowFeed.right<=narrowCard.right&&narrowFeed.bottom<narrowTitle.top);
cards.style.removeProperty('max-width');
if(matchMedia('(prefers-reduced-motion: reduce)').matches)check('reduced motion keeps rows static',getComputedStyle(feed.querySelector('.profile-apply-line')).animationName==='none');
await sleep(650);
check('the next setting appears in sequence',feed.querySelectorAll('.profile-apply-line').length===2&&feed.textContent.includes('Texture filtering'));
await sleep(1200);
check('skipped settings are announced separately',feed.dataset.phase==='warn'&&feed.textContent.includes('Close Steam')&&$('profile-apply-live').textContent.includes('2 updated · 1 to review'));
const beforeRetry=previews;selectedCard.click();check('clicking the card with a warning retries the same profile',previews===beforeRetry+1);
api=async route=>route==='/api/apply'?{ok:false,error:'Access denied'}:planFor(intent);
intent='quality';paintIntent(intent);await applyProfileForCheck('mode');
check('switching cards cancels the previous feed and reports failure on the new card',!feed.isConnected&&$('intents').querySelector('[data-intent="quality"] .profile-apply').textContent.includes('Access denied'));
api=oldApi;intent='balanced';paintIntent(intent);
for(const theme of ${JSON.stringify(themes)}){document.documentElement.dataset.theme=theme;presetBegin('balanced');presetReveal(sample);const row=document.querySelector('.preset-row');check('preset readable in '+theme,getComputedStyle(row).color!==getComputedStyle(document.querySelector('.preset-changes')).backgroundColor);check('dimmer cuts window through selected card in '+theme,document.querySelector('.preset-veil').style.clipPath.includes('evenodd'));presetClose();}delete document.documentElement.dataset.theme;
$('status').remove();document.querySelector('.scroll').scrollTop=0;
if(location.hash.includes('this-pc')){document.querySelector('[data-panel="launcher"]').classList.add('hidden');document.querySelector('[data-panel="settings"]').classList.remove('hidden');setSettingsSub('this-pc',true)}
if(location.hash.includes('settings-apply')){document.querySelector('[data-panel="launcher"]').classList.add('hidden');document.querySelector('[data-panel="settings"]').classList.remove('hidden');setSettingsSub('nvidia',true)}
if(location.hash.includes('settings-steam')){panel.classList.add('hidden');settingsPanel.classList.remove('hidden');setSettingsSub('steam',true);$('who-name').textContent='Edy';$('who-how').textContent='Following Steam';$('net-summary').textContent='Not tested';whoData={accounts:[{active:true,name:'Edy'}]};dockSteam={available:true,linked:false,state:'idle',connection:{connected:false}};cloudData={configured:true,signed_in:false,google:true};renderCloud();}
if(location.hash.includes('settings-account')){panel.classList.add('hidden');settingsPanel.classList.remove('hidden');setSettingsSub('account',true);cloudData={configured:true,signed_in:false,google:true};renderCloud();}
if(location.hash.includes('preset')){presetBegin('balanced');presetReveal(sample);await new Promise(r=>setTimeout(r,780));clearTimeout(presetSession.timer);$('intents').scrollIntoView({block:'center'});}
if(location.hash.includes('profile-apply')){profileApplyFeed.start('balanced','Balanced');profileApplyFeed.play({video:[{name:'Ambient Occlusion',before:'High',after:'Low'},{name:'Texture filtering',before:'Quality',after:'Performance'}],steps:[{what:'Steam launch options',ok:false,skipped:true}]},'Balanced');await sleep(1750);$('intents').scrollIntoView({block:'center'});}
if(location.hash.includes('connection-offline'))renderNet({...measured,download:{mbps:null,error:'offline'}});
if(location.hash.includes('connection'))$('chip-net').click();
if(location.hash.includes('cold')){hardwareGraph.at=null;hardwareGraph.data={};hardwareUpdate({at:200,history:{cpu:[22,31,27],gpu:[48,55,51],ram:[52,52,53],vram:[18,19,19]},gpu:{}});hardwarePause();$('live-card').scrollIntoView({block:'start'})}
if(location.hash.includes('system')){$('live-card').scrollIntoView({block:'start'});hardwareInspect(400)}
if(location.hash.includes('sound')){const card=$('audio-card');document.querySelector('.scroll').replaceChildren(card);card.scrollIntoView()}
if(location.hash.includes('machine')){const card=$('machine-card'),frame=document.createElement('div');frame.className='settings-box';frame.append(card);document.querySelector('.scroll').replaceChildren(frame);card.scrollIntoView()}
if(location.hash.includes('family')){const thermal=$('live-temps').cloneNode(true);thermal.style.cssText='display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:28px;margin:28px;';document.querySelector('.scroll').innerHTML='<section class="panel"><h2>Hardware family</h2><div style="display:grid;grid-template-columns:repeat(4,1fr);gap:32px;padding:28px">'+Object.keys(HW_ART).map(k=>'<div style="display:flex;align-items:center;gap:18px">'+hwIcon(k)+'<span>'+HW_NAMES[k]+'</span></div>').join('')+'</div></section>';const frame=document.createElement('div');frame.dataset.panel='launcher';frame.append(thermal);document.querySelector('.scroll').firstElementChild.append(frame)}
if(location.hash.includes('paper'))document.documentElement.dataset.theme='paper';
if(location.hash.includes('solo'))hardwareSelect('gpu');
if(!settingsPanel.classList.contains('hidden'))document.querySelectorAll('.tabs .tab').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.tab==='settings')));

}catch(e){checks.push({error:e.stack})}const freeze=document.createElement('style');freeze.textContent='*,*::before,*::after{transition:none!important;animation:none!important}';document.head.append(freeze);document.body.insertAdjacentHTML('beforeend','<pre id="checks" hidden>'+JSON.stringify(checks)+'</pre>')})();`;
let html=s.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'');html=html.replace('<head>','<head><base href="'+url.pathToFileURL(path.join(root,'cs2cfg/web/')).href+'">');html=html.replace('</body>',()=>'<script>window.addEventListener("error",e=>{const p=document.createElement("pre");p.id="checks";p.textContent=JSON.stringify([{error:e.error?.stack||e.message}]);document.body.append(p)});</script><script>'+code+'</script></body>');
new (require('vm').Script)(code);fs.writeFileSync(path.join(work,'preview.html'),html);
const chrome=process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';const args=['--headless','--no-sandbox','--disable-gpu','--allow-file-access-from-files','--user-data-dir='+path.join(work,'chrome'),'--window-size='+(process.env.HOME_VIEWPORT||'1440,1100'),'--virtual-time-budget=30000',url.pathToFileURL(path.join(work,'preview.html')).href+(process.env.HOME_HASH||'')];
if(process.env.HOME_REDUCED)args.unshift('--force-prefers-reduced-motion');
const out=cp.execFileSync(chrome,[...args,'--dump-dom','--screenshot='+(process.env.HOME_SCREENSHOT||path.join(work,'preview.png'))],{maxBuffer:4e6,stdio:['ignore','pipe','ignore']}).toString();fs.writeFileSync(path.join(work,'dom.html'),out);const result=out.match(/<pre id="checks"(?:\s[^>]*)?>(\[[\s\S]*?\])<\/pre>/)?.[1];console.log(result??'NO TEST RESULTS. Last check: '+(out.match(/data-last-check="([^"]+)"/)?.[1]??'unavailable'));assert(result&& !result.includes('false')&&!result.includes('"error"'));
console.log('Browser checks: '+JSON.parse(result).length+' passed');
