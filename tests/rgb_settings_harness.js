// Exercise production lighting UI with controlled requests and a minimal DOM.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('cs2cfg/web/index.html', 'utf8');
for (const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) new vm.Script(match[1]);
const start = html.indexOf('// Both lighting entry points');
const end = html.indexOf('// Read-only screenshot fixtures', start);
assert(start > 0 && end > start);
const elements = Object.fromEntries(['rgb-out', 'kb-rgb-enabled', 'kb-rgb-status', 'rgb-brightness-value'].map(id => [id, {}]));
const handlers = {}, calls = [], timers = [];
const snapshot = (enabled = false) => ({ok: true, enabled,
  settings: {rgb_enabled: enabled, rgb_free: 'dim', rgb_brightness: 100},
  providers: [{name: 'Razer Chroma', active: enabled, why: enabled ? '' : '<not running>'}]});
let response = snapshot();
const context = vm.createContext({
  $: id => elements[id], esc: x => String(x).replaceAll('<', '&lt;'),
  document: {addEventListener: (type, fn) => handlers[type] = fn},
  api: async (path, body) => { calls.push({path, body}); return typeof response === 'function' ? response(path, body) : response; },
  setTimeout: (fn, delay) => { timers.push({fn, delay}); return timers.length; },
  clearTimeout: () => {},
});
vm.runInContext(html.slice(start, end), context);
const run = source => vm.runInContext(source, context);
(async () => {
  run('renderRgb()');
  assert.equal(elements['kb-rgb-enabled'].disabled, true);
  await run('loadRgb()');
  assert.equal(calls[0].path, '/api/rgb');
  assert.equal(elements['kb-rgb-enabled'].checked, false);
  assert.equal(elements['kb-rgb-enabled'].disabled, false);
  assert(elements['rgb-out'].innerHTML.includes('not found'));
  assert(elements['rgb-out'].innerHTML.includes('&lt;not running>'));
  response = snapshot(true);
  await run('saveRgb({rgb_enabled: true})');
  assert.equal(calls.at(-1).path, '/api/rgb/settings');
  assert.equal(calls.at(-1).body.rgb_enabled, true);
  assert.equal(elements['kb-rgb-enabled'].checked, true);
  assert.equal(elements['kb-rgb-status'].textContent, 'Razer Chroma · live');
  assert.equal(timers.at(-1).delay, 2000);
  await timers.at(-1).fn();
  assert.equal(calls.at(-1).path, '/api/rgb');
  const beforeInput = calls.length;
  handlers.input({target: {id: 'rgb-brightness', value: '37'}});
  assert.equal(elements['rgb-brightness-value'].textContent, '37%');
  assert.equal(calls.length, beforeInput);
  handlers.change({target: {id: 'rgb-brightness', value: '37', matches: () => false}});
  assert.equal(calls.at(-1).body.rgb_brightness, 37);
  await new Promise(resolve => setImmediate(resolve));
  handlers.click({target: {closest: () => ({dataset: {rgbFree: 'off'}})}});
  assert.equal(calls.at(-1).body.rgb_free, 'off');
  await new Promise(resolve => setImmediate(resolve));
  response = path => path.endsWith('/settings') ? {ok: false, error: 'Save failed'} : snapshot(true);
  await run('saveRgb({rgb_enabled: false})');
  assert.equal(elements['kb-rgb-enabled'].checked, true);
  assert.equal(elements['kb-rgb-enabled'].disabled, false);
  assert.equal(elements['kb-rgb-status'].textContent, 'Save failed');
  response = () => { throw Error('Offline'); };
  await run('loadRgb()');
  assert.equal(elements['kb-rgb-enabled'].checked, true);
  assert.equal(elements['kb-rgb-status'].textContent, 'Offline');
  // An old status response must never replace a newer saved setting.
  let finishRead;
  response = () => new Promise(resolve => { finishRead = resolve; });
  const oldRead = run('loadRgb()');
  response = snapshot(false);
  await run('saveRgb({rgb_enabled: false})');
  finishRead(snapshot(true));
  await oldRead;
  assert.equal(elements['kb-rgb-enabled'].checked, false);
  response = snapshot(true);
  response.providers = [{name: 'SteelSeries GG', active: false, why: 'Start GG'}];
  await run('loadRgb()');
  assert.equal(elements['kb-rgb-status'].textContent, 'Start GG');
  console.log('Lighting: shared state, saves, delayed refresh, slider release, errors and stale reads passed');
})().catch(err => { console.error(err); process.exitCode = 1; });
