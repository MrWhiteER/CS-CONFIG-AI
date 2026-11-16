/* GoXLR is loaded only when Sound is opened. No polling, remote URLs or jobs. */
let goxlrData = null, goxlrBusy = false, goxlrStale = false, goxlrMessage = '', goxlrPending = '';
const goxlrIcon = (kind) => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + ({
  mixer: '<rect x="2" y="4" width="20" height="16" rx="3"/><path d="M7 8v8m5-8v8m5-8v8M5 11h4m1 3h4m1-4h4"/>',
  mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M6 10v2a6 6 0 0 0 12 0v-2m-6 8v4m-4 0h8"/>',
  refresh: '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.1 6.2A8 8 0 0 1 20 12M4 12a8 8 0 0 0 13.9 5.8"/>',
  link: '<path d="m10 13 4-4m-6 6-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 3 1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0"/>',
  unlink: '<path d="m3 3 18 18M8 16l-1 1a4 4 0 0 1-6-6l3-3m12 0 1-1a4 4 0 0 1 6 6l-3 3M8 8l1-1m6 10 1-1"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
  offline: '<path d="M5 8h14v11H5zM8 5v3m8-3v3M3 3l18 18"/>',
}[kind] || '') + '</svg>';

function goxlrAction(id, icon, label, disabled = false) {
  return '<button type="button" class="btn goxlr-icon" id="' + id + '" title="' + esc(label) + '" aria-label="' + esc(label) + '"' + (disabled ? ' disabled' : '') + '>' + goxlrIcon(icon) + '</button>';
}

function renderGoxlr() {
  const box = $('goxlr-out'), refresh = $('goxlr-refresh');
  if (!box) return;
  if (refresh) { refresh.disabled = goxlrBusy; refresh.classList.toggle('goxlr-working', goxlrBusy); }
  const d = goxlrData;
  $('goxlr-card').setAttribute('aria-busy', String(goxlrBusy));
  if (!d) { box.innerHTML = '<div class="goxlr-empty">' + goxlrIcon(goxlrBusy ? 'refresh' : 'offline') + '<span>' + (goxlrBusy ? 'Looking for GoXLR…' : 'GoXLR unavailable') + '</span></div>'; }
  else if (d.backend === 'none') {
    box.innerHTML = '<div class="goxlr-empty" title="Open GoXLR Utility or the official GoXLR App, then refresh.">' + goxlrIcon('offline') + '<span>GoXLR not found</span></div>';
  } else {
    const disabled = goxlrBusy || !d.can_switch || goxlrStale;
    let html = '<div class="goxlr-backend"><span class="goxlr-dot" data-ready="' + !!d.can_switch + '"></span><span>' + (d.backend === 'utility' ? 'GoXLR Utility' : 'Official App') + '</span>';
    if (d.reason) html += '<span class="goxlr-help" tabindex="0" role="img" aria-label="' + esc(d.reason) + '" title="' + esc(d.reason) + '">' + goxlrIcon('info') + '</span>';
    html += '</div>';
    if ((d.mixers || []).length > 1) html += '<select id="goxlr-mixer" aria-label="GoXLR mixer"' + (goxlrBusy ? ' disabled' : '') + '><option value="">Choose a mixer</option>' + d.mixers.map(m => '<option value="' + esc(m.serial) + '"' + (m.serial === d.serial ? ' selected' : '') + '>' + esc(m.label) + '</option>').join('') + '</select>';
    for (const [kind, icon, title, list] of [['device','mixer','Device profile',d.profiles],['mic','mic','Mic profile',d.mic_profiles]]) {
      html += '<div class="goxlr-group"><div class="goxlr-label" title="' + title + '">' + goxlrIcon(icon) + '<span>' + title + '</span></div><div class="goxlr-profiles" role="group" aria-label="' + title + '">';
      html += (list || []).map(name => {
        const active = d.current?.[kind] === name, pending = goxlrPending === kind + ':' + name;
        const hint = goxlrStale ? 'Last read state; refresh to check your GoXLR.' : d.reason || 'Switch ' + title.toLowerCase() + ' to ' + name;
        return '<button type="button" class="goxlr-profile" data-goxlr-kind="' + kind + '" data-goxlr-name="' + esc(name) + '" aria-label="' + esc('Switch ' + title.toLowerCase() + ' to ' + name) + '" aria-pressed="' + (active && !goxlrStale) + '" title="' + esc(hint) + '"' + (disabled ? ' disabled' : '') + '><span>' + esc(name) + '</span><i class="' + (pending ? 'goxlr-working' : '') + '">' + goxlrIcon(pending ? 'refresh' : active && !goxlrStale ? 'check' : d.backend === 'official' ? 'info' : icon) + '</i></button>';
      }).join('') || '<span class="sub2">' + (d.state === 'unavailable' ? 'Connection unavailable' : 'No saved profiles') + '</span>';
      html += '</div></div>';
    }
    if (d.backend === 'official') html += '<p class="sub2 goxlr-limit">Profiles only · switching unavailable</p>';
    if (d.setup_names?.length) {
      const selected = $('goxlr-setup')?.value;
      html += '<div class="goxlr-binding"><label for="goxlr-setup" aria-label="Saved Setup" title="Link the current GoXLR profiles to a saved Setup">' + goxlrIcon('link') + '</label><select id="goxlr-setup" aria-label="Saved Setup"' + (goxlrBusy ? ' disabled' : '') + '>' + d.setup_names.map(name => '<option value="' + esc(name) + '"' + (name === selected ? ' selected' : '') + '>' + esc(name) + (d.bindings?.[name] ? ' · linked' : '') + '</option>').join('') + '</select>' + goxlrAction('goxlr-bind','link','Link current profiles to this Setup',disabled) + goxlrAction('goxlr-unbind','unlink','Unlink this Setup',goxlrBusy) + '</div>';
    }
    box.innerHTML = html;
  }
  const feedback = $('goxlr-feedback');
  feedback.textContent = goxlrMessage;
  feedback.classList.toggle('warn', goxlrStale);
}

