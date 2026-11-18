const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const page=fs.readFileSync(path.join(__dirname,'../cs2cfg/web/index.html'),'utf8');
let now=0,serial=0;const timers=new Map();
function tick(ms){const until=now+ms;for(;;){const next=[...timers].filter(([,t])=>t.at<=until).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;now=next[1].at;timers.delete(next[0]);next[1].fn();}now=until;}
class El {
 constructor(){this.children=[];this.handlers={};this.dataset={};this.attrs={};this.style={setProperty(k,v){this[k]=v}};this.classes=new Set();this.classList={add:(...s)=>s.forEach(x=>this.classes.add(x)),remove:(...s)=>s.forEach(x=>this.classes.delete(x)),toggle:(s,v)=>v?this.classes.add(s):this.classes.delete(s)};}
 set className(s){this.classes=new Set(s.split(' ').filter(Boolean))}get className(){return [...this.classes].join(' ')}
 set innerHTML(s){this.html=s;this.button=new El();this.fill=new El();this.button.parent=this;this.fill.parent=this;}
 get innerHTML(){return this.html}
 get isConnected(){return this===root||!!this.parent?.isConnected}
 appendChild(e){this.children.push(e);e.parent=this;return e}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this);this.parent=null}
 getBoundingClientRect(){return {width:410}}
 setAttribute(k,v){this.attrs[k]=v}
 querySelector(s){return s==='button'?this.button:this.fill}
 addEventListener(k,f){this.handlers[k]=f}
 contains(e){return e===this||e?.parent===this}
 fire(k,e={}){this.handlers[k]?.(e)}
}
const root=new El(),doc=new El();doc.hidden=false;doc.documentElement=new El();doc.createElement=()=>new El();
const ctx=vm.createContext({assert,console,document:doc,$:id=>id==='status'?root:null,Error,Date:{now:()=>now},requestAnimationFrame:f=>f(),setTimeout:(fn,delay)=>{const id=++serial;timers.set(id,{fn,at:now+delay});return id},clearTimeout:id=>timers.delete(id)});
const source=page.slice(page.indexOf('function statusText('),page.indexOf('async function api('));
vm.runInContext(source+`
globalThis.testDock={status,busy,friendlyError,notificationDock};`,ctx);
const {status,busy,friendlyError,notificationDock:dock}=ctx.testDock;
const record=id=>dock.records.get(id),clear=()=>{status.clear();assert.equal(root.children.length,0)};
// Legacy states and actual timer boundary, including exit motion.
let id=status('Your settings are saved.');assert.equal(record(id).kind,'done');assert.equal(record(id).el.attrs.role,'status');
tick(5999);assert.ok(record(id));tick(1);assert.equal(record(id),undefined);tick(180);assert.equal(root.children.length,0);
id=busy('Reading settings');const element=record(id).el;tick(60000);assert.ok(record(id));assert.equal(record(id).kind,'working');
status('Your settings are ready.');assert.equal(record(id).el,element,'busy to done morphs on the same card');clear();
id=busy('Downloading',{progress:.6,detail:'3 of 5',id:'demo'});assert.equal(record(id).kind,'progress');assert.match(record(id).el.innerHTML,/aria-valuenow="60"/);assert.match(record(id).el.innerHTML,/3 of 5/);
busy('Downloading',{id:'demo',progress:1.5});assert.match(record(id).el.innerHTML,/aria-valuenow="100"/);clear();
busy('Unknown total',{id:'unknown'});assert.doesNotMatch(record('unknown').el.innerHTML,/aria-valuenow/);clear();
for(const kind of ['notice','warn']){id=status('Please close CS2.',{kind});assert.equal(record(id).kind,kind);assert.equal(record(id).el.attrs['aria-live'],'polite');clear();}
id=status('HTTP 500',{kind:'error',id:'error'});assert.equal(record(id).el.attrs.role,'alert');assert.equal(record(id).el.attrs['aria-live'],'assertive');assert.match(record(id).el.innerHTML,/<details><summary>Details/);assert.doesNotMatch(record(id).text,/500/);tick(600000);assert.ok(record(id));
status('A separate job finished.');assert.ok(record('error'),'errors survive other jobs');status('');assert.ok(record('error'),'legacy clearing does not remove an error');record('error').el.button.fire('click');tick(180);assert.equal(record('error'),undefined);clear();
status('Failed to fetch',true);const legacyError=[...dock.records.values()][0];busy('Another job');assert.ok(dock.records.has(legacyError.id),'legacy busy cannot wipe an error');clear();
// Three visible slots and a FIFO queue, with errors retained.
for(let i=0;i<5;i++)status('Please check your settings.',{kind:'error',id:'job'+i});assert.equal(root.children.length,3);assert.equal(record('job3').el,null);status.dismiss('job1');tick(180);assert.ok(record('job3').el);assert.equal(root.children.length,3);assert.ok(record('job0'));clear();
// Hover and keyboard focus pause the remaining time rather than resetting it.
id=status('Saved');let r=record(id);tick(2000);r.el.fire('pointerenter');tick(10000);assert.ok(record(id));r.el.fire('pointerleave');tick(3999);assert.ok(record(id));tick(1);assert.equal(record(id),undefined);tick(180);clear();
id=status('Saved');r=record(id);tick(1000);r.el.fire('focusin');tick(10000);r.el.fire('focusout',{relatedTarget:null});tick(4999);assert.ok(record(id));tick(1);assert.equal(record(id),undefined);tick(180);clear();
id=status('Saved');tick(1000);doc.hidden=true;doc.fire('visibilitychange');tick(20000);assert.ok(record(id));doc.hidden=false;doc.fire('visibilitychange');tick(5000);assert.equal(record(id),undefined);tick(180);clear();
// Untrusted strings are escaped even when compatibility markup is supplied.
id=status('<img src=x onerror=alert(1)><b>Saved &amp; ready</b>');assert.match(record(id).el.innerHTML,/&lt;img/);assert.doesNotMatch(record(id).el.innerHTML,/<img/);assert.match(record(id).el.innerHTML,/Saved &amp; ready/);clear();
const cases=[['Failed to fetch','background service'],['HTTP 503','background service'],['response was not JSON','background service'],['PermissionError: [WinError 5] Access is denied','access that file'],['FileNotFoundError: [WinError 2]','no longer available'],['TimeoutError: timed out','longer than expected'],['OSError: no space left on device','free space'],['ValueError: bad value at worker_id','could not finish'],['Traceback (most recent call last):','could not finish'],['0x80070002','could not finish']];
for(const [raw,expected] of cases)assert.ok(friendlyError(raw).includes(expected),raw+' => '+friendlyError(raw));
assert.equal(friendlyError('Close CS2 before changing match.cfg.'),'Close CS2 before changing match.cfg.');
assert.equal(friendlyError('The GoXLR Mini is already in use.'),'The GoXLR Mini is already in use.');
assert.match(friendlyError("PermissionError: access denied: 'C:\\exports\\My match.cfg'"),/access My match\.cfg/);
assert.match(friendlyError("FileNotFoundError: 'C:\\exports\\match.zip'"),/file match\.zip is no longer/);
assert.equal(friendlyError(new Error('Failed to fetch')),friendlyError('Failed to fetch'));
assert.ok(page.includes('@media (prefers-reduced-motion:reduce)'));assert.ok(page.includes('status-page-hidden'));assert.ok(page.includes("id:'demo-download',progress:job.total>0?job.seen/job.total:undefined"));
console.log('PASS: states, progress, morph, hide timing, persistence, queue, hover/focus/visibility, escaping, friendlyError');
