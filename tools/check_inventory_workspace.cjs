const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {execFileSync} = require('node:child_process');

const root = path.resolve(__dirname, '..');
const page = fs.readFileSync(path.join(root, 'cs2cfg/web/index.html'), 'utf8');
const start = page.indexOf('/* Inventory watches');
const end = page.indexOf('window.addEventListener("resize"', start);
assert(start >= 0 && end > start);
const logic = page.slice(start, end);
const fixture = `
const $ = id => document.getElementById(id);
const esc = x => String(x ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const account = 'owner';
const currentAccount = () => account;
let activeTab = 'inventory';
function status() {}
const icon = 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2230%22 height=%2230%22%3E%3Ccircle cx=%2215%22 cy=%2215%22 r=%2212%22 fill=%22orange%22/%3E%3C/svg%3E';
const item = (asset_id,name,type,marketable) => ({asset_id,name,type,marketable,icon,rarity:'Rare',exterior:'',category:'',weapon:''});
let listings = [item('99','Music Kit | Artist, Song','Music Kit',true), item('101','Sticker | Orange','Sticker',false)];
let attempts = 0, networkDown = false;
async function api(route, body) {
  if (route === '/api/inventory') {
    attempts++;
    if (body.account !== account || body.force !== true) throw Error('Incorrect inventory request');
    return networkDown ? {ok:false,error:'Steam unavailable'} : {ok:true,steam_id:'76561198000000000',items:listings,count:listings.length};
  }
  if (route === '/api/skins/catalog') return {ok:true,items:[{kind:'music',paintkit:'5',skin_name:'Song',display_name:'Music Kit | Artist, Song'}]};
  if (route === '/api/skins/music') return {kits:[{kit:'5',parts:[{label:'MVP song',part:'mvp'}]}]};
  throw Error(route);
}
`;
const checks = `
(async () => {
  const check = (condition, name) => { if (!condition) throw Error(name); };
  document.querySelector('.boot-screen')?.remove();
  document.documentElement.dataset.boot = 'ready';
  document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.toggle('hidden',panel.dataset.panel !== 'inventory'));
  await loadInventory();
  check(invRows.map(x => x.asset_id).join(',') === '101,99','Newest initial order preserves full asset IDs');
  await loadInventory();
  check(attempts === 1,'Background reads respect the refresh interval');
  listings = [...listings,item('125','AK-47 | Redline','Rifle',true)];
  await loadInventory(true);
  check(invRows[0].asset_id === '125','Newly acquired skin appears first');
  $('inv-search').value='redline';$('inv-search').dispatchEvent(new Event('input'));
  check(invRows.length === 1 && invRows[0].asset_id === '125','Search filters inventory');
  $('inv-select-page').click();
  $('inv-search').value='';$('inv-search').dispatchEvent(new Event('input'));
  $('inv-select-page').click();
  $('inv-review').click();
  const destinations = [...$('inv-sale').querySelectorAll('a')].map(a => a.href);
  check(destinations.length === 2 && destinations.every(url => url.startsWith('https://steamcommunity.com/profiles/76561198000000000/inventory/#730_2_')),'Multiple marketable assets form a Steam review batch');
  networkDown = true;
  await loadInventory(true);
  check(invRows.length === 3 && $('inv-status').textContent.includes('last successful'),'Temporary Steam failure preserves the inventory');
  await loadInventory();
  check(attempts === 3,'Temporary errors back off');
  await previewInventoryItem(listings[0]);
  check($('skin-viewer-body').querySelector('[data-mk-kit="5"][data-mk-part="mvp"]'),'Inventory shares the music preview controls');
  closeSkinViewer();
  await previewInventoryItem(listings[1]);
  const stage = $('skin-viewer-body').querySelector('.sticker-stage');
  stage.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
  check(stage.style.getPropertyValue('--ry') === '5deg','Sticker rotates in 3D with arrow keys');
  const lighting = $('skin-viewer-body').querySelector('select');
  const before = stage.style.getPropertyValue('--light');
  lighting.value = 'Nuke'; lighting.dispatchEvent(new Event('change'));
  check(stage.style.getPropertyValue('--light') !== before,'Map lighting preset changes the preview');
  closeSkinViewer();
  $('inv-clear').click();
  check($('inv-sale').hidden && invSelected.size === 0,'Clearing the selection closes the sale batch');
  document.body.insertAdjacentHTML('beforeend','<pre id="inventory-result">passed</pre>');
})().catch(error => {
  const result = document.createElement('pre');
  result.id = 'inventory-result';
  result.textContent = error.message;
  document.body.append(result);
});
`;

const tempRoot = fs.realpathSync(os.tmpdir());
const temp = fs.mkdtempSync(path.join(tempRoot, 'cs2-inventory-check-'));
const chrome = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
try {
  const src = page.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'')
    .replace('<head>', '<head><base href="' + pathToFileURL(path.join(root,'cs2cfg/web')+path.sep).href + '">')
    .replace('</body>', () => '<script>' + fixture + logic + checks + '</script></body>');
  const preview = path.join(temp,'inventory.html');
  fs.writeFileSync(preview,src);
  const output = execFileSync(chrome, ['--headless','--no-sandbox','--disable-gpu','--allow-file-access-from-files',
    '--user-data-dir='+path.join(temp,'chrome'),'--virtual-time-budget=8000','--dump-dom',pathToFileURL(preview).href],
    {encoding:'utf8',maxBuffer:4e6,stdio:['ignore','pipe','ignore']});
  const result = output.match(/<pre id="inventory-result">([^<]*)<\/pre>\s*<\/body>/)?.[1];
  assert.equal(result,'passed',result || 'Fixture did not finish');
  console.log('Inventory browser checks passed');
} finally {
  const resolved = fs.realpathSync(temp);
  if (path.dirname(resolved) === tempRoot && path.basename(resolved).startsWith('cs2-inventory-check-')) {
    fs.rmSync(resolved,{recursive:true,force:true});
  }
}
