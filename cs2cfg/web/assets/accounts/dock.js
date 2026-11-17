/* The Steam website session is shared across the app, not a Stats filter. */
let dockSteam = null;
let dockSteamWaiting = 0;
let dockSteamOpening = false;
let dockSteamTimer = null;
let dockSteamRequest = null;
let dockSteamNotice = '';
const DOCK_ICONS = {
  steam:'<circle cx="15.5" cy="8" r="4"/><circle cx="15.5" cy="8" r="2"/><circle cx="6.5" cy="16" r="3"/><path d="m2 13 5 2m2 3 7-6M8 13l4-5"/>',
  web:'<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
  cloud:'<path d="M7 18h11a4 4 0 0 0 0-8 6 6 0 0 0-11-2 5 5 0 0 0 0 10Z"/><path d="m9 13 2 2 4-4"/>',
  faceit:'<path d="M3 10h12l5-5v14L3 10Z"/>'
};

function renderAccountsDock() {
  const box = $('dock-rows');
  if (!box) return;
  const pc = whoData?.accounts?.find(a=>a.active);
  const web = dockSteam;
  const cloud = cloudData;
  const player = fcData?.player;
  const pcError = whoData?.ok === false;
  const rows = [
    {id:'steam', label:'Steam (this PC)', name:pc?.name, detail:pc ? (whoData.following?'Following Steam':'Pinned account') : whoData ? (pcError?'Could not read account':'No Steam account') : 'Checking account…', state:pc?'linked':pcError?'error':'idle', action:pc?'':'Open', picture:pc?.picture, error:whoData?.error},
    {id:'web', label:'Steam web', detail:dockSteamNotice || (dockSteamWaiting?'Finish sign-in in Steam':!web?'Checking session…':web.state==='reading'?'Reading match history':web.error?web.error:web.state==='unavailable'||web.available===false?'Open in the desktop app':web.state==='signed_out'?'Session expired':web.linked?'Match history · '+(web.found ?? 0)+' matches':'Older CS2 match history'), state:dockSteamWaiting?'waiting':web?.state==='reading'?'reading':web?.error||web?.state==='error'?'error':web?.linked&&web.state!=='signed_out'?'linked':'idle', action:dockSteamWaiting?'':web?.state==='reading'?'':web?.state==='error'&&web.linked?'Retry':web && (!web.linked||web.state==='signed_out')?'Connect':'', disabled:!web||web.available===false||web.state==='unavailable'||dockSteamOpening, updated:web?.updated},
    {id:'cloud', label:'Cloud sync', name:cloud?.signed_in?(cloud.name||cloud.display_name||cloud.email||'Signed in'):null, detail:!cloud?'Checking account…':cloud.error?'Cloud unavailable':cloud.signed_in?'Signed in':cloud.configured===false?'Cloud not configured':'Settings across PCs', state:cloud?.error?'error':cloud?.signed_in?'linked':'idle', action:cloud&&!cloud.signed_in&&cloud.configured!==false?'Sign in':'', picture:cloud?.signed_in?(cloud.avatar||cloud.avatar_url):null, error:cloud?.error},
    {id:'faceit', label:'FACEIT', name:player?.nickname, detail:player?(player.level?'Following · Level '+player.level:'Following player'):fcData?.error?'Could not read player':fcData?'ELO & match history':'Checking player…', state:fcData?.error?'error':player?'linked':'idle', action:fcData&&!player?'Follow':'', picture:player?.avatar, error:fcData?.error}
  ];
  for (const row of rows) {
    let button = $('dock-'+row.id);
    if (!button) {
      button = document.createElement('button');
      button.type = 'button'; button.id = 'dock-'+row.id; button.className = 'dock-row';
      button.dataset.dock = row.id;
      box.appendChild(button);
    }
    // Preserve the focused button and the animation clock across status polls.
    const content = '<span class="dock-face" aria-hidden="true"><svg viewBox="0 0 24 24">'+DOCK_ICONS[row.id]+'</svg><span class="dock-picture"></span><i class="dock-dot"></i></span><span class="dock-copy"><span class="dock-name">'+esc(row.name||row.label)+'</span><span class="dock-detail">'+esc(row.name?row.label+' · '+row.detail:row.detail)+'</span></span><span class="dock-action">'+esc(row.action||'')+'</span>';
    const signature = content+'|'+(row.picture||'');
    if (button._dockContent !== signature) {
      button.innerHTML = content;
      if (row.picture && /^(https?:|data:image\/|\/)/i.test(row.picture)) paintFace(button.querySelector('.dock-picture'), {picture:row.picture});
      button._dockContent = signature;
    }
    button.dataset.state = row.state;
    button.disabled = !!row.disabled;
    const updated = row.updated ? ' · Updated '+new Date(row.updated*1000).toLocaleString() : '';
    button.title = row.label+(row.name?' · '+row.name:'')+' · '+(row.error||row.detail)+updated+(row.action?' · '+row.action:'');
    button.setAttribute('aria-label',button.title);
  }
  $('dock-summary').textContent = [!!pc, !!web?.linked && web.state!=='signed_out', !!cloud?.signed_in, !!player].filter(Boolean).length+' / 4';
}

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
      if (dockSteam.linked && dockSteam.state!=='signed_out') {
        const wasWaiting = !!dockSteamWaiting;
        dockSteamWaiting = 0;
        dockSteamNotice = '';
        if (wasWaiting || (wasReading && dockSteam.state==='done')) loadFaceit();
      }
    } catch (err) {
      dockSteam = {...dockSteam, state:'error', error:String(err.message||err)};
    }
    if (dockSteamWaiting && Date.now() >= dockSteamWaiting) {
      dockSteamWaiting = 0;
      dockSteamNotice = 'Sign-in timed out · try again';
    }
    renderAccountsDock();
    dockScheduleSteam();
  })().finally(()=>{dockSteamRequest=null;});
  return dockSteamRequest;
}

