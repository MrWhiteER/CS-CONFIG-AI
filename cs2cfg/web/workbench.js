/* Local tools share the app's authenticated API and existing theme tokens. */
(() => {
  let comparison = null, diagnosticToken = '', debugEvents = [], debugSpec = '';
  const byId = id => document.getElementById(id);
  const text = value => esc(String(value == null ? 'Unknown' : value));
  const button = (action, label, extra = '') => `<button class="btn" type="button" data-tools-action="${action}" ${extra}>${label}</button>`;
  const pretty = value => `<pre style="white-space:pre-wrap;overflow:auto;max-height:380px">${text(JSON.stringify(value, null, 2))}</pre>`;
  const note = (id, message) => { if (byId(id)) byId(id).textContent = message; };

  function mount() {
    const host = byId('tools-workspace');
    if (!host || host.dataset.ready) return;
    host.dataset.ready = 'true';
    host.style.cssText = 'display:grid;gap:16px;min-width:0';
    const panel = (title, description, contents) => `<section class="panel"><h2>${title}</h2><p class="sub">${description}</p>${contents}</section>`;
    host.innerHTML =
      panel('Home / Work sync', 'Compare this PC with your account’s cloud copy. If both changed, automatic sync waits for your choice. Download failures stay pending.',
        `<div class="actions">${button('sync-review', 'Compare copies')}</div><div id="tools-sync" aria-live="polite"></div>`) +
      panel('Preset A/B benchmark', 'Choose your preset in the Launcher first. Label the same map or workload, arm the next session as A or B, and play with frame capture enabled. Each measured run needs at least two minutes and 1,000 frames.',
        `<label for="tools-bench-map">Map / repeatable workload</label><input id="tools-bench-map" placeholder="Mirage offline — same route" maxlength="80"><div class="actions">${button('bench-arm-A', 'Arm next run as A')}${button('bench-arm-B', 'Arm next run as B')}${button('bench-cancel', 'Cancel armed run')}${button('bench-load', 'Refresh runs')}${button('bench-compare', 'Compare selected runs')}</div><div id="tools-bench" aria-live="polite">Load the recorded runs to begin.</div><div id="tools-bench-result"></div>`) +
      panel('Why is this value active?', 'Trace custom startup definitions, compare the saved game value, and review related changes. Manually loaded scripts can change a value after startup.',
        `<div class="actions"><label>Type <select id="tools-trace-kind"><option value="setting">Setting</option><option value="key">Key bind</option><option value="alias">Alias</option></select></label><label>Name <input id="tools-trace-name" value="sensitivity" maxlength="120"></label>${button('trace', 'Trace value')}</div><div id="tools-trace" aria-live="polite"></div>`) +
      panel('Diagnostic package', 'Preview the exact diagnostic data before exporting it. Credentials, account identifiers, private paths, personal config contents and full logs are excluded. Nothing is uploaded.',
        `<div class="actions">${button('diag-preview', 'Preview diagnostic data')}${button('diag-export', 'Export preview as ZIP', 'disabled id="tools-diag-export"')}</div><div id="tools-diag" aria-live="polite"></div>`) +
      panel('Guided practice', 'Start with CS2 closed so the normal baseline can be captured. Follow a practice checklist, then check the game’s saved values after closing it. Completion is verified from fresh game files, not from checking a box.',
        `<div id="tools-practice-form"></div><div class="actions">${button('practice-load', 'Refresh practice')}${button('practice-start', 'Start practice plan')}${button('practice-end', 'Finish and restore')}${button('practice-verify', 'Verify saved normal values')}</div><div id="tools-practice" aria-live="polite"></div>`) +
      '<p class="sub" id="tools-message" role="status" aria-live="polite"></p>';
    loadBench().catch(error => note('tools-bench', error.message));
    callPractice({}).catch(error => note('tools-practice', error.message));
  }

  async function syncReview(resolution = '') {
    const body = resolution ? {resolution, local_hash:comparison.local_hash, remote_hash:comparison.remote_hash} : {};
    const result = await api('/api/tools/sync', body);
    if (resolution) {
      note('tools-sync', result.waiting ? 'Download is still pending. Resolve the listed file permissions and compare again.' : 'Sync choice completed. Refreshing comparison…');
      return syncReview();
    }
    comparison = result.comparison;
    const d = comparison;
    byId('tools-sync').innerHTML = `<p><b>This PC ↔ ${text(d.source)}</b> · Suggested action: ${text(d.action)}</p>` +
      (d.pending ? '<p class="warn">A download is pending. Uploading the older local copy is disabled.</p>' : '') +
      (d.failed.length ? `<ul>${d.failed.map(f => `<li>${text(f.path)}: ${text(f.error)}</li>`).join('')}</ul>` : '') +
      `<p>${d.files.length} file differences · ${d.prefs.length} preference differences</p>` +
      d.files.map(f => `<details><summary>${text(f.path)} · ${text(f.status)}</summary><pre style="white-space:pre-wrap;max-height:320px;overflow:auto">${text(f.diff)}</pre></details>`).join('') +
      (d.prefs.length ? pretty(d.prefs) : '') +
      `<div class="actions">${button('sync-push', 'Use this PC’s copy', d.pending ? 'disabled' : '')}${button('sync-pull', 'Use the cloud copy', d.remote_hash ? '' : 'disabled')}</div>`;
  }

  async function loadBench() {
    const d = await api('/api/tools/benchmarks', {});
    const armed = d.plan.armed;
    byId('tools-bench').innerHTML = `<p>Current preset: <b>${text(d.context.preset)}</b>. ${armed ? `Next session is armed as <b>${text(armed.slot)}</b>: ${text(armed.map)}.` : 'No session is armed.'}</p>` +
      (d.runs.length ? `<div style="overflow:auto"><table><thead><tr><th>A</th><th>B</th><th>Recorded run</th><th>Preset / label</th><th>Duration</th><th>Measured FPS / 1% low</th></tr></thead><tbody>${d.runs.map(r => `<tr><td><input type="checkbox" data-tools-run="${text(r.stamp)}" data-side="A" aria-label="Select ${text(r.stamp)} for A"></td><td><input type="checkbox" data-tools-run="${text(r.stamp)}" data-side="B" aria-label="Select ${text(r.stamp)} for B"></td><td>${text(r.started)}</td><td>${text(r.intent)} / ${text(r.benchmark?.map || 'Unlabelled')}</td><td>${text(Math.round(r.duration || 0))}s</td><td>${text(r.overlay?.avg_fps == null ? 'No frame data' : Number(r.overlay.avg_fps).toFixed(1))} / ${text(r.overlay?.one_percent_low == null ? '—' : Number(r.overlay.one_percent_low).toFixed(1))}</td></tr>`).join('')}</tbody></table></div>` : '<p>No recorded sessions yet. Arm a run, launch CS2, repeat the workload and close the game.</p>');
  }

  async function traceValue() {
    const d = await api('/api/tools/trace', {kind:byId('tools-trace-kind').value, name:byId('tools-trace-name').value});
    byId('tools-trace').innerHTML = `<p>${text(d.explanation)}</p><p><b>Custom startup winner:</b> ${d.winner ? `${text(d.winner.value)} · ${text(d.winner.file)}:${text(d.winner.line)}` : 'No explicit custom startup definition'}</p><p>Saved game value: ${text(d.saved_game_value)} · Stock bind: ${text(d.stock)}</p>` +
      (d.definitions.length ? `<ol>${d.definitions.map(r => `<li><code>${text(r.value)}</code> — ${text(r.file)}:${text(r.line)} · ${r.startup ? 'startup' : 'deferred / manually loaded'} ${button('trace-open', 'Open file', `data-file="${text(r.file)}" data-line="${r.line}"`)}</li>`).join('')}</ol>` : '<p>No matching custom definitions.</p>') +
      (d.history.length ? '<h3>Related recorded changes</h3>' + d.history.map(h => `<p>${text(h.title)} · ${text(h.files.join(', '))} ${button('trace-undo', 'Undo this recorded change', `data-history="${text(h.id)}"`)}</p>`).join('') : '<p>No related recorded changes are available to undo.</p>');
  }

  async function callPractice(body) {
    const d = await api('/api/tools/practice', body);
    const s = d.session;
    byId('tools-practice-form').innerHTML = `<div class="actions"><label>Practice config <select id="tools-practice-file">${d.options.setups.map(v => `<option value="${text(v.file)}" ${s.file === v.file ? 'selected' : ''}>${text(v.name)}</option>`).join('')}</select></label><label>Map <select id="tools-practice-map">${d.options.maps.map(v => `<option value="${text(v.id)}" ${s.map === v.id ? 'selected' : ''}>${text(v.name)}</option>`).join('')}</select></label></div>`;
    byId('tools-practice').innerHTML = !s.status ? '<p>No practice plan is active. Choose a config and map.</p>' :
      `<p><b>${text(s.status === 'verified' ? 'Saved normal values verified' : s.status === 'restore_pending' ? 'Restoration pending verification' : 'Practice active')}</b> · ${text(s.file)}</p>` +
      `<ol>${s.steps.map((step, i) => `<li><label><input type="checkbox" data-practice-step="${i}" ${(s.done || []).includes(i) ? 'checked' : ''} ${s.status !== 'active' ? 'disabled' : ''}> ${text(step)}</label></li>`).join('')}</ol>` +
      (d.mismatches?.length ? `<p class="warn">Values still different: ${text(d.mismatches.join(', '))}. The session has not been marked verified.</p>` : '') +
      (d.lineups.length ? `<details><summary>Lineups to practise</summary><ul>${d.lineups.map(l => `<li>${text(l.name)} — ${text(l.area)} / ${text(l.type)}</li>`).join('')}</ul><p class="sub">Open the lineup overlay for pictures and placement details.</p></details>` : '');
  }

  async function debug(action) {
    if (action === 'reset') { debugEvents = []; debugSpec = ''; note('tools-debug', 'Simulation cleared.'); return; }
    const spec = Object.assign({}, sb.spec, {target:sb.target});
    const signature = JSON.stringify([spec, sb.binding]);
    if (signature !== debugSpec) debugEvents = [];
    debugSpec = signature;
    if (action === 'auto') debugEvents = [];
    else debugEvents.push(action);
    if (debugEvents.length > 24) { debugEvents.pop(); throw Error('Clear the simulation before adding more events.'); }
    const request = {spec, binding:sb.binding};
    if (action !== 'auto') request.events = debugEvents;
    const d = await api('/api/tools/script-debug', request);
    const sim = d.simulation;
    byId('tools-debug').innerHTML = `<p>${text(sim.limits)}</p>` +
      `<p><b>Held at the end:</b> ${text(sim.held.join(', ') || 'Nothing')} · <b>Simulated values:</b> ${text(JSON.stringify(sim.settings))}</p>` +
      [...sim.errors, ...sim.warnings, ...d.built.checks.filter(c => c.level === 'block').map(c => c.text)].map(v => `<p class="warn">${text(v)}</p>`).join('') +
      `<details open><summary>Command timeline (${sim.trace.length})</summary><ol style="max-height:420px;overflow:auto">${sim.trace.map(t => `<li><small>${text(t.event)} · ${text(t.kind)}</small> <code>${text(t.command)}</code>${t.held ? ` · held: ${text(t.held.join(', ') || 'nothing')}` : ''}</li>`).join('')}</ol></details>`;
  }

  document.addEventListener('click', async event => {
    if (event.target.closest('#settings-subtabs [data-sub="tools"]')) mount();
    const control = event.target.closest('[data-tools-action]');
    if (!control) return;
    const action = control.dataset.toolsAction;
    control.disabled = true;
    try {
      if (action.startsWith('debug-')) await debug(action.slice(6));
      else if (action === 'sync-review') await syncReview();
      else if (action === 'sync-open') {
        setTab('settings'); setSettingsSub('tools'); mount(); await syncReview();
      }
      else if (action === 'sync-push' || action === 'sync-pull') {
        if (comparison && await appAsk('Use this whole copy for synced settings? Review the file differences first. Local replacements are backed up.', {yes:'Use selected copy'})) await syncReview(action.slice(5));
      } else if (action === 'bench-load') await loadBench();
      else if (action.startsWith('bench-arm-')) {
        await api('/api/tools/benchmarks', {action:'arm', slot:action.slice(-1), map:byId('tools-bench-map').value});
        await loadBench();
      } else if (action === 'bench-cancel') {
        await api('/api/tools/benchmarks', {action:'cancel'}); await loadBench();
      } else if (action === 'bench-compare') {
        const selected = side => [...document.querySelectorAll(`input[data-tools-run][data-side="${side}"]:checked`)].map(v => v.dataset.toolsRun);
        const d = await api('/api/tools/benchmarks', {action:'compare', left:selected('A'), right:selected('B')});
        const c = d.comparison;
        byId('tools-bench-result').innerHTML = `<h3>Measured comparison</h3><p>B versus A: <b>${text(c.fps_change_percent)}%</b> average FPS change.</p>${pretty({A:c.A, B:c.B})}<ul>${c.warnings.map(v => `<li>${text(v)}</li>`).join('')}</ul>`;
      } else if (action === 'trace') await traceValue();
      else if (action === 'trace-open') {
        document.querySelector('.tabs [data-tab="files"]')?.click();
        await showFile(control.dataset.file, Number(control.dataset.line));
      } else if (action === 'trace-undo') {
        if (await appAsk('Undo this recorded change? It can affect all files listed for that change. Later overlapping edits will block the undo.', {yes:'Undo recorded change'})) {
          await api('/api/tools/trace/undo', {kind:byId('tools-trace-kind').value, name:byId('tools-trace-name').value, id:control.dataset.history});
          await traceValue();
        }
      } else if (action === 'diag-preview') {
        const d = await api('/api/tools/diagnostics', {});
        diagnosticToken = d.token;
        byId('tools-diag').innerHTML = pretty(d.data) + `<p>Excluded: ${text(d.excluded.join(', '))}.</p>`;
        byId('tools-diag-export').disabled = false;
      } else if (action === 'diag-export') {
        const d = await api('/api/tools/diagnostics', {action:'export', token:diagnosticToken});
        const bytes = Uint8Array.from(atob(d.data), v => v.charCodeAt(0));
        const url = URL.createObjectURL(new Blob([bytes], {type:'application/zip'}));
        const a = document.createElement('a'); a.href = url; a.download = d.filename; a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } else if (action === 'practice-load') await callPractice({});
      else if (action === 'practice-start') await callPractice({action:'start', file:byId('tools-practice-file').value, map:byId('tools-practice-map').value});
      else if (action === 'practice-end') await callPractice({action:'end'});
      else if (action === 'practice-verify') await callPractice({action:'verify'});
      note('tools-message', '');
    } catch (error) {
      note(action.startsWith('debug-') ? 'tools-debug' : 'tools-message', error.message || String(error));
    } finally { control.disabled = false; }
  });

  document.addEventListener('change', async event => {
    if (!event.target.matches('[data-practice-step]')) return;
    try { await callPractice({action:'step', index:Number(event.target.dataset.practiceStep), done:event.target.checked}); }
    catch (error) { note('tools-message', error.message); }
  });
  // Restore a saved Tools selection, including when Settings is opened later.
  const tab = document.querySelector('#settings-subtabs [data-sub="tools"]');
  const syncPopover = byId('sync-popover');
  if (syncPopover) {
    const controls = document.createElement('div'); controls.className = 'actions';
    controls.innerHTML = button('sync-open', 'Compare PC and cloud copies');
    syncPopover.append(controls);
  }
  if (tab) {
    new MutationObserver(() => { if (tab.getAttribute('aria-selected') === 'true') mount(); })
      .observe(tab, {attributes:true, attributeFilter:['aria-selected']});
    if (tab.getAttribute('aria-selected') === 'true') mount();
  }
})();
