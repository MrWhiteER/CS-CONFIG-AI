// Exercise the shipped widget and styles with fixture pings, without the backend.
const fs = require('fs'), path = require('path'), os = require('os');
const {spawn} = require('child_process');
const {pathToFileURL} = require('url');
const assert = require('assert');

const root = path.resolve(__dirname, '..');
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'cs-config-ping-'));
const source = fs.readFileSync(path.join(root, 'cs2cfg/web/index.html'), 'utf8');
for (const script of source.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))
  new (require('vm').Script)(script[1]);
const widget = source.slice(source.indexOf('const serverPingWidget = (() => {'), source.indexOf('let activeTab ='));
const fixture = [
  ['pwj', 'Fujairah', 'United Arab Emirates', 6], ['bom', 'Mumbai', 'India', 41],
  ['par', 'Paris', 'France', 75], ['fra', 'Frankfurt', 'Germany', 80],
  ['ams', 'Amsterdam', 'Netherlands', 85], ['lhr', 'London', 'United Kingdom', 90],
  ['sto', 'Stockholm', 'Sweden', 95], ['mad', 'Madrid', 'Spain', 100],
  ['sgp', 'Singapore', 'Singapore', 110], ['dxb', 'Dubai', 'United Arab Emirates', 130],
  ['tyo', 'Tokyo', 'Japan', 180], ['syd', 'Sydney', 'Australia', null]
].map(([code, city, country, ping_ms]) => ({code, city, country, ping_ms,
  status: ping_ms === null ? 'unknown' : ping_ms > 120 ? 'bad' : 'good', loss: 0, relays_tried: 1}));
const setup = `
const esc = x => String(x ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const startup = {finished:true};
const fixture = ${JSON.stringify(fixture)};
let pingError = '';
async function api() { return {regions:fixture, error:pingError, updated_at:Date.now()/1000, running:false}; }
document.documentElement.dataset.boot = 'ready';
document.querySelector('.boot-screen').remove();
document.getElementById('status').remove();
`;
const html = source.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, '')
  .replace('<head>', '<head><base href="'+pathToFileURL(path.join(root,'cs2cfg/web/')).href+'">')
  .replace('</body>', '<script>'+setup+widget+'</script></body>');
const preview = path.join(work, 'preview.html');
fs.writeFileSync(preview, html);