document.addEventListener('click',async e=>{
  const button = e.target.closest('[data-dock]');
  if (!button) return;
  if (button.dataset.dock==='steam') {
    setTab('settings'); setSettingsSub('steam'); whoOpen(true); $('who')?.focus();
  } else if (button.dataset.dock==='cloud') {
    setTab('settings'); setSettingsSub('account');
    $('account-out')?.scrollIntoView({block:'nearest'});
    // The existing entry owns all authentication options and polling.
    setTimeout(()=>$('account-out')?.querySelector('button')?.focus(),0);
  } else if (button.dataset.dock==='faceit') {
    setTab('faceit');
    // setTab can trigger an async refresh; the dashboard preserves this draft/focus.
    const target = $('fc-nick') || $('fc-refresh');
    target?.scrollIntoView({block:'nearest'}); target?.focus();
  } else if (button.dataset.dock==='web' && !dockSteamWaiting && !dockSteamOpening && dockSteam?.state!=='reading' && (!dockSteam?.linked||dockSteam?.state==='signed_out'||dockSteam?.state==='error')) {
    dockSteamOpening = true; dockSteamNotice = ''; renderAccountsDock();
    try {
      const action = dockSteam?.linked && dockSteam.state==='error' ? 'sync' : 'signin';
      const result = await api('/api/stats/steam',{action});
      if (result.ok===false || result.available===false || result.state==='unavailable' || result.error) throw Error(result.error||'Open in the desktop app');
      if (action==='signin') dockSteamWaiting = Date.now()+10*60*1000;
    } catch (err) { dockSteamNotice = String(err.message||err); }
    dockSteamOpening = false;
    await loadDockSteam();
  } else if (button.dataset.dock==='web' && dockSteam?.linked && !dockSteamWaiting) {
    setTab('faceit');
  }
});
document.addEventListener('visibilitychange',()=>{
  dockPauseMotion();
  if (!document.hidden) loadDockSteam();
  else clearTimeout(dockSteamTimer);
});
document.addEventListener('cs2cfg:ready',()=>{dockPauseMotion(); renderAccountsDock(); loadDockSteam();});
