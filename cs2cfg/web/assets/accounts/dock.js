/* The Steam website session is shared across the app, not a Stats filter. */
let dockSteam = null;
let dockSteamWaiting = 0;
let dockSteamOpening = false;
let dockSteamTimer = null;
let dockSteamRequest = null;
let dockSteamNotice = '';
let dockExpanded = false;
let dockCloseTimer;
const DOCK_ICONS = {
  steam:'<circle cx="15.5" cy="8" r="4"/><circle cx="15.5" cy="8" r="2"/><circle cx="6.5" cy="16" r="3"/><path d="m2 13 5 2m2 3 7-6M8 13l4-5"/>'
};

/* One Steam connection: Steam's website (match history) and the app's cloud
   (settings sync) are signed in together, so the dock shows a single row. */
function dockSteamRow() {
  const pc = whoData?.accounts?.find(a=>a.active);
  const web = dockSteam;
  const conn = web?.connection || {};
  const pcError = whoData?.ok === false;
  const unavailable = !!web && (web.available===false || web.state==='unavailable');
  const connected = !!conn.connected && web?.state!=='signed_out';
  const needsConnect = !!web && !unavailable && !connected;
  let detail, state = 'idle', action = '';
  if (dockSteamNotice) { detail = dockSteamNotice; state = 'error'; action = needsConnect ? 'Connect' : ''; }
  else if (dockSteamWaiting) { detail = 'Finish signing in on Steam’s page'; state = 'waiting'; }
  else if (!whoData) detail = 'Checking your account…';
  else if (pcError) { detail = 'Could not read your Steam account'; state = 'error'; }
  else if (!web) detail = 'Checking the connection…';
  else if (unavailable) detail = 'Open the app window to connect Steam';
  else if (web.state==='reading') { detail = 'Reading your match history'; state = 'reading'; }
  else if (web.state==='error' && web.linked) { detail = 'Could not read match history'; state = 'error'; action = 'Retry'; }
  else if (connected) { detail = 'Connected · '+(web.found ?? 0)+' past matches'; state = 'linked'; action = 'Manage'; }
  else if (web.state==='signed_out') { detail = 'Steam sign-in ended · connect again'; action = 'Connect'; }
  else { detail = pc ? 'Not connected yet' : 'No Steam account on this PC'; action = 'Connect'; }
  const tip = connected ? 'Match history and settings sync are on' : 'Connect once for match history and settings sync on every PC';
  return {id:'steam', label:'Steam', name:pc?.name, detail, state, action, picture:pc?.picture,
    tip, connect:needsConnect, retry:action==='Retry', disabled:dockSteamOpening, updated:web?.updated};
}