async function loadGoxlr(force = false, serial) {
  if (goxlrBusy) return;
  if (goxlrData && !force) { renderGoxlr(); return; }
  goxlrBusy = true; goxlrMessage = ''; renderGoxlr();
  try {
    const r = await api('/api/goxlr', {serial: serial ?? goxlrData?.serial ?? ''});
    if (r.ok === false) throw Error(r.error || 'GoXLR unavailable');
    goxlrData = r; goxlrStale = false;
  } catch (e) { goxlrMessage = String(e.message || e); goxlrStale = true; }
  finally { goxlrBusy = false; renderGoxlr(); }
}

async function switchGoxlr(kind, profile) {
  if (goxlrBusy || !goxlrData?.can_switch || goxlrStale) return;
  goxlrBusy = true; goxlrPending = kind + ':' + profile; goxlrMessage = ''; renderGoxlr();
  try {
    const r = await api('/api/goxlr/switch', {backend:goxlrData.backend, serial:goxlrData.serial, kind, profile});
    if (r.ok === false) throw Error(r.error || 'Switch not confirmed. Refresh to check your GoXLR.');
    goxlrData = r; goxlrMessage = 'Profile switched';
  } catch (e) {
    // Restore the last read data, never the optimistic target. The device may
    // have received a timed-out command: disable switches until explicit refresh.
    goxlrStale = true; goxlrMessage = String(e.message || e);
  } finally {
    goxlrBusy = false; goxlrPending = ''; renderGoxlr();
    if (goxlrStale) $('goxlr-refresh')?.focus();
    else document.querySelector('[data-goxlr-kind="' + kind + '"][aria-pressed="true"]')?.focus();
  }
}

async function bindGoxlr(remove) {
  const setup = $('goxlr-setup')?.value;
  if (goxlrBusy || !setup) return;
  goxlrBusy = true; goxlrMessage = ''; renderGoxlr();
  try {
    const r = await api('/api/goxlr/bind', {setup, remove, serial:goxlrData.serial});
    if (r.ok === false) throw Error(r.error || 'Could not link this Setup.');
    Object.assign(goxlrData, r); goxlrMessage = remove ? 'Setup unlinked' : 'Setup linked';
  } catch (e) { goxlrMessage = String(e.message || e); }
  finally { goxlrBusy = false; renderGoxlr(); $('goxlr-setup')?.focus(); }
}

async function useGoxlrSetup(setup) {
  // Called only after an explicit, successful Setup selection. Not on startup,
  // account restore, save, Apply or Play. Errors do not undo the CS2 Setup.
  if (goxlrBusy) return {ok:false, error:'GoXLR is busy. Refresh Sound to check profiles.'};
  goxlrBusy = true; renderGoxlr();
  try {
    const r = await api('/api/goxlr/setup/use', {setup});
    if (r.ok === false) throw Error(r.error || 'GoXLR switch not confirmed.');
    if (!r.skipped) { goxlrData = r; goxlrStale = false; goxlrMessage = 'Setup profiles switched'; }
    return r;
  } catch (e) {
    goxlrStale = true; goxlrMessage = String(e.message || e);
    return {ok:false, error:goxlrMessage};
  } finally { goxlrBusy = false; renderGoxlr(); }
}

document.addEventListener('click', e => {
  const profile = e.target.closest('[data-goxlr-kind]');
  if (profile && !profile.disabled) switchGoxlr(profile.dataset.goxlrKind, profile.dataset.goxlrName);
  if (e.target.closest('#goxlr-refresh')) loadGoxlr(true);
  if (e.target.closest('#goxlr-bind')) bindGoxlr(false);
  if (e.target.closest('#goxlr-unbind')) bindGoxlr(true);
});
document.addEventListener('change', e => { if (e.target.id === 'goxlr-mixer') loadGoxlr(true, e.target.value); });
document.addEventListener('cs2cfg:ready', () => { if (settingsSub === 'sound') loadGoxlr(true); });
document.addEventListener('visibilitychange', () => document.documentElement.classList.toggle('goxlr-paused', document.hidden));
