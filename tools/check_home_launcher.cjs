const fs=require('fs'),cp=require('child_process'),assert=require('assert');
const path=require('path'),url=require('url');
const root=path.resolve(__dirname,'..');process.chdir(root);
const work=path.join(require('os').tmpdir(),'cs-config-home-'+require('crypto').createHash('sha1').update(root).digest('hex').slice(0,8));fs.mkdirSync(work,{recursive:true});
const s=fs.readFileSync('cs2cfg/web/index.html','utf8').replace(/\r\n/g,'\n');
for(const x of s.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))new (require('vm').Script)(x[1]);
const themes=require('vm').runInNewContext(s.slice(s.indexOf('const THEMES = [')+'const THEMES = '.length,s.indexOf('function applyTheme(')).trim().replace(/;$/, '')).map(t=>t[0]);
const slice=(a,b)=>s.slice(s.indexOf(a),s.indexOf(b,s.indexOf(a)));
let code=fs.readFileSync(path.join(root,'cs2cfg/web/assets/hardware/icons.js'),'utf8')+'\n'+fs.readFileSync(path.join(root,'cs2cfg/web/assets/fixit/icons.js'),'utf8')+'\n'+`const $=id=>document.getElementById(id); const esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');let intent='balanced',planned={},prefs=0,previews=0;const INTENTS=['competitive','balanced','quality'];function paintModeBadge(){} function rememberPrefs(){prefs++} function noteChange(){} function requestBody(){return {intent,target_fps:240}};let netApi;async function api(url,b){if(url.startsWith("/api/net"))return netApi(url,b);return {intent:b.intent,estimated_fps:{competitive:410,balanced:340,quality:230}[b.intent]}};const tempAlarm={};function status(){};`;
code+=slice("function renderHardware(d) {","/* The machine's scores,");
code+=`let prefsNow={},audioData=null;`;
code+=slice('function audioOptions(list, pinned)', 'async function saveAudio');
code+=slice('let wgData = null;','/* What the launch did about the crosshair.');
code+=slice('const CHIPS = { CPU:', '// -- 2. the gradient');
code+=slice('/* Launcher motion:','function renderPlan(');
code+=`const verificationNavigation=[];function setTab(name){verificationNavigation.push(name);document.querySelectorAll('.tab-panel').forEach(panel=>panel.classList.toggle('hidden',panel.dataset.panel!==name))};`;
code+=slice('/* Every card uses','$("preview").addEventListener("click", previewPlan);');
code+='function busy(){};';
code+=`let fpsEffect='';function renderFps(){}function markPending(){};`;
code+=slice('function renderPlan(', '// The last detection,');
code+=slice('let netTimer = null;', '/* Three scene cards');
code+=`const prefsReady=false,startup={finished:false};function moveSegThumb(){};`;
code+=slice('let settingsSub = "apply";', '/* ---------------------------------------------------------------------------\n   Sound devices');
code+='let cloudData=null;';
code+=slice('const WAY_ICONS = {', 'async function loadCloud()');
code+=slice('function cloudWay(', 'function showPasswordForm(');
code+=slice('function ring(value','function meter(');
code+=slice('/* Administrator helper status','/* ------');
code+=slice('// Horizontal thermal strips','// --- live system readout');
code+=`document.documentElement.dataset.boot='ready';document.querySelector('.boot-screen').remove();$('preview').addEventListener('click',()=>previews++);
const checks=[];function check(name,ok){checks.push({name,ok});if(!ok)throw Error(name)}
(async()=>{try{
check('hero controls remain inside hero', $('home-hero').contains($('play')) && $('home-hero').contains($('launch-modes')));
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

check('all sixteen hardware glyphs are distinct', Object.keys(HW_ART).length===16&&new Set(Object.values(HW_ART)).size===16);
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
setSettingsSub('this-pc',true);check('This PC navigation reveals hardware',!$('hw-card').closest('.subpane').classList.contains('hidden')&&document.querySelector('[data-sub="this-pc"][role="tab"]').getAttribute('aria-selected')==='true');setSettingsSub('apply',true);
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
const receipt={total:9,verified:9,checked_at:1794739320,applied_at:1794739300,account:'42',intent:'balanced',items:['CS2 video settings','Config files','Autoexec link','Steam launch options','Launch options reference','Display scaling'].map(label=>({label,status:'verified',detail:'Matches the applied value',counted:true})).concat(['NVIDIA profile','Windows power','Windows graphics'].map(label=>({label,status:'verified',detail:'Matches the recommended settings',counted:true})))};
const noNvidia={...receipt,total:8,verified:8,items:receipt.items.map(item=>item.label==='NVIDIA profile'?{...item,status:'not_applicable',counted:false,detail:'No NVIDIA GPU/driver. Excluded from the count.'}:item)};
await refreshVerification();check('read-back waits for gated startup',!verificationStarted&&!verificationBusy);
renderVerification({total:0,items:[]});check('no receipt never claims success',$('verification').hidden);
renderVerification(receipt,true);check('badge uses verified count and time',$('verification-title').textContent==='Your PC is set: 9/9 verified'&&$('verification-time').textContent.startsWith('Checked'));
$('results').insertAdjacentHTML('afterbegin','<section id="apply-verification" class="verification reveal"></section>');renderApplyVerification();
check('Apply results show the same read-back checklist',$('apply-verification').querySelectorAll('.verify-row').length===9&&$('apply-verification').textContent.includes('9/9 verified'));
check('apply reveals accessible checklist',$('verification').open&&$('verification-list').children.length===9&&$('verification-title').getAttribute('role')==='status');
check('all three system settings count as verified',$('verification-list').querySelectorAll('[data-state="verified"][data-counted="true"]').length===9);
$('verification').scrollIntoView({block:'start'});
check('expanded checklist shows all nine rows without internal scrolling',$('verification-list').scrollHeight<=$('verification-list').clientHeight);
renderVerification(noNvidia,true);
check('non NVIDIA case counts eight of eight',$('verification-title').textContent==='Your PC is set: 8/8 verified'&&$('verification-list').children.length===9);
check('not applicable is visibly excluded',$('verification-list').querySelector('[data-state="not_applicable"][data-counted="false"]').textContent.includes('Not applicable'));
check('Apply shares the non NVIDIA denominator',$('apply-verification').textContent.includes('8/8 verified')&&$('apply-verification').querySelectorAll('[data-counted="true"]').length===8);
const unset={...receipt,verified:6,items:receipt.items.map((item,i)=>i<6?item:{...item,status:'not_set',action:['nvidia','power','wingraphics'][i-6],detail:['In NVIDIA Control Panel > Manage 3D settings > Program Settings > cs2.exe: Prefer maximum performance; Vertical sync: application-controlled or Off.','Choose Ultimate Performance in Fix It (High performance is also accepted).','Use Set for performance in Settings > Apply > Machine.'][i-6]})};
renderVerification(unset,true);
check('never applied recommendations are amber Not set',$('verification').dataset.state==='changed'&&$('verification-title').textContent==='Review settings: 6/9 verified'&&$('verification-list').querySelectorAll('[data-state="not_set"]').length===3&&$('verification-list').textContent.includes('Not set'));
check('both checklists offer existing controls',$('verification-list').querySelectorAll('[data-verify-action]').length===3&&$('apply-verification').querySelectorAll('[data-verify-action]').length===3);
const actionApi=api,actionRequests=[];api=async(...args)=>{actionRequests.push(args);return {}};
for(const action of ['nvidia','power','wingraphics'])$('verification-list').querySelector('[data-verify-action="'+action+'"]').click();
check('review actions navigate to Graphics Fix It and Machine',verificationNavigation.join(',')==='gpu,fix,settings'&&settingsSub==='apply'&&document.activeElement===$('wg-apply'));
check('review actions do not apply settings or call an API',actionRequests.length===0&&!$('wg-apply').disabled);api=actionApi;setTab('launcher');
renderVerification({...unset,verified:8,items:receipt.items.map((item,i)=>i===6?{...item,status:'not_checked',action:'nvidia',detail:'Not checked: access denied. No extra rights requested.'}:item)});
check('unreadable system value stays in denominator',$('verification-title').textContent==='Review settings: 8/9 verified'&&$('verification-list').querySelectorAll('[data-state="not_checked"]').length===1);
renderVerification({...receipt,verified:7,items:receipt.items.map((item,i)=>({...item,status:i===0?'changed':i===1?'failed':item.status,detail:i===0?'CS2 changed this value after Apply. Close CS2 and apply again.':i===1?'Config write failed: access denied.':item.detail}))});
check('partial result cannot claim PC set',$('verification').dataset.state==='failed'&&$('verification-title').textContent==='Review settings: 7/9 verified');
check('partial result updates Apply checklist too',$('apply-verification').dataset.state==='failed'&&$('apply-verification').textContent.includes('7/9 verified'));
verificationDirty=true;renderVerification(receipt);check('pending edits invalidate badge',$('verification-title').textContent.startsWith('Settings changed'));verificationDirty=false;
renderVerification({...receipt,selection:{intent:'quality'}});check('saved selection changes invalidate receipt after reload',$('verification-title').textContent.startsWith('Settings changed'));
renderVerification(receipt);
api=async()=>{throw Error('offline')};await refreshVerification();check('read failure invalidates green badge',$('verification-title').textContent.startsWith('Not checked')&&$('verification').dataset.state==='changed');
api=()=>new Promise(()=>{});await refreshVerification();check('hung read-back settles and enables retry',!verificationBusy&&!$('verify-again').disabled&&$('verification-title').textContent.startsWith('Not checked'));
api=async()=>receipt;await refreshVerification();check('read again restores actual result',$('verification-title').textContent==='Your PC is set: 9/9 verified'&&!$('verify-again').disabled);
renderVerification({...receipt,items:[{label:'<unsafe>',detail:'<img src=x>',status:'not_set',action:'constructor'}]});check('read-back escapes text and rejects unknown actions',!$('verification-list').querySelector('img,button')&&$('verification-list').textContent.includes('<unsafe>'));
renderVerification(receipt,true);
if(matchMedia('(prefers-reduced-motion: reduce)').matches)check('reduced motion disables checklist reveal',getComputedStyle(document.querySelector('.verify-row')).animationName==='none');
Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));check('background pauses read-back animation',document.documentElement.classList.contains('verify-paused'));delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));await Promise.resolve();await Promise.resolve();
for(const theme of ${JSON.stringify(themes)}){document.documentElement.dataset.theme=theme;check('verification readable in '+theme,getComputedStyle($('verification-title')).color!==getComputedStyle($('verification')).backgroundColor);}delete document.documentElement.dataset.theme;
renderPlan({intent:'balanced',tier:'S',headroom:5.7,estimated_fps:342,settings:[{name:'GPU level',after:'High',changed:true,reason:'Tier S headroom'}],launch_current:'',launch_new:'',launch_added:[],launch_removed:[],advisories:[{title:'Estimated 342 fps',detail:'Tier S',level:'warn'}],changed_count:1});
check('plan keeps settings without estimates',!/(342|headroom|Tier S)/.test($('results').textContent+$('assessment-out').textContent)&&$('results').textContent.includes('GPU level'));
check('Machine has no estimated FPS',!$('machine-out').textContent.includes('FPS')&&!$('machine-out').querySelector('.part-vs'));
check('launch controls moved once',['w-launch','steam-launch-out','who','who-menu'].every(id=>document.querySelectorAll('#'+id).length===1&&!!$(id).closest('[data-sub="steam"]')));
check('app Account stays separate',['account-card','account-out'].every(id=>document.querySelectorAll('#'+id).length===1&&!!$(id).closest('.subpane[data-sub="account"]'))&&!document.querySelector('.subpane[data-sub="steam"] #account-card'));
check('Steam preview moved from Apply',!$('results').textContent.includes('Steam launch options')&&$('steam-launch-out').textContent.includes('Next Apply'));
check('Worth knowing render removed',!$('results').textContent.includes('Worth knowing'));
setSettingsSub('account',true);check('saved Account preference restores Account',settingsSub==='account'&&!$('account-card').closest('.subpane').classList.contains('hidden')&&document.querySelector('#settings-subtabs [data-sub="account"]').getAttribute('aria-selected')==='true');setSettingsSub('apply',true);
const settingsPanel=document.querySelector('[data-panel="settings"]');panel.classList.add('hidden');settingsPanel.classList.remove('hidden');
for(const name of ['apply','this-pc','lighting','steam','account','apps','look','sound','config','editing','logs']){setSettingsSub(name,true);const pane=settingsPanel.querySelector('.subpane[data-sub="'+name+'"]');check('shared grid '+name,getComputedStyle(pane).gap==='16px'&&getComputedStyle(pane).display==='grid');}
setSettingsSub('apply',true);const machineRect=$('machine-card').getBoundingClientRect(),writeRect=$('w-video').closest('.panel').getBoundingClientRect();check('Machine and Write aligned',innerWidth<=900||Math.abs(machineRect.width-writeRect.width)<1&&machineRect.top===writeRect.top&&machineRect.height===writeRect.height);
settingsPanel.classList.add('hidden');panel.classList.remove('hidden');
const sample={intent:'balanced',settings:[{name:'Texture quality',before:'Low',after:'High',changed:true},{name:'Shadows',before:'Off',after:'On',changed:true},{name:'GPU level',before:'Quality',after:'Quality',before_raw:1,after_raw:3,same_label:true,changed:true}]};
for(const mode of INTENTS){presetBegin(mode);presetReveal({...sample,intent:mode});check(mode+' uses real preview values',document.querySelector('.preset-row').textContent.includes('Low → High'));check(mode+' dims behind selected card',!!document.querySelector('.preset-veil')&&presetSession.card.dataset.intent===mode);if(!matchMedia('(prefers-reduced-motion: reduce)').matches){check(mode+' reveals sequentially',document.querySelectorAll('.preset-row').length===1);await new Promise(r=>setTimeout(r,780));}check(mode+' displays every changed value',document.querySelectorAll('.preset-row').length===3&&document.querySelector('.preset-rows').textContent.includes('Quality (1) → Quality (3)'));presetClose();}
presetBegin('quality');presetReveal(sample);check('stale preset response ignored',!document.querySelector('.preset-row'));presetReveal({...sample,intent:'quality',settings:[]});check('unchanged preset honest',document.querySelector('.preset-rows').textContent==='Everything already matches.');document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));check('Escape clears dimming',!presetSession&&!document.querySelector('.preset-veil'));
presetBegin('balanced');Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));check('background cancels reveal and timer',!presetSession&&!document.querySelector('.preset-veil'));delete document.hidden;
presetBegin('balanced');panel.classList.add('hidden');await Promise.resolve();check('leaving Play cancels reveal',!presetSession);panel.classList.remove('hidden');
const oldApi=api;const queue=[];api=(route,body)=>new Promise((resolve,reject)=>queue.push({route,body,resolve,reject}));
const planFor=name=>({...sample,intent:name,launch_current:'-old',launch_new:'-new',launch_removed:[],launch_added:[],changed_count:3});
intent='competitive';const first=previewPlan();intent='quality';const second=previewPlan();queue[1].resolve(planFor('quality'));await second;queue[0].resolve(planFor('competitive'));await first;check('late plan cannot overwrite latest selection',planned.intent==='quality'&&$('assessment-out').textContent.includes('quality'));
check('Steam launch options use latest same plan',$('steam-launch-out').textContent.includes('-new')&&!$('results').textContent.includes('-new'));
presetBegin('quality');const failed=previewPlan();queue[2].reject(Error('Offline'));await failed;check('plan failure releases dimmer and preview button',!presetSession&&!$('preview').disabled);
api=oldApi;intent='balanced';paintIntent(intent);renderPlan(planFor('balanced'));
for(const theme of ${JSON.stringify(themes)}){document.documentElement.dataset.theme=theme;presetBegin('balanced');presetReveal(sample);const row=document.querySelector('.preset-row');check('preset readable in '+theme,getComputedStyle(row).color!==getComputedStyle(document.querySelector('.preset-changes')).backgroundColor);check('dimmer cuts window through selected card in '+theme,document.querySelector('.preset-veil').style.clipPath.includes('evenodd'));presetClose();}delete document.documentElement.dataset.theme;
renderVerification(receipt);$('verification').open=location.hash.includes('verification');
if(location.hash.includes('changed')){renderVerification({...receipt,verified:7,items:receipt.items.map((item,i)=>({...item,status:i===0?'changed':i===1?'failed':item.status,detail:i===0?'CS2 changed this value after Apply. Close CS2 and apply again.':i===1?'Config write failed: access denied.':item.detail}))},true);api=async()=>({...receipt,verified:7,items:receipt.items.map((item,i)=>({...item,status:i===0?'changed':i===1?'failed':item.status,detail:i===0?'CS2 changed this value after Apply. Close CS2 and apply again.':i===1?'Config write failed: access denied.':item.detail}))})}
if(location.hash.includes('notapplicable')){renderVerification(noNvidia,true);api=async()=>noNvidia}
if(location.hash.includes('notset')){renderVerification(unset,true);api=async()=>unset}
$('status').remove();document.querySelector('.scroll').scrollTop=0;
if(location.hash.includes('verification'))$('verification').scrollIntoView({block:'start'});
if(location.hash.includes('this-pc')){document.querySelector('[data-panel="launcher"]').classList.add('hidden');document.querySelector('[data-panel="settings"]').classList.remove('hidden');setSettingsSub('this-pc',true)}
if(location.hash.includes('settings-apply')){document.querySelector('[data-panel="launcher"]').classList.add('hidden');document.querySelector('[data-panel="settings"]').classList.remove('hidden');setSettingsSub('apply',true)}
if(location.hash.includes('settings-steam')){panel.classList.add('hidden');settingsPanel.classList.remove('hidden');setSettingsSub('steam',true);$('who-name').textContent='Edy';$('who-how').textContent='Following Steam';}
if(location.hash.includes('settings-account')){panel.classList.add('hidden');settingsPanel.classList.remove('hidden');setSettingsSub('account',true);cloudData={configured:true,signed_in:false,google:true};renderCloud();}
if(location.hash.includes('preset')){presetBegin('balanced');presetReveal(sample);await new Promise(r=>setTimeout(r,780));clearTimeout(presetSession.timer);$('intents').scrollIntoView({block:'center'});}
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
let html=s.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'');html=html.replace('<head>','<head><base href="'+url.pathToFileURL(path.join(root,'cs2cfg/web/')).href+'">');html=html.replace('</body>','<script>'+code+'</script></body>');
fs.writeFileSync(path.join(work,'preview.html'),html);
const chrome=process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';const args=['--headless','--no-sandbox','--disable-gpu','--allow-file-access-from-files','--user-data-dir='+path.join(work,'chrome'),'--window-size='+(process.env.HOME_VIEWPORT||'1440,1100'),'--virtual-time-budget=30000',url.pathToFileURL(path.join(work,'preview.html')).href+(process.env.HOME_HASH||'')];
if(process.env.HOME_REDUCED)args.unshift('--force-prefers-reduced-motion');
const out=cp.execFileSync(chrome,[...args,'--dump-dom','--screenshot='+(process.env.HOME_SCREENSHOT||path.join(work,'preview.png'))],{maxBuffer:4e6,stdio:['ignore','pipe','ignore']}).toString();fs.writeFileSync(path.join(work,'dom.html'),out);const result=[...out.matchAll(/<pre id="checks"[^>]*>(.*?)<\/pre>/gs)].at(-1);console.log(result?result[1]:'NO TEST RESULTS');assert(result&& !result[1].includes('false')&&!result[1].includes('"error"'));
console.log('Browser checks: '+JSON.parse(result[1]).length+' passed');