function renderAccountsDock() {
  const box = $('dock-rows');
  if (!box) return;
  const pc = whoData?.accounts?.find(a=>a.active);
  const rows = [dockSteamRow()];
  const others = (whoData?.accounts || []).filter(a=>!a.active).map((a,i)=>({
    id:'local-'+i, label:'Steam account', name:a.name || a.login || a.account,
    detail:a.signed_in?'Signed in to Steam':'Available on this PC', state:a.signed_in?'linked':'idle',
    picture:a.picture, action:'Switch', account:a.account
  }));
  rows.push(...others);
  const wanted = new Set(rows.map(r=>'dock-'+r.id));
  for (const old of [...box.children]) if (!wanted.has(old.id)) old.remove();
  for (const [index,row] of rows.entries()) {
    let button = $('dock-'+row.id);
    if (!button) {
      button = document.createElement('button');
      button.type = 'button'; button.id = 'dock-'+row.id; button.className = 'dock-row';
      if (row.account == null) button.dataset.dock = row.id;
      box.appendChild(button);
    }
    if (box.children[index] !== button) box.insertBefore(button,box.children[index] || null);
    button.style.setProperty('--dock-i',index);
    button.style.setProperty('--dock-close-i',rows.length-1-index);
    if (row.account != null) button.dataset.use = row.account;
    button.setAttribute('aria-current',String(row.id==='steam'));
    // Preserve the focused button and the animation clock across status polls.
    const content = '<span class="dock-face" aria-hidden="true"><svg viewBox="0 0 24 24">'+(DOCK_ICONS[row.id] || DOCK_ICONS.steam)+'</svg><span class="dock-picture"></span><i class="dock-dot"></i></span><span class="dock-copy"><span class="dock-name">'+esc(row.name||row.label)+'</span><span class="dock-detail">'+esc(row.name?row.label+' · '+row.detail:row.detail)+'</span></span><span class="dock-action">'+esc(row.action||'')+'</span>';
    const signature = content+'|'+(row.picture||'');
    if (button._dockContent !== signature) {
      button.innerHTML = content;
      if (row.picture && /^(https?:|data:image\/|\/)/i.test(row.picture)) paintFace(button.querySelector('.dock-picture'), {picture:row.picture});
      button._dockContent = signature;
    }
    button.dataset.state = row.state;
    button.disabled = !!row.disabled;
    const updated = row.updated ? ' · Updated '+new Date(row.updated*1000).toLocaleString() : '';
    button.title = row.label+(row.name?' · '+row.name:'')+' · '+row.detail+(row.tip?' · '+row.tip:'')+updated+(row.action?' · '+row.action:'');
    button.setAttribute('aria-label',button.title);
  }
  const main = $('dock-main');
  const mainContent = $('dock-steam').innerHTML.replace(/<img[^>]*>/g,'').replace(/<span class="dock-action">.*?<\/span>/,'').replace(/(<span class="dock-detail">).*?(<\/span>)/,'$1'+esc(rows[0].detail)+'$2') +
    '<span class="dock-cluster" aria-hidden="true">'+rows.slice(1,6).map(r=>'<i data-state="'+r.state+'"></i>').join('')+'</span><svg class="dock-chevron" viewBox="0 0 16 16" aria-hidden="true"><path d="m5 10 3-3 3 3"/></svg>';
  const mainSignature = mainContent+'|'+(pc?.picture || '');
  if (main._dockContent !== mainSignature) {
    main.innerHTML = mainContent;
    if (pc?.picture && /^(https?:|data:image\/|\/)/i.test(pc.picture)) paintFace(main.querySelector('.dock-picture'),pc);
    main._dockContent = mainSignature;
  }
  main.dataset.state = rows[0].state;
  main.setAttribute('aria-label',(pc?.name || 'Steam')+' \u00b7 '+rows[0].detail+' \u00b7 '+rows.length+' accounts');
  main.title = dockExpanded?'Hide accounts':'Show accounts';
  if (dockExpanded) dockPosition();
  $('dock-summary').textContent = rows.filter(r=>r.state==='linked'||r.state==='reading').length+' / '+rows.length;
}

function dockPosition() {
  const anchor = $('dock-main').getBoundingClientRect(), panel = $('dock-panel');
  const tight = !!document.querySelector('.app.rail-tight');
  panel.style.width = Math.min(tight?304:320,window.innerWidth-24)+'px';
  panel.style.left = Math.max(12,Math.min(tight?anchor.right+12:anchor.left,window.innerWidth-parseFloat(panel.style.width)-12))+'px';
  panel.style.bottom = Math.max(12,window.innerHeight-(tight?anchor.bottom:anchor.top)+(tight?0:10))+'px';
  panel.style.maxHeight = Math.max(120,(tight?anchor.bottom:anchor.top)-24)+'px';
}
function dockToggle(open, returnFocus = true) {
  const panel = $('dock-panel'), main = $('dock-main');
  if (!panel || dockExpanded === open) return;
  clearTimeout(dockCloseTimer);
  dockExpanded = open;
  main.setAttribute('aria-expanded',String(open));
  main.title = open?'Hide accounts':'Show accounts';
  if (open) {
    dockPosition(); panel.showPopover(); panel.inert = false;
    panel.getBoundingClientRect(); panel.classList.add('is-open');
    panel.querySelector('button:not(:disabled)')?.focus({preventScroll:true});
  } else {
    panel.classList.remove('is-open'); panel.inert = true;
    if (returnFocus) main.focus({preventScroll:true});
    dockCloseTimer = setTimeout(()=>{if (!dockExpanded) panel.hidePopover();},matchMedia('(prefers-reduced-motion: reduce)').matches?0:760);
  }
}
window.addEventListener('resize',()=>{if (dockExpanded) dockPosition();});
document.addEventListener('keydown',e=>{
  if (e.key==='Escape' && dockExpanded) { e.preventDefault(); e.stopImmediatePropagation(); dockToggle(false); }
},true);

