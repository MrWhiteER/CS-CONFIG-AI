const fs=require('fs'),cp=require('child_process'),assert=require('assert');
const path=require('path'),url=require('url');
const root=path.resolve(__dirname,'..');process.chdir(root);
const work=path.join(require('os').tmpdir(),'cs-config-home-'+require('crypto').createHash('sha1').update(root).digest('hex').slice(0,8));fs.mkdirSync(work,{recursive:true});
const s=fs.readFileSync('cs2cfg/web/index.html','utf8');
for(const x of s.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))new (require('vm').Script)(x[1]);
const themes=require('vm').runInNewContext(s.slice(s.indexOf('const THEMES = [')+'const THEMES = '.length,s.indexOf('function applyTheme(')).trim().replace(/;$/, '')).map(t=>t[0]);
const slice=(a,b)=>s.slice(s.indexOf(a),s.indexOf(b,s.indexOf(a)));
let code=fs.readFileSync(path.join(root,'cs2cfg/web/assets/hardware/icons.js'),'utf8')+'\n'+fs.readFileSync(path.join(root,'cs2cfg/web/assets/fixit/icons.js'),'utf8')+'\n'+`const $=id=>document.getElementById(id); const esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');let intent='balanced',planned={},prefs=0,previews=0;const INTENTS=['competitive','balanced','quality'];function paintModeBadge(){} function rememberPrefs(){prefs++} function noteChange(){} function requestBody(){return {intent,target_fps:240}};async function api(url,b){return {intent:b.intent,estimated_fps:{competitive:410,balanced:340,quality:230}[b.intent]}};const tempAlarm={};function status(){};`;
code+=slice("function renderHardware(d) {","/* The machine's scores,");
code+=`let prefsNow={},audioData=null;`;
code+=slice('function audioOptions(list, pinned)', 'async function saveAudio');
code+=slice('let wgData = null;','document.addEventListener("click", async e => {');
code+=slice('const CHIPS = { CPU:', '// -- 2. the gradient');
code+=slice('/* Launcher motion:','function renderPlan(');
code+=slice('/* Every card uses','async function previewPlan()');
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
setBandFigures({intent:'competitive',estimated_fps:410});await new Promise(r=>setTimeout(r,30));check('all mode estimates use backend result',Array.from(document.querySelectorAll('[data-mode-fps]')).every(el=>homeMotion.jobs.has(el)||Number(el.textContent)>0));
$('history-stats').innerHTML='<div class="stat"><b>16</b><span>sessions</span></div><div class="stat"><b>5.5</b><span>hours played</span></div><div class="stat"><b>7.41s</b><span>alt-tab back</span></div>';
renderHardware({cpu:{name:'Intel Core i9-12900K',cores:16,threads:24},gpu:{name:'NVIDIA GeForce RTX 3090 Ti',vram_gb:24,driver:'621.01'},ram_gb:32,ram_speed:6000,displays:[{width:2560,height:1440,refresh:240,primary:true,confident:true}],power_plan:'Balanced'});
$('assessment-out').innerHTML='<div class="assess"><div class="subcat">Assessment</div><div class="stats"><div class="stat"><b>A</b><span>tier</span></div><div class="stat"><b>~410</b><span>est. fps</span></div><div class="stat"><b>1.7—</b><span>of 240 Hz</span></div><div class="stat"><b>CPU</b><span>limited by</span></div></div></div>';
$('assessment-out').innerHTML=$('assessment-out').innerHTML.replace('<b>CPU</b>','<b>'+hwIcon('cpu')+'</b>');
homeFrame(performance.now()+2200);check('gauge reaches its target',node.querySelector('.val').textContent==='80');check('smooth combined area chart',$('hardware-chart').querySelector('.hardware-line').getAttribute('d').includes(' C'));
const errors=[...document.images].filter(i=>i.getAttribute('src')&&(!i.complete||!i.naturalWidth));check('all home image assets load',errors.length===0);
check('no horizontal overflow',document.documentElement.scrollWidth<=innerWidth);
const media=homeMotion.reduced;homeMotion.reduced={matches:true};homeNumber(node.querySelector('.val'),31);check('reduced motion sets final reading immediately',node.querySelector('.val').textContent==='31');homeMotion.reduced=media;
const panel=document.querySelector('[data-panel="launcher"]');panel.classList.add('hidden');homePause();hardwarePause();check('hidden graph stops frames',!hardwareGraph.raf);check('hidden Launcher pauses animation scheduler',!homeMotion.raf && document.documentElement.classList.contains('home-paused'));panel.classList.remove('hidden');homePause();
for(const theme of ${JSON.stringify(themes)}){if(theme==='violet')delete document.documentElement.dataset.theme;else document.documentElement.dataset.theme=theme;check('theme '+theme+' keeps controls visible',getComputedStyle($('play')).display!=='none' && getComputedStyle(node.querySelector('.val')).fill!=='none');const tones=[...document.querySelectorAll('.hardware-line')].map(el=>getComputedStyle(el).stroke);check('theme '+theme+' keeps chart series distinct',new Set(tones).size===4&&!tones.includes('none'));}delete document.documentElement.dataset.theme;
const wasReduced=homeMotion.reduced;homeMotion.reduced={matches:true};hardwareUpdate({at:108,history,gpu:{}});check('reduced motion skips chart scrolling',hardwareGraph.offset===0&&!hardwareGraph.raf);homeMotion.reduced=wasReduced;

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

