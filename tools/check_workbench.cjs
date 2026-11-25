/* Browser checks of shipped Tools controls with synthetic API responses only. */
const fs = require('fs'), path = require('path'), os = require('os');
const cp = require('child_process'), assert = require('assert'), vm = require('vm');
const {pathToFileURL} = require('url');
const root = path.resolve(__dirname, '..');
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'cs-config-tools-'));
const source = fs.readFileSync(path.join(root, 'cs2cfg/web/index.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'cs2cfg/web/workbench.js'), 'utf8');
new vm.Script(script);
const fixtures = `
const esc = value => String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
const calls=[], errors=[];window.addEventListener('error',e=>errors.push(e.message));
const sb={spec:{name:'Duck',mode:'hold',steps:[{id:'cmd:+duck'}]},binding:'scancode13',target:''};
const appAsk=async()=>true;function setTab(){}function setSettingsSub(){}async function showFile(){}
URL.createObjectURL=()=> 'blob:test'; URL.revokeObjectURL=()=>{};
HTMLAnchorElement.prototype.click=function(){calls.push({download:this.download})};
let practiceSession={};
async function api(route,body={}) {
 calls.push({route,body:structuredClone(body)});
 if(route==='/api/tools/sync')return body.resolution?{ok:true,action:body.resolution}:{comparison:{local_hash:'local',remote_hash:'remote',source:'Home',action:'conflict',pending:false,failed:[],files:[{path:'me/a.cfg',status:'different',diff:'<img src=x onerror=alert(1)>'}],prefs:[]}};
 if(route==='/api/tools/benchmarks')return body.action==='compare'?{comparison:{A:{avg_fps:100},B:{avg_fps:120},fps_change_percent:20,warnings:['Repeat comparable workloads.']}}:{plan:{},context:{preset:'balanced'},runs:[{stamp:'A',started:'A',duration:180,intent:'balanced',overlay:{avg_fps:100}},{stamp:'B',started:'B',duration:180,intent:'quality',overlay:{avg_fps:120}}]};
 if(route==='/api/tools/trace')return {explanation:'Startup order',winner:{value:'1',file:'me/a.cfg',line:1},saved_game_value:'2',stock:null,definitions:[{value:'<img src=x>',file:'me/a.cfg',line:1,startup:true}],history:[{id:'app:test',title:'Edited sensitivity',files:['a.cfg']}]};
 if(route==='/api/tools/trace/undo')return {ok:true};
 if(route==='/api/tools/diagnostics')return body.action==='export'?{filename:'CS-CONFIG-AI-diagnostics.zip',data:btoa('zip fixture')}:{token:'preview',data:{app_version:'test'},excluded:['Credentials']};
 if(route==='/api/tools/script-debug')return {built:{checks:[]},simulation:{limits:'Simulation only',held:[],settings:{},errors:[],warnings:[],trace:[{event:'down',kind:'command',command:'<img src=x>',held:[]}]}};
 if(route==='/api/tools/practice') {
   if(body.action==='start')practiceSession={status:'active',file:body.file,map:body.map,steps:['Practice','Restore'],done:[]};
   if(body.action==='step')practiceSession.done=[body.index];
   if(body.action==='end')practiceSession.status='restore_pending';
   if(body.action==='verify')practiceSession.status='verified';
   return {session:practiceSession,options:{setups:[{file:'me/practice.cfg',name:'Practice'}],maps:[{id:'de_mirage',name:'Mirage'}]},lineups:[]};
 }
 throw Error('Unexpected route '+route);
}
document.querySelector('.boot-screen')?.remove();
document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('hidden',p.dataset.panel!=='settings'));
document.querySelectorAll('[data-panel="settings"] .subpane').forEach(p=>p.classList.toggle('hidden',p.dataset.sub!=='tools'));
document.querySelector('#settings-subtabs [data-sub="tools"]').setAttribute('aria-selected','true');
`;
const checks = `
(async()=>{
 const results=[];const check=(name,value)=>{results.push({name,ok:!!value});if(!value)throw Error(name)};
 const tick=()=>new Promise(r=>setTimeout(r,40));
 const click=async action=>{const b=document.querySelector('[data-tools-action="'+action+'"]');check('control '+action+' exists',!!b);b.click();await tick()};
 try {
 await tick();check('five new tool panels mount',document.querySelectorAll('#tools-workspace>section').length===5);
 await click('sync-review');check('sync source and diff visible',document.getElementById('tools-sync').textContent.includes('Home')&&!document.getElementById('tools-sync').querySelector('img'));
 await click('sync-pull');check('sync choice carries expected revisions',calls.some(c=>c.body?.resolution==='pull'&&c.body.local_hash==='local'&&c.body.remote_hash==='remote'));
 document.getElementById('tools-bench-map').value='Mirage route';await click('bench-arm-A');check('arm carries workload label',calls.some(c=>c.body?.action==='arm'&&c.body.slot==='A'&&c.body.map==='Mirage route'));
 document.querySelector('[data-tools-run="A"][data-side="A"]').checked=true;
 document.querySelector('[data-tools-run="B"][data-side="B"]').checked=true;
 await click('bench-compare');check('measured comparison visible',document.getElementById('tools-bench-result').textContent.includes('20%'));
 await click('trace');check('trace escapes values',!document.getElementById('tools-trace').querySelector('img')&&document.getElementById('tools-trace').textContent.includes('Startup order'));
 await click('trace-undo');check('undo names the selected recorded change',calls.some(c=>c.route==='/api/tools/trace/undo'&&c.body.id==='app:test'));
 check('export starts disabled',document.getElementById('tools-diag-export').disabled);
 await click('diag-preview');check('preview enables export',!document.getElementById('tools-diag-export').disabled);
 await click('diag-export');check('export uses the preview token',calls.some(c=>c.route==='/api/tools/diagnostics'&&c.body.action==='export'&&c.body.token==='preview'));
 check('export creates a local ZIP download',calls.some(c=>c.download==='CS-CONFIG-AI-diagnostics.zip'));
 await click('practice-start');check('practice checklist rendered',document.querySelectorAll('[data-practice-step]').length===2);
 await click('practice-end');check('practice waits for verification',document.getElementById('tools-practice').textContent.includes('pending verification'));
 await click('practice-verify');check('verified result comes from API',document.getElementById('tools-practice').textContent.includes('verified'));
 await click('debug-down');await click('debug-up');check('debugger replays press and release',calls.some(c=>c.route==='/api/tools/script-debug'&&c.body.events?.join(',')==='down,up'));
 check('debugger escapes command text',!document.getElementById('tools-debug').querySelector('img'));
 const before=calls.length;await click('debug-reset');check('clear does not call backend',calls.length===before);
 const strip=document.getElementById('settings-subtabs'),pane=document.querySelector('[data-panel="settings"] .subpane[data-sub="tools"]');
 strip.lastElementChild.focus();strip.lastElementChild.scrollIntoView({block:'nearest',inline:'nearest'});
 check('only tab strip scrolls horizontally',strip.scrollWidth>strip.clientWidth&&strip.scrollLeft>0&&pane.getBoundingClientRect().left>=185);
 check('no uncaught client errors',errors.length===0);
 }catch(error){results.push({error:error.stack})}
 const meta=document.createElement('meta');meta.name='fixture-results';meta.content=btoa(unescape(encodeURIComponent(JSON.stringify(results))));document.head.append(meta);
})();`;
let html = source.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, '');
html = html.replace('<head>', () => '<head><base href="'+pathToFileURL(path.join(root,'cs2cfg/web/')).href+'">');
html = html.replace('</body>', () => '<script>'+fixtures+'</script><script>'+script+'</script><script>'+checks+'</script></body>');
fs.writeFileSync(path.join(work,'preview.html'),html);
const chrome=process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe';
const output=cp.execFileSync(chrome,['--headless','--no-sandbox','--disable-gpu','--allow-file-access-from-files','--user-data-dir='+path.join(work,'chrome'),'--window-size=1280,900','--virtual-time-budget=12000','--dump-dom',pathToFileURL(path.join(work,'preview.html')).href],{maxBuffer:4e6,stdio:['ignore','pipe','ignore']}).toString();
fs.writeFileSync(path.join(work,'dom.html'),output);
const match=output.match(/<meta name="fixture-results" content="([A-Za-z0-9+/=]+)">/);
assert(match,'No browser result; fixture '+work);
const result=JSON.parse(Buffer.from(match[1],'base64').toString('utf8'));
assert(result.every(r=>r.ok),JSON.stringify(result.slice(-5))+'; fixture '+work);
console.log('Tools workspace: '+result.length+' browser checks passed');