function dockPauseMotion() {
  document.documentElement.classList.toggle('dock-paused', document.hidden);
}

function dockScheduleSteam() {
  clearTimeout(dockSteamTimer);
  if (document.hidden) return;
  dockSteamTimer = setTimeout(loadDockSteam, dockSteamWaiting || dockSteam?.state==='reading' ? 3000 : 30000);
}

function loadDockSteam() {
  if (dockSteamRequest) return dockSteamRequest;
  dockSteamRequest = (async()=>{
    try {
      const wasReading = dockSteam?.state==='reading';
      dockSteam = await api('/api/stats/steam',{});
      if (dockSteam.connection?.connected && dockSteam.state!=='signed_out') {
        const wasWaiting = !!dockSteamWaiting;
        dockSteamWaiting = 0;
        dockSteamNotice = '';
        if (wasWaiting && typeof loadCloud==='function') loadCloud();
        if (wasWaiting || (wasReading && dockSteam.state==='done')) loadFaceit();
      }
    } catch (err) {
      dockSteam = {...dockSteam, state:'error', error:String(err.message||err)};
    }
    if (dockSteamWaiting && Date.now() >= dockSteamWaiting) {
      dockSteamWaiting = 0;
      dockSteamNotice = 'Steam sign-in was not finished · try again';
    }
    renderAccountsDock();
    dockScheduleSteam();
  })().finally(()=>{dockSteamRequest=null;});
  return dockSteamRequest;
}

document.addEventListener('click',async e=>{
  if (e.target.closest('#dock-main')) { dockToggle(!dockExpanded); return; }
  if (dockExpanded && !e.target.closest('#dock-panel')) dockToggle(false);
  if (e.target.closest('#dock-panel [data-use]')) { dockToggle(false); return; }
  const button = e.target.closest('[data-dock]');
  if (!button) return;
  const row = dockSteamRow();
  if (row.connect || row.retry) {
    if (dockSteamWaiting || dockSteamOpening) return;
    dockSteamOpening = true; dockSteamNotice = ''; renderAccountsDock();
    try {
      const result = row.retry ? await api('/api/stats/steam',{action:'sync'}) : await api('/api/steam/connect',{});
      if (result.ok===false || result.error) throw Error(result.error||'Steam could not be opened');
      if (result.opened) dockSteamWaiting = Date.now()+10*60*1000;
    } catch (err) { dockSteamNotice = String(err.message||err); }
    dockSteamOpening = false;
    await loadDockSteam();
    return;
  }
  if (dockSteamWaiting) return;
  dockToggle(false);
  setTab('settings'); setSettingsSub('steam'); whoOpen(true); $('who')?.focus();
});
document.addEventListener('visibilitychange',()=>{
  dockPauseMotion();
  if (!document.hidden) loadDockSteam();
  else clearTimeout(dockSteamTimer);
});
document.addEventListener('cs2cfg:ready',()=>{dockPauseMotion(); renderAccountsDock(); loadDockSteam();});