$('status').remove();document.querySelector('.scroll').scrollTop=0;
if(location.hash.includes('system')){$('live-card').scrollIntoView({block:'start'});hardwareInspect(400)}
if(location.hash.includes('sound')){const card=$('audio-card');document.querySelector('.scroll').replaceChildren(card);card.scrollIntoView()}
if(location.hash.includes('machine')){const card=$('machine-card');document.querySelector('.scroll').replaceChildren(card);card.scrollIntoView()}
if(location.hash.includes('family')){const thermal=$('live-temps').cloneNode(true);thermal.style.cssText='display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:28px;margin:28px;';document.querySelector('.scroll').innerHTML='<section class="panel"><h2>Hardware family</h2><div style="display:grid;grid-template-columns:repeat(4,1fr);gap:32px;padding:28px">'+Object.keys(HW_ART).map(k=>'<div style="display:flex;align-items:center;gap:18px">'+hwIcon(k)+'<span>'+HW_NAMES[k]+'</span></div>').join('')+'</div></section>';const frame=document.createElement('div');frame.dataset.panel='launcher';frame.append(thermal);document.querySelector('.scroll').firstElementChild.append(frame)}
if(location.hash.includes('paper'))document.documentElement.dataset.theme='paper';
if(location.hash.includes('solo'))hardwareSelect('gpu');

}catch(e){checks.push({error:e.stack})}const freeze=document.createElement('style');freeze.textContent='*,*::before,*::after{transition:none!important;animation:none!important}';document.head.append(freeze);document.body.insertAdjacentHTML('beforeend','<pre id="checks" hidden>'+JSON.stringify(checks)+'</pre>')})();`;
let html=s.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'');html=html.replace('<head>','<head><base href="'+url.pathToFileURL(path.join(root,'cs2cfg/web/')).href+'">');html=html.replace('</body>','<script>'+code+'</script></body>');
fs.writeFileSync(path.join(work,'preview.html'),html);
const chrome=process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';const args=['--headless','--no-sandbox','--disable-gpu','--allow-file-access-from-files','--user-data-dir='+path.join(work,'chrome'),'--window-size='+(process.env.HOME_VIEWPORT||'1440,1100'),'--virtual-time-budget=4000',url.pathToFileURL(path.join(work,'preview.html')).href+(process.env.HOME_HASH||'')];
if(process.env.HOME_REDUCED)args.unshift('--force-prefers-reduced-motion');
const out=cp.execFileSync(chrome,[...args,'--dump-dom'],{maxBuffer:4e6,stdio:['ignore','pipe','ignore']}).toString();fs.writeFileSync(path.join(work,'dom.html'),out);const result=[...out.matchAll(/<pre id="checks"[^>]*>(.*?)<\/pre>/gs)].at(-1);console.log(result?result[1]:'NO TEST RESULTS');assert(result&& !result[1].includes('false')&&!result[1].includes('"error"'));
cp.execFileSync(chrome,[...args,'--screenshot='+(process.env.HOME_SCREENSHOT||path.join(work,'preview.png'))],{stdio:'ignore'});
