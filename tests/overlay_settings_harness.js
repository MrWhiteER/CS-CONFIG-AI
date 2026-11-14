// Production Settings renderer, with a minimal DOM and no browser dependencies.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('cs2cfg/web/index.html', 'utf8');
for (const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) {
  new vm.Script(match[1]);
}
const start = html.indexOf('function overlaySettingsSample(mode)');
const end = html.indexOf('\ndocument.addEventListener("click", async e => {', start);
assert(start > 0 && end > start);
const elements = {'overlay-out': {}, 'overlay-said': {}};
let writes = 0, timers = 0;
const buttons = [{}, {}];
const context = vm.createContext({
  $: id => elements[id], esc: value => String(value ?? '').replaceAll('<', '&lt;'),
  URLSearchParams, location: {search: ''},
  document: {querySelectorAll: () => buttons},
  api: () => { writes++; throw Error('Unexpected request'); },
  setTimeout: () => timers++, setInterval: () => timers++,
});
vm.runInContext(html.slice(start, end), context);
const render = mode => {
  vm.runInContext(`renderOverlay(overlaySettingsSample(${JSON.stringify(mode)}))`, context);
  return elements['overlay-out'].innerHTML;
};
let output = render('off');
for (const title of ['Performance overlay', 'HUD', 'Panel', 'Behaviour', 'Frame stats']) {
  assert(output.includes(`<h2>${title}</h2>`));
}
assert(output.includes('Enable the overlay and start CS2'));
assert(!output.includes('286.4'));
output = render('waiting');
assert(output.includes('Start CS2, then refresh'));
assert(!output.includes('286.4'));
assert(output.includes('Dismiss reminder'));
output = render('live');
assert(output.includes('286.4'));
assert(output.includes('Frame capture ready'));
assert(!output.includes('Dismiss reminder'));
context.location.search = '?overlayPreview=off';
render('off');
assert(buttons.every(b => b.disabled));
assert(elements['overlay-said'].textContent.includes('Sample data'));
assert.equal(writes, 0);
assert.equal(timers, 0);
console.log('Settings renderer: off, waiting, live, preview and syntax passed');
