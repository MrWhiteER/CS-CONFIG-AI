/* One completion-driven refresh per second. Hiding cancels every pending task. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const preview = new URLSearchParams(location.search).get('preview') === '1';
  let active = false, requested = false, generation = 0, seconds = 120;
  let performanceTimer = null, regionTimer = null, controller = null, latest = null;
  let graphTimer = null, lastGraphAt = -Infinity;
  let regionBusy = false;
  const number = (n, unit = '') => Number.isFinite(n) ? n.toFixed(1) + unit : '—';
  const text = (id, value) => { $(id).textContent = value; };

  async function api(path, body = {}, signal = controller?.signal) {
    if (preview) throw new Error('Preview changes are disabled');
    const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json',
      'X-CS2CFG-Token':window.overlayToken}, body:JSON.stringify(body), signal});
    const result = await response.json();
    if (!response.ok || result.ok === false) throw new Error(result.error || 'Request failed');
    return result;
  }

  function report(error) {
    if (active && error.name !== 'AbortError') text('error', error.message || String(error));
  }

  function graph(history, ready) {
    if (!active) return;
    clearTimeout(graphTimer); graphTimer = null;
    const wait = 100 - (performance.now() - lastGraphAt);
    if (wait > 0) {
      graphTimer = setTimeout(() => graph(history, ready), Math.ceil(wait));
      return;
    }
    lastGraphAt = performance.now();
    const svg = $('graph'), ns = 'http://www.w3.org/2000/svg';
    svg.replaceChildren();
    const node = (tag, attrs, label) => {
      const el = document.createElementNS(ns, tag);
      for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
      if (label != null) el.textContent = label;
      svg.appendChild(el); return el;
    };
    const now = preview ? previewData.now : Date.now() / 1000;
    const samples = ready ? history.filter(s => s.at >= now - seconds && Number.isFinite(s.frame_time_ms)) : [];
    const max = Math.max(10, ...samples.map(s => s.frame_time_ms)) * 1.1;
    for (let i = 0; i <= 4; i++) {
      const y = 8 + i * 40;
      node('line', {x1:38, x2:618, y1:y, y2:y, class:'grid'});
      node('text', {x:0, y:y + 4}, (max * (1 - i / 4)).toFixed(0));
    }
    if (!samples.length) node('text', {x:75, y:90}, ready ? 'Waiting for frame data' : 'Frame stats unavailable');
    // Break the path at missing intervals instead of inventing frame data.
    let previous = null;
    const path = samples.map(s => {
      const x = 38 + Math.max(0, Math.min(1, (s.at - now + seconds) / seconds)) * 580;
      const y = 168 - s.frame_time_ms / max * 160;
      const move = previous === null || s.at - previous > 2;
      previous = s.at;
      return `${move ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(' ');
    node('path', {d:path, class:'trace'});
    text('range-label', `${seconds / 60} minutes ago`);
  }

  function render(data) {
    latest = data;
    const current = data.current || {}, summary = data.summary || {}, ready = data.frame_capture_ready;
    text('shortcut', data.settings.overlay_panel_hotkey);
    text('capture-state', preview ? 'Sample session' : data.game_running ? 'Current session' : 'Waiting for CS2');
    text('fps', ready ? number(current.fps) : '—');
    text('average', ready ? number(summary.avg_fps) : '—');
    text('low', ready ? number(summary.one_percent_low) : '—');
    text('worst', ready ? number(summary.worst_frame_ms, ' ms') : '—');
    text('cpu', number(current.cpu_percent, '%'));
    text('gpu', number(current.gpu_percent, '%'));
    text('temp', number(current.gpu_temp_c, ' °C'));
    $('frame-hint').hidden = !data.frame_capture_hint;
    $('frame-hint').querySelector('span').textContent = data.frame_capture_hint || '';
    $('dismiss').hidden = !data.frame_capture_hint_dismissible;
    text('notice', [data.notice, data.error, data.hud_warning, data.panel_warning].filter(Boolean).join(' · '));
    graph(data.history || [], ready);
    const rows = (data.events || []).slice().sort((a,b) => b.at - a.at);
    $('events').replaceChildren();
    if (!rows.length) {
      const row = $('events').insertRow(), cell = row.insertCell();
      cell.colSpan = 3; cell.textContent = 'No events this session';
    }
    for (const event of rows) {
      const row = $('events').insertRow();
      const values = [new Date(event.at * 1000).toLocaleTimeString(), number(event.duration_ms, ' ms'),
        event.type === 'not_responding' ? 'Not responding' : 'Frame spike'];
      for (const value of values) row.insertCell().textContent = value;
    }
  }

  function options(id, entries, value, label, selected) {
    const select = $(id);
    select.replaceChildren();
    for (const item of entries) {
      const option = document.createElement('option');
      option.value = value(item); option.textContent = label(item);
      option.selected = selected(item); select.appendChild(option);
    }
    if (!entries.length) {
      const option = document.createElement('option'); option.textContent = 'None saved'; select.appendChild(option);
    }
    select.disabled = preview || !entries.length;
  }

  async function profiles(epoch) {
    const results = await Promise.allSettled([api('/api/setups'), api('/api/cfg/layouts/profiles')]);
    if (!active || epoch !== generation) return;
    const [setup, layout] = results;
    if (setup.status === 'fulfilled') {
      const d = setup.value;
      options('setups', d.setups || [], s => s.name, s => s.name, s => s.name === d.live);
      $('use-setup').disabled = $('setups').disabled;
    } else report(setup.reason);
    if (layout.status === 'fulfilled') {
      options('layouts', layout.value.profiles || [], p => p.file, p => p.label, p => p.active);
      $('use-layout').disabled = $('layouts').disabled;
    } else text('profile-note', layout.reason.message);
  }

  async function refreshPerformance(epoch) {
    try {
      const data = await api('/api/overlay', {seconds:600});
      if (active && epoch === generation) render(data);
    } catch (error) { report(error); }
    if (active && epoch === generation) performanceTimer = setTimeout(() => refreshPerformance(epoch), 1000);
  }

  function region(data, epoch) {
    if (!active || epoch !== generation) return;
    clearTimeout(regionTimer); regionTimer = null;
    text('region-text', data.text);
    $('region-controls').hidden = !data.available;
    if (!data.available) return;
    regionBusy = Boolean(data.status.busy);
    const selected = $('regions').value || data.status?.firewall?.code;
    options('regions', data.regions || [], r => r.code,
      r => `${r.city}, ${r.country} · ${number(r.ping_ms, ' ms')} · loss ${number(r.loss)} · ${r.status || ''}`,
      r => r.code === selected);
    $('lock-region').disabled = preview || data.status.busy || $('regions').disabled;
    $('unlock-region').disabled = preview || data.status.busy;
    if (data.poll) regionTimer = setTimeout(async () => {
      try { region(await api('/api/overlay/panel'), epoch); } catch (error) { report(error); }
    }, 1000);
  }

  function stop() {
    active = false; generation++;
    clearTimeout(performanceTimer); clearTimeout(regionTimer);
    clearTimeout(graphTimer); graphTimer = null;
    performanceTimer = regionTimer = null;
    controller?.abort(); controller = null;
  }

  async function start() {
    if (active || document.hidden) return;
    active = true;
    const epoch = ++generation;
    controller = new AbortController();
    if (preview) { renderPreview(); return; }
    refreshPerformance(epoch);
    profiles(epoch).catch(report);
    try { region(await api('/api/overlay/panel', {action:'open'}), epoch); } catch (error) { report(error); }
  }

  window.overlayPanelActive = value => { requested = value; if (value) start(); else stop(); };
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stop(); else if (requested) start();
  });
  window.addEventListener('pagehide', stop);

  document.querySelectorAll('[data-range]').forEach(button => button.addEventListener('click', () => {
    seconds = Number(button.dataset.range);
    document.querySelectorAll('[data-range]').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
    if (latest) graph(latest.history || [], latest.frame_capture_ready);
  }));

  async function action(button, fn) {
    if (!active || preview) return;
    button.disabled = true; text('error', '');
    const epoch = generation;
    try { await fn(epoch); } catch (error) { report(error); }
    finally {
      if (active && epoch === generation) {
        if (button.id.endsWith('-region')) {
          $('lock-region').disabled = regionBusy || $('regions').disabled;
          $('unlock-region').disabled = regionBusy;
        } else button.disabled = false;
      }
    }
  }
  $('use-setup').onclick = () => action($('use-setup'), async epoch => {
    await api('/api/setups/act', {do:'use', name:$('setups').value});
    if (active && epoch === generation) text('profile-note', 'Setup selected for the app’s next Apply.');
  });
  $('use-layout').onclick = () => action($('use-layout'), async epoch => {
    const data = await api('/api/cfg/layouts/apply', {file:$('layouts').value});
    if (active && epoch === generation) text('profile-note', data.apply_keys?.length ?
      `Press ${data.apply_keys.join(' / ')} in game to load it` : 'No Apply Saved Settings key is bound. Set one in the Keyboard tab.');
  });
  $('dismiss').onclick = () => action($('dismiss'), async epoch => {
    const data = await api('/api/overlay/settings', {overlay_sign_out_hint_dismissed:true});
    if (active && epoch === generation) render(data);
  });
  for (const [id, operation] of [['lock-region','lock'], ['unlock-region','unlock']]) {
    $(id).onclick = () => action($(id), async epoch => {
      const data = await api('/api/overlay/panel', {action:operation, code:$('regions').value});
      region(data, epoch);
    });
  }
  $('close').onclick = () => {
    if (preview) { window.overlayPanelActive(false); return; }
    stop(); requested = false;
    api('/api/overlay/panel', {action:'close'}, null).catch(() => {});
  };
  document.addEventListener('keydown', event => { if (event.key === 'Escape') $('close').click(); });
  document.querySelectorAll('a').forEach(link => link.addEventListener('click', event => {
    if (preview) { event.preventDefault(); return; }
    event.preventDefault();
    const operation = link.id === 'keyboard' ? 'keyboard' : 'setup';
    api('/api/overlay/panel', {action:operation}).catch(report);
  }));

  const previewData = (() => {
    if (!preview) return null;
    const now = Date.now() / 1000;
    return {now, settings:{overlay_panel_hotkey:'Ctrl+Alt+P'}, game_running:true, frame_capture_ready:true,
      frame_capture_hint:'', current:{fps:287, cpu_percent:32, gpu_percent:56, gpu_temp_c:66},
      summary:{avg_fps:281, one_percent_low:182, worst_frame_ms:24.1},
      history:Array.from({length:600}, (_,i) => ({at:now - 599 + i,
        frame_time_ms:i % 97 === 0 ? 20.5 : 3.55 + Math.sin(i * 2.7) * .7 + Math.cos(i * .9) * .4})),
      events:[{at:now-18,duration_ms:24.1,type:'frame_spike'},
        {at:now-73,duration_ms:212.4,type:'not_responding'},
        {at:now-116,duration_ms:18.9,type:'frame_spike'}]};
  })();
  function renderPreview() {
    $('preview').hidden = false;
    render(previewData);
    options('setups', [{name:'Balanced'}], s => s.name, s => s.name, () => true);
    options('layouts', [{file:'competitive',label:'Competitive'}], p => p.file, p => p.label, () => true);
    text('profile-note', 'Press F8 in game to load it');
  }
  if (preview) window.overlayPanelActive(true);
})();
