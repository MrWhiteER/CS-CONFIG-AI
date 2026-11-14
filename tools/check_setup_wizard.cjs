/* Offline browser checks of the production wizard, using synthetic API replies.
   No Steam session, preferences or game files are touched. No dependencies.
   node tools/check_setup_wizard.cjs
   Optional previews: SETUP_STEP, SETUP_THEME, SETUP_VIEWPORT, CHROME_PATH. */
const fs = require('fs'), os = require('os'), path = require('path');
const cp = require('child_process'), url = require('url'), assert = require('assert');
const root = path.resolve(__dirname, '..');
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'cs-config-setup-'));
const source = fs.readFileSync(path.join(root, 'cs2cfg/web/index.html'), 'utf8');
let scripts = 0;
for (const match of source.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)) {
  if (!match[1].trim()) continue;
  const filename = path.join(work, `inline-${++scripts}.js`);
  fs.writeFileSync(filename, match[1]);
  cp.execFileSync(process.execPath, ['--check', filename], {stdio:'pipe'});
}
console.log(`node --check: all ${scripts} inline script bodies passed`);
const slice = (a,b) => { const start = source.indexOf(a), end = source.indexOf(b,start); assert(start >= 0 && end > start, a); return source.slice(start,end); };
assert(source.indexOf('await checkFirstRun();') < source.indexOf('await startup.run("scan"'), 'setup gates startup');
const preview = process.env.SETUP_STEP || '', theme = process.env.SETUP_THEME || 'violet';
const code = `
window.addEventListener('error',event=>{const pre=document.createElement('pre');pre.id='setup-checks';pre.textContent=JSON.stringify({error:event.message+' at '+event.lineno,checks:[]});document.body.append(pre)});
const $ = id => document.getElementById(id);
${slice('function esc(s) {','async function api(')}
${slice('const THEMES = [','function currentTheme()')}
${source.match(/const MODE_ART = \{[\s\S]*?\n\};/)[0]}
${source.match(/const WAY_ICONS = \{[\s\S]*?\n\};/)[0]}
let lastScan = null, cloudData = null, cloudPoll = null, prefsReady = false, audioData = null;
let prefsNow = {}, failures = {}, calls = [], statuses = [], pollCount = 0;
let syncReply = {ok:true,action:'none'}, loginOpened = true, remoteCurrent = null, syncDelay = 0;
const fixture = {
  ok:true,needed:true,steps:['sync','permission','sound','preset','apps','theme'],
  cloud:{configured:true,signed_in:false},sync:{},
  cfg:{path:'C:\\\\Games\\\\Counter-Strike 2\\\\game\\\\csgo\\\\cfg',exists:true,writable:true,reason:''},
  sound:{output:[{id:'out-headset',name:'Gaming headset',default:true},{id:'out-speakers',name:'Desktop speakers'}],input:[{id:'in-mic',name:'USB microphone',default:true}]},
  presets:[{id:'competitive',label:'Competitive',fps:410,bottleneck:'CPU',blurb:'Highest frame rate and clearest picture for spotting players.'},{id:'balanced',label:'Balanced',fps:320,bottleneck:'CPU',blurb:'Good-looking and smooth. The default.'},{id:'quality',label:'Visual',fps:225,bottleneck:'GPU',blurb:'Best picture this PC can hold at a playable frame rate.'}],
  apps:[{id:'discord',name:'Discord',with_game:true},{id:'crosshairx',name:'Crosshair X',with_game:false},{id:'faceit-client',name:'FACEIT',with_game:true}],
  themes:THEMES.map(t=>t[0]),current:{intent:'balanced',theme:'violet',cfg_write_ok:null,sync_auto:true}
};
let response = structuredClone(fixture);
function status(text,error) { statuses.push({text,error}); }
function applyPrefs(ui) { prefsNow = {...ui}; applyTheme(ui.theme); }
function renderCloud() {} function loadAudio() {} function loadCompanions() {} function loadMachine() {} function previewPlan() {}
async function api(route,body) {
  calls.push({route,body:structuredClone(body)});
  if (failures[route]) throw new Error(failures[route]);
  if (route === '/api/firstrun') return structuredClone(response);
  if (route === '/api/firstrun/finish') {
    const a=body.answers;
    for (const [answer,key] of Object.entries({preset:'intent',theme:'theme',cfg_write:'cfg_write_ok',sync:'sync_auto'})) if (Object.hasOwn(a,answer)) response.current[key]=a[answer];
    response.needed=false;return {ok:true,ui:structuredClone(response.current)};
  }
  if (route === '/api/prefs') return {ui:structuredClone(response.current)};
  if (route === '/api/scan') return {cpu:{name:'Intel Core i7-13700K'},gpu:{name:'NVIDIA GeForce RTX 4070'}};
  if (route === '/api/sync/now') { if(syncDelay)await new Promise(r=>setTimeout(r,syncDelay));if(syncReply.action==='pull'&&remoteCurrent)Object.assign(response.current,remoteCurrent);return {ok:true,last:structuredClone(syncReply)}; }
  if (route === '/api/sync') return {ok:true,auto:response.current.sync_auto !== false,last:structuredClone(syncReply)};
  if (route === '/api/sync/auto') { response.current.sync_auto=body.on;return {ok:true,auto:body.on}; }
  if (route === '/api/cloud/login') return {ok:true,opened:loginOpened,url:'https://example.test/steam-login'};
  if (route === '/api/cloud/poll') { pollCount++;return {ok:true,waiting:false}; }
  if (route === '/api/cloud') return {ok:true,configured:true,signed_in:true};
  throw Error('Unexpected API: '+route);
}
${slice('/* First-run setup.','/* The Machine card:')}
document.querySelector('.boot-screen')?.remove();
document.documentElement.classList.remove('setup-checking');
const checks=[];
function check(name,value) { checks.push({name,ok:!!value});if(!value) throw Error(name); }
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const reset=()=>{ response=structuredClone(fixture);failures={};calls=[];syncReply={ok:true,action:'none'};remoteCurrent=null;syncDelay=0; };
const tap=selector=>{ const el=document.querySelector(selector);if(!el)throw Error('Missing '+selector);el.click(); };
const move=async(skip=false)=>{ await setupMove(1,skip); };
async function close() { await finishSetupWizard(); }
async function suite() {
  reset();
  const gating=checkFirstRun();await sleep(30);
  check('first request is POST first-run data',calls[0].route==='/api/firstrun'&&calls[0].body);
  check('needed setup opens before startup continues',!!setupSession&&!$('setup-wizard').hidden&&document.querySelector('.app').inert);
  check('Steam step has a single primary decision',getComputedStyle($('setup-steam')).display!=='none'&&getComputedStyle($('setup-steam-link')).display==='none'&&getComputedStyle($('setup-sync-retry')).display==='none');
  check('all six progress segments are present',$('setup-progress').children.length===6);
  await move(true);check('skip sync leaves it unanswered',!Object.hasOwn(setupSession.answers,'sync'));
  tap('[data-setup-permission="allow"]');await move();
  check('Windows sound defaults preselected',$('setup-audio-output').value==='out-headset'&&$('setup-audio-input').value==='in-mic');
  await move(true);await sleep(800);
  check('hardware chips reuse scan data',$('setup-hardware').textContent.includes('RTX 4070')&&$('setup-hardware').textContent.includes('i7-13700K'));
  check('FPS counters reach backend estimates',[...document.querySelectorAll('[data-setup-fps]')].every(n=>n.textContent===n.dataset.setupFps));
  check('Visual maps to quality id',document.querySelector('[data-setup-preset="quality"] b').textContent==='Visual');
  tap('[data-setup-preset="competitive"]');await move();
  check('companion defaults match this PC',[...document.querySelectorAll('[data-setup-app]:checked')].map(n=>n.dataset.setupApp).join(',')==='discord,faceit-client');
  check('companion icon route reused',document.querySelector('[data-setup-app-icon]').getAttribute('src')==='/companion-icon/discord.png');
  await move(true);check('theme offers all ten existing themes',document.querySelectorAll('[data-setup-theme]').length===10);
  tap('[data-setup-theme="paper"]');
  check('theme preview applies live without preference writes',document.documentElement.dataset.theme==='paper'&&!calls.some(c=>c.route==='/api/prefs'&&c.body));
  check('theme crossfade freezes previous wizard tokens or skips reduced motion',setupReduced.matches ? !document.querySelector('.setup-theme-ghost') : !!document.querySelector('.setup-theme-ghost')&&document.querySelector('.setup-theme-ghost').inert&&!document.querySelector('.setup-theme-ghost [id]'));
  await move(true);await gating;
  const finish=calls.find(c=>c.route==='/api/firstrun/finish').body.answers;
  check('finish sends only answered steps',JSON.stringify(finish)==='{"cfg_write":true,"preset":"competitive"}');
  check('skipping theme restores saved look',!document.documentElement.dataset.theme&&prefsNow.intent==='competitive');
  check('finish reloads preferences, closes and releases app',calls.some(c=>c.route==='/api/prefs')&&$('setup-wizard').hidden&&!document.querySelector('.app').inert);
  const finishCalls=calls.filter(c=>c.route==='/api/firstrun/finish').length;await checkFirstRun();check('completed setup does not auto-open twice',!setupSession&&calls.filter(c=>c.route==='/api/firstrun/finish').length===finishCalls);
  reset();response.cloud.configured=false;await openSetupWizard({step:'sync'});
  check('unconfigured cloud silently skips sync',setupCurrentStep()==='permission'&&!setupSession.steps.includes('sync'));
  await close();check('closing untouched setup saves no defaults',JSON.stringify(calls.find(c=>c.route==='/api/firstrun/finish').body.answers)==='{}');
  reset();response.current={intent:'quality',theme:'daylight',audio_output:'out-speakers',audio_input:'missing-mic',cfg_write_ok:false,sync_auto:false};
  await openSetupWizard({step:'sound'});
  check('rerun prefills saved devices including disconnected pins',$('setup-audio-output').value==='out-speakers'&&$('setup-audio-input').selectedOptions[0].textContent.includes('not connected'));
  await openSetupWizard({step:'preset'});check('rerun prefills current intent',document.querySelector('[data-setup-preset="quality"]').getAttribute('aria-pressed')==='true');
  document.querySelector('[data-setup-preset="quality"]').focus();document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Home',bubbles:true}));
  check('arrow-group keyboard selects and focuses tiles',document.activeElement.dataset.setupPreset==='competitive'&&setupSession.answers.preset==='competitive');
  await setupMove(-1);check('Back returns to previous step without accepting defaults',setupCurrentStep()==='sound'&&!Object.hasOwn(setupSession.answers,'sound'));
  await openSetupWizard({step:'permission'});check('Not now prefilled from current',document.querySelector('[data-setup-permission="later"]').getAttribute('aria-pressed')==='true');
  $('setup-next').focus();document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',bubbles:true}));check('modal traps Tab at last control',document.activeElement===$('setup-close'));
  document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',shiftKey:true,bubbles:true}));check('modal traps Shift Tab',document.activeElement===$('setup-next'));
  document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await sleep(450);check('Esc saves answered choices and closes',!setupSession&&calls.find(c=>c.route==='/api/firstrun/finish').body.answers.preset==='competitive');
  reset();response.cfg={path:'',writable:false,reason:'CS2 was not found on this PC'};response.apps=[];response.sound={error:'No audio stack'};response.presets[2].fps=null;
  await openSetupWizard({step:'permission'});check('unwritable folder explains reason and permits continuing',$('setup-content').textContent.includes('CS2 was not found')&&!$('setup-next').disabled);
  await move(true);check('missing audio remains usable',$('setup-content').textContent.includes('could not be read')&&$('setup-audio-output').value==='');
  await move(true);check('missing FPS never shows invented zero',document.querySelector('[data-setup-preset="quality"]').textContent.includes('Estimate unavailable'));
  await move(true);check('empty companion list has recovery copy',$('setup-content').textContent.includes('No companion apps found on this PC'));
  await close();
  reset();await openSetupWizard({step:'preset'});tap('[data-setup-preset="quality"]');failures['/api/firstrun/finish']='Save failed';await close();
  check('save failure preserves answers and keeps wizard open',setupSession.answers.preset==='quality'&&!$('setup-wizard').hidden&&!$('setup-next').disabled&&$('setup-error').textContent==='Save failed');
  failures={};await close();
  reset();syncReply={ok:true,action:'pull',source:'Gaming PC',written:['one.cfg','two.cfg'],waiting:0};remoteCurrent={intent:'quality',theme:'ember'};
  await openSetupWizard();loginOpened=false;tap('#setup-steam');await sleep(40);
  check('Steam login uses existing provider contract',calls.some(c=>c.route==='/api/cloud/login'&&c.body.provider==='steam'));
  check('browser-open fallback is a labelled link',$('setup-steam-link').href==='https://example.test/steam-login'&&!$('setup-steam-link').hidden);
  await sleep(1200);check('sign-in polls existing endpoint then syncs',pollCount>0&&calls.some(c=>c.route==='/api/sync/now'));
  check('pull counts written arrays and refreshes later prefills',$('setup-sync-result').textContent.includes('Gaming PC: 2 files')&&setupSession.draft.preset==='quality'&&setupSession.draft.theme==='ember');
  await close();
  reset();response.cloud.signed_in=true;syncReply={ok:true,action:'pull',written:['one.cfg'],waiting:0};remoteCurrent={intent:'quality',theme:'ember'};syncDelay=80;
  await openSetupWizard({step:'sync'});await openSetupWizard({step:'preset'});tap('[data-setup-preset="competitive"]');await openSetupWizard({step:'theme'});tap('[data-setup-theme="paper"]');await sleep(150);
  check('late pull preserves choices already answered',setupSession.draft.preset==='competitive'&&setupSession.draft.theme==='paper'&&document.documentElement.dataset.theme==='paper');
  await close();
  reset();response.cloud.signed_in=true;syncReply={ok:true,action:'pull',waiting:3,written:[]};await openSetupWizard();await sleep(40);
  check('already signed in syncs without another login',calls.some(c=>c.route==='/api/sync/now')&&!calls.some(c=>c.route==='/api/cloud/login'));
  check('waiting files retain honest source fallback',$('setup-sync-result').textContent.includes('your other PC: 3 files')&&$('setup-sync-result').textContent.includes('wait for permission'));
  await close();
  for (const [last,label] of [[{ok:true,action:'push'},'Synced to cloud'],[{ok:true,action:'pull',source:'Desk PC'},'Updated from Desk PC'],[{ok:true,action:'none'},'In sync'],[{ok:false,reason:'sign in with Steam to sync'},'sign in with Steam to sync']]) {
    syncStatusData={auto:true,last};renderSyncStatus();check('sync status '+label,$('sync-label').textContent===label);
  }
  syncStatusData={auto:true,last:{ok:true,action:'pull',waiting:4}};renderSyncStatus();
  check('waiting state offers permission step',!$('sync-permission').hidden&&$('sync-detail').textContent.includes('4 config files'));
  tap('#sync-permission');await sleep(20);check('permission action opens step two',setupCurrentStep()==='permission');await close();
  calls=[];syncReply={ok:true,action:'push'};tap('#sync-now');await sleep(30);check('Sync now uses expected endpoint',calls[0].route==='/api/sync/now'&&$('sync-label').textContent==='Synced to cloud');
  $('sync-auto').checked=false;$('sync-auto').dispatchEvent(new Event('change',{bubbles:true}));await sleep(20);check('auto toggle sends on boolean',calls.some(c=>c.route==='/api/sync/auto'&&c.body.on===false));
  failures['/api/sync/auto']='Offline';$('sync-auto').checked=true;$('sync-auto').dispatchEvent(new Event('change',{bubbles:true}));await sleep(20);check('failed auto update rolls back UI',!$('sync-auto').checked&&!$('sync-auto').disabled);failures={};
  reset();await openSetupWizard({step:'preset'});
  for (const [id] of THEMES) {
    applyTheme(id);
    for (const step of SETUP_STEPS) {
      await openSetupWizard({step});
      const box=$('setup-viewport'), next=$('setup-next').getBoundingClientRect();
      check(id+' / '+step+' fits viewport',box.scrollWidth<=box.clientWidth+1&&next.bottom<=innerHeight&&next.right<=innerWidth&&getComputedStyle($('setup-title')).color!==getComputedStyle($('setup-wizard')).backgroundColor);
    }
  }
  await openSetupWizard({step:'theme'});applyTheme('violet');
  const reduced=setupReduced.matches;
  if (reduced) { await openSetupWizard({step:'preset'});check('reduced motion skips FPS countups',[...document.querySelectorAll('[data-setup-fps]')].every(n=>n.textContent===n.dataset.setupFps));check('reduced motion removes particles',getComputedStyle(document.querySelector('.setup-particles')).display==='none'); }
  await close();
  let created=false, made=0;async function checkStarter(){return {ok:true,complete:false,present:[],autoexec:false}}async function makeStarter(){made++;return {ok:true}}
  async function starterAfterSetup(){${source.match(/await startup.run\("starter", async \(\) => \{([\s\S]*?)\n      \}\);/)[1]}}
  $('cfg-folder').value='';prefsNow={};await starterAfterSetup();check('skipping permission prevents automatic starter writes',made===0);
  prefsNow.cfg_write_ok=false;await starterAfterSetup();check('Not now prevents automatic starter writes',made===0);
  prefsNow.cfg_write_ok=true;await starterAfterSetup();check('Allow keeps automatic starter behavior',made===1&&created);
}
(async()=>{try {
  if (!${JSON.stringify(preview)}) await suite();
  reset();response.current.theme=${JSON.stringify(theme)};
  await openSetupWizard({step:${JSON.stringify(preview || 'preset')}});await sleep(900);
  // Headless virtual time advances timers independently of CSS animation time.
  // Settle finite effects for an honest screenshot of the final layout.
  for (const animation of document.getAnimations()) if (animation.effect?.target?.closest('.setup-wizard') && Number.isFinite(animation.effect.getComputedTiming().endTime)) animation.finish();
  document.body.insertAdjacentHTML('beforeend','<pre id="setup-checks" hidden>'+JSON.stringify({passed:checks.length,checks})+'</pre>');
} catch(error) {document.body.insertAdjacentHTML('beforeend','<pre id="setup-checks">'+JSON.stringify({error:error.stack,checks})+'</pre>');}})();
`;
let html = source.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, '');
fs.writeFileSync(path.join(work,'fixture-script.js'),code);
cp.execFileSync(process.execPath,['--check',path.join(work,'fixture-script.js')],{stdio:'pipe'});
html = html.replace('<head>', '<head><base href="' + url.pathToFileURL(path.join(root,'cs2cfg/web/')).href + '">');
html = html.replace('</body>', '<script>' + code + '</script></body>');
const file = path.join(work,'fixture.html'); fs.writeFileSync(file,html);
const chrome = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const args = ['--headless','--no-sandbox','--disable-gpu','--allow-file-access-from-files','--hide-scrollbars','--user-data-dir='+path.join(work,'chrome'),'--window-size='+(process.env.SETUP_VIEWPORT || '1440,1000'),'--virtual-time-budget=25000'];
if (process.env.SETUP_REDUCED) args.push('--force-prefers-reduced-motion');
const target = url.pathToFileURL(file).href;
const out = cp.execFileSync(chrome,[...args,'--dump-dom',target],{maxBuffer:8e6,stdio:['ignore','pipe','ignore']}).toString();
fs.writeFileSync(path.join(work,'dom.html'),out);
const result = [...out.matchAll(/<pre id="setup-checks"[^>]*>(.*?)<\/pre>/gs)].at(-1);
assert(result,'No browser results; inspect '+work);
const report = JSON.parse(result[1].replaceAll('&gt;','>').replaceAll('&lt;','<').replaceAll('&amp;','&'));
if (report.error) console.error(report.error,report.checks.filter(c=>!c.ok));
assert(!report.error,'Browser checks failed; inspect '+work);
console.log(`Browser checks: ${report.passed} passed`);
cp.execFileSync(chrome,[...args,'--screenshot='+path.join(work,'preview.png'),target],{stdio:'ignore'});
console.log('Screenshot and fixture: '+work);

