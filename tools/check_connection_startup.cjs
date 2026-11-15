// Exercise the production loading-screen coordinator with a deferred connection.
const fs = require('fs'), path = require('path'), os = require('os');
const cp = require('child_process'), {pathToFileURL} = require('url'), assert = require('assert');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'cs2cfg/web/index.html'), 'utf8');
const coordinator = source.slice(source.indexOf('const startup = (() => {'), source.indexOf('</script>', source.indexOf('const startup = (() => {')));
const names = JSON.parse(coordinator.match(/const names = (\[[\s\S]*?\]);/)[1]);
assert(names.includes('connection'));
const boot = source.slice(source.indexOf('(async () => {\n  await checkFirstRun();'));
assert(boot.indexOf('startup.run("connection", runNetCheck)') > boot.indexOf('await checkFirstRun()'));
assert(boot.indexOf('startup.run("connection", runNetCheck)') < boot.indexOf('startup.run("scan"'));
assert(boot.includes('await Promise.allSettled([\n    connectionReady,'));
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'cs-config-connection-'));
const checks = `
const checks=[];
function check(name,ok){checks.push({name,ok});if(!ok)throw Error(name)}
(async()=>{try{
  let finishConnection;
  const connection = startup.run('connection',()=>new Promise(resolve=>{finishConnection=resolve}));
  await Promise.all(${JSON.stringify(names.filter(n => n !== 'connection'))}.map(name=>startup.run(name,async()=>{})));
  await new Promise(resolve=>setTimeout(resolve,400));
  check('loading waits for connection after other loads settle',!startup.finished&&!document.querySelector('.boot-screen').classList.contains('is-dismissed'));
  check('connection counted in loading progress',parseFloat(document.querySelector('.boot-screen').style.getPropertyValue('--boot-progress'))<100);
  let ready=0;document.addEventListener('cs2cfg:ready',()=>ready++);
  finishConnection();await connection;
  await new Promise(resolve=>setTimeout(resolve,500));
  check('connection completion dismisses loading',startup.finished&&ready===1);
  check('startup progress reaches 100 percent',document.querySelector('.boot-screen')===null);
}catch(error){checks.push({error:error.stack})}
const pre=document.createElement('pre');pre.id='checks';pre.textContent=JSON.stringify(checks);document.body.append(pre)})();`;
const file = path.join(work, 'startup.html');
// Virtual-time Chrome may skip paint frames. Schedule the two paint-grace
// callbacks deterministically; task coordination remains production code.
fs.writeFileSync(file, '<!doctype html><meta charset="utf-8"><div class="boot-screen"><span class="boot-tip"></span></div><script>window.requestAnimationFrame=callback=>setTimeout(()=>callback(performance.now()),16);'+coordinator+'\n'+checks+'</script>');
const chrome = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const output = cp.execFileSync(chrome, ['--headless','--no-sandbox','--disable-gpu','--user-data-dir='+path.join(work,'chrome'),'--virtual-time-budget=3000','--dump-dom',pathToFileURL(file).href], {maxBuffer:2e6,stdio:['ignore','pipe','ignore']}).toString();
const found = output.match(/<pre id="checks">(.*?)<\/pre>/s);
assert(found, 'No loading-screen results');
const report = JSON.parse(found[1]);
assert(report.every(c=>c.ok), JSON.stringify(report));
console.log('Connection startup checks: '+(report.length+4)+' passed');