const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless', '--no-sandbox', '--disable-gpu', '--allow-file-access-from-files',
  '--remote-debugging-port=0', '--user-data-dir='+path.join(work,'chrome'), 'about:blank'
], {stdio:'ignore', windowsHide:true});
let socket;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  try {
    const portFile = path.join(work, 'chrome/DevToolsActivePort');
    for (let n=0; !fs.existsSync(portFile) && n<100; n++) await delay(50);
    const port = fs.readFileSync(portFile, 'utf8').split('\n')[0];
    const targets = await (await fetch('http://127.0.0.1:'+port+'/json')).json();
    socket = new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
    await new Promise(resolve => socket.addEventListener('open', resolve, {once:true}));
    let sequence = 0;
    const pending = new Map();
    socket.addEventListener('message', event => {
      const reply = JSON.parse(event.data);
      if (reply.id) { pending.get(reply.id)(reply); pending.delete(reply.id); }
    });
    const send = (method, params={}) => new Promise((resolve,reject) => {
      const id = ++sequence;
      pending.set(id, reply => reply.error ? reject(Error(JSON.stringify(reply.error))) : resolve(reply.result));
      socket.send(JSON.stringify({id, method, params}));
    });
    const evaluate = async expression => {
      const result = await send('Runtime.evaluate', {expression, returnByValue:true, awaitPromise:true});
      assert(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
      return result.result.value;
    };
    await send('Emulation.setDeviceMetricsOverride', {width:1400,height:860,deviceScaleFactor:1,mobile:false});
    await send('Page.navigate', {url:pathToFileURL(preview).href});
    for (let n=0; n<100 && !await evaluate('!!document.getElementById("sp-panel")'); n++) await delay(50);
    await evaluate('document.getElementById("sp-toggle").click()');
    await delay(750);
    const measure = () => evaluate(`(() => {
      const rect = q => { const el=document.querySelector(q), r=el.getBoundingClientRect(), c=getComputedStyle(el);
        return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,height:r.height,position:c.position,
          clientHeight:el.clientHeight,scrollHeight:el.scrollHeight}; };
      return {open:document.getElementById('sp-panel').matches(':popover-open'),viewport:[innerWidth,innerHeight],
        hero:rect('#home-hero'),chip:rect('#sp-toggle'),bar:rect('.topbar'),
        panel:rect('#sp-panel'),head:rect('.sp-head'),search:rect('.sp-search'),list:rect('.sp-list'),
        row:rect('.sp-row'),notice:rect('.sp-notice'),foot:rect('.sp-foot')};
    })()`);
    const settled = async () => {
      await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
      await delay(40); // Allow the app's global reduced-motion transitions to finish.
    };
    const capture = async name => {
      const screenshot = await send('Page.captureScreenshot');
      fs.writeFileSync(path.join(work,name+'.png'), Buffer.from(screenshot.data,'base64'));
    };
    let checks = 0;
    const check = (message, ok) => { assert(ok, message); checks++; };
    const checkLayout = (g, label) => {
      check(label+': remains open', g.open);
      check(label+': gap below actual top bar', g.panel.top >= g.bar.bottom+14-0.1);
      check(label+': stays inside viewport', g.panel.bottom <= g.viewport[1]-12+0.1 && g.panel.left >= 12 && g.panel.right <= g.viewport[0]-12);
      check(label+': fixed sections stay inside panel', g.head.top >= g.panel.top && g.foot.bottom <= g.panel.bottom);
      check(label+': search and list do not overlap', g.search.bottom <= g.list.top);
      check(label+': footnote stays between list and footer', g.list.bottom <= g.notice.top && g.notice.bottom <= g.foot.top && g.notice.position==='static');
      check(label+': only list scrolls', g.list.scrollHeight > g.list.clientHeight && g.panel.scrollHeight <= g.panel.clientHeight+1);
    };
    const baseline = await measure();
    checkLayout(baseline, '1400x860');
    const rows = baseline.list.height / baseline.row.height;
    check('1400x860: six to eight rows', rows >= 6 && rows <= 8);
    await capture('violet-1400x860');
    check('normal motion: upward unfold and row stagger remain', await evaluate(`(() => {
      const el=document.getElementById('sp-panel'),panel=getComputedStyle(el),origin=panel.transformOrigin.split(' ').map(parseFloat);
      const rules = [...document.styleSheets].flatMap(sheet=>[...sheet.cssRules]);
      const animations = rules.filter(rule=>rule.type===CSSRule.KEYFRAMES_RULE && /^sp-/.test(rule.name));
      return panel.animationName==='sp-unfold' && Math.abs(origin[0]-el.offsetWidth)<1 && Math.abs(origin[1]-el.offsetHeight)<1 &&
        animations.length===4 && animations.every(animation=>[...animation.cssRules].every(frame=>
          [...frame.style].every(property=>['transform','opacity'].includes(property))));
    })()`));
    await send('Emulation.setEmulatedMedia', {features:[{name:'prefers-reduced-motion',value:'reduce'}]});
    check('reduced motion disables panel and row animations', await evaluate(`getComputedStyle(document.getElementById('sp-panel')).animationName==='none' && getComputedStyle(document.querySelector('.sp-row')).animationName==='none'`));

    for (const [width,height] of [[1400,860],[1400,650],[1400,560],[1100,700],[900,650],[640,700]]) {
      await send('Emulation.setDeviceMetricsOverride', {width,height,deviceScaleFactor:1,mobile:false});
      await settled();
      for (const theme of ['violet','ember','carbon','acid','crimson','frost','neon','daylight','paper','pro']) {
        await evaluate(theme==='violet' ? 'delete document.documentElement.dataset.theme' : 'document.documentElement.dataset.theme='+JSON.stringify(theme));
        await settled();
        checkLayout(await measure(), theme+' '+width+'x'+height);
        const colors = await evaluate(`(() => {
          const panel = document.getElementById('sp-panel'), style=getComputedStyle(panel);
          const probe = document.createElement('span');probe.style.color='var(--ink)';panel.append(probe);
          const themed={color:style.color,expected:getComputedStyle(probe).color,background:style.backgroundImage};probe.remove();return themed;
        })()`);
        check(theme+': uses theme text and panel tokens '+JSON.stringify(colors), colors.color===colors.expected && colors.background.includes('gradient'));
        if (width===1400 && height===860 && ['daylight','paper'].includes(theme)) await capture(theme+'-1400x860');
      }
      if (width===640) await capture('pro-640x700');
    }

    await send('Emulation.setDeviceMetricsOverride', {width:1400,height:860,deviceScaleFactor:1,mobile:false});
    await evaluate(`delete document.documentElement.dataset.theme;
      fixture[fixture.length-1].ping_ms=200;fixture[fixture.length-1].status='bad';
      document.querySelector('.sp-refresh').click();`);
    await settled();
    checkLayout(await measure(), 'full relay explanation');
    check('full help text appears', await evaluate(`document.querySelector('.sp-notice').textContent.includes('In-game ping is usually within a few ms.')`));
    await capture('help-1400x860');
    await evaluate(`pingError='A relay measurement failed. '.repeat(12);document.querySelector('.sp-refresh').click()`);
    await settled();
    checkLayout(await measure(), 'wrapped measurement error');
    await evaluate(`pingError='';document.querySelector('.sp-refresh').click();document.querySelector('.topbar').style.minHeight='108px'`);
    await settled();
    checkLayout(await measure(), 'top bar grows without window resize');
    await evaluate(`document.querySelector('.topbar').style.minHeight='';document.querySelector('.sp-list').scrollTop=10000`);
    await settled();
    const scrolled = await measure();
    checkLayout(scrolled, 'scrolled to last region');
    check('last region scrolls into list without moving footer', await evaluate(`(() => {
      const list=document.querySelector('.sp-list'),last=list.lastElementChild.getBoundingClientRect();
      return list.scrollTop>0 && last.bottom <= list.getBoundingClientRect().bottom+1;
    })()`));
    await evaluate(`document.querySelector('.sp-search').value='france';document.querySelector('.sp-search').dispatchEvent(new Event('input'))`);
    await settled();
    const filtered = await measure();
    check('search shrinks to one matching region', await evaluate(`document.querySelectorAll('.sp-row').length===1 && document.querySelector('.sp-city').textContent==='Paris'`));
    check('small results remain anchored nine pixels above pill', Math.abs(filtered.chip.top-filtered.panel.bottom-9)<1);
    await evaluate(`document.getElementById('sp-toggle').click()`);
    await settled();
    check('pill toggles a panel that fits above it', !await evaluate(`document.getElementById('sp-panel').matches(':popover-open')`));
    await evaluate(`document.querySelector('.sp-search').value='';document.getElementById('sp-toggle').click()`);
    await settled();
    await evaluate(`document.querySelector('.sp-close').click()`);
    await settled();
    check('close control dismisses panel and restores pill focus', await evaluate(`!document.getElementById('sp-panel').matches(':popover-open') && document.activeElement.id==='sp-toggle' && document.getElementById('sp-toggle').getAttribute('aria-expanded')==='false'`));
    await evaluate(`document.getElementById('sp-toggle').click()`);
    await settled();
    await send('Input.dispatchKeyEvent', {type:'keyDown',key:'Escape',code:'Escape'});
    await settled();
    check('Escape dismisses panel', !await evaluate(`document.getElementById('sp-panel').matches(':popover-open')`));
    await evaluate(`document.getElementById('sp-toggle').click()`);
    await settled();
    await send('Input.dispatchMouseEvent', {type:'mousePressed',x:300,y:180,button:'left',clickCount:1});
    await send('Input.dispatchMouseEvent', {type:'mouseReleased',x:300,y:180,button:'left',clickCount:1});
    await settled();
    check('outside click dismisses panel', !await evaluate(`document.getElementById('sp-panel').matches(':popover-open')`));

    await send('Emulation.setDeviceMetricsOverride', {width:1400,height:1300,deviceScaleFactor:1,mobile:false});
    await evaluate(`document.querySelector('.scroll').style.paddingTop='500px'`);
    await settled();
    await evaluate(`document.getElementById('sp-toggle').click()`);
    await settled();
    const escaped = await measure();
    checkLayout(escaped, 'hero lower in viewport');
    check('panel escapes above overflow-hidden hero', escaped.panel.top < escaped.hero.top && Math.abs(escaped.chip.top-escaped.panel.bottom-9)<1);
    check('escaped panel remains in browser top layer', await evaluate(`(() => {
      const panel=document.getElementById('sp-panel'),box=panel.getBoundingClientRect();
      return panel.contains(document.elementFromPoint(box.left+20,box.top+20));
    })()`));
    console.log('Passed '+checks+' browser checks. At 1400x860: '+rows.toFixed(2)+' rows, '+(baseline.panel.top-baseline.bar.bottom)+' px top-bar gap.');
    console.log('Screenshots: '+work);
    await send('Browser.close');
  } finally {
    socket?.close();
    chrome.kill();
  }
})().catch(error => { console.error(error); process.exitCode=1; });