// Exercise the entire unextracted page too: definitions and event hooks from
// other features must not throw or start work underneath the first-run gate.
if (!preview) {
  const bootData = {ok:true,needed:true,cloud:{configured:false},cfg:{writable:false,reason:'CS2 was not found on this PC'},sound:{},apps:[],presets:[],current:{theme:'violet'}};
  const bootstrap = `<script>
  window.__setupBootCalls=[];window.__setupBootErrors=[];
  addEventListener('error',e=>window.__setupBootErrors.push(e.message));
  addEventListener('unhandledrejection',e=>window.__setupBootErrors.push(String(e.reason)));
  const originalFetch=window.fetch;
  window.fetch=async(input,init)=>{const route=String(input);if(route.startsWith('/api/')){window.__setupBootCalls.push({route,method:init?.method||'GET'});if(route==='/api/firstrun')return new Response(JSON.stringify(${JSON.stringify(bootData)}),{headers:{'Content-Type':'application/json'}});throw Error('Startup ran under setup: '+route)}return originalFetch(input,init)};
  </script>`;
  const inspect = `<script>setTimeout(()=>{const result={calls:window.__setupBootCalls,errors:window.__setupBootErrors,open:!document.getElementById('setup-wizard').hidden,inert:document.querySelector('.app').inert,title:document.getElementById('setup-title')?.textContent};const pre=document.createElement('pre');pre.id='full-boot-checks';pre.textContent=JSON.stringify(result);document.body.append(pre)},2000)</script>`;
  const bootFile = path.join(work,'full-boot.html');
  fs.writeFileSync(bootFile,source.replace('<head>','<head><base href="'+url.pathToFileURL(path.join(root,'cs2cfg/web/')).href+'">'+bootstrap).replace('</body>',inspect+'</body>'));
  const bootDOM = cp.execFileSync(chrome,[...args,'--dump-dom',url.pathToFileURL(bootFile).href],{maxBuffer:8e6,stdio:['ignore','pipe','ignore']}).toString();
  fs.writeFileSync(path.join(work,'full-boot-dom.html'),bootDOM);
  const found = [...bootDOM.matchAll(/<pre id="full-boot-checks">(.*?)<\/pre>/gs)].at(-1);
  assert(found,'Full-page boot check did not complete');
  const boot = JSON.parse(found[1].replaceAll('&gt;','>').replaceAll('&lt;','<').replaceAll('&amp;','&'));
  assert.deepStrictEqual(boot.errors,[],'Full-page JavaScript errors');
  assert.deepStrictEqual(boot.calls,[{route:'/api/firstrun',method:'POST'}],'Only setup may run before first-run completion');
  assert(boot.open&&boot.inert&&boot.title==='Give your config a home.','First-run gate is visible over an inert app');
  console.log('Full-page boot: passed (POST first-run precedes all other app work)');
}
