/* Region controls extend the existing sp-* widget. All values are escaped. */
function createServerRegionLock({panel, chip, api, esc, tone, changed}) {
  const lockIcon = '<svg class="sp-glyph" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/></svg>';
  const info = document.createElement('div');
  info.className = 'sl-info'; info.id = 'sp-lock-info';
  panel.querySelector('.sp-list').after(info);
  const dialog = document.createElement('dialog');
  dialog.className = 'sl-confirm'; dialog.setAttribute('aria-labelledby', 'sl-confirm-title');
  document.body.append(dialog);
  let state = {checking:true,firewall:{status:'unknown'},history:[]}, timer = 0, pending = false;
  let dismissed = '', lastNotice = '', draft = null, message = '', messageError = false;
  function detailText() {
    const f = state.firewall;
    if(state.checking) return 'Checking Windows Firewall…';
    if(f.status === 'locked') return 'Locked to '+f.city;
    if(f.status === 'outdated') return 'Lock is out of date, re-apply';
    if(f.status === 'missing') return 'Lock rules are missing';
    if(f.status === 'damaged') return 'Lock needs attention';
    if(f.status === 'unknown') return 'Firewall status unavailable';
    return 'Region lock off · suggested: Dubai';
  }
  function rowAction(r) {
    const selected = state.firewall.code === r.code && state.firewall.present;
    return '<button type="button" class="sl-row-lock'+(selected?' sl-selected':'')+'" data-lock-code="'+esc(r.code)+'" aria-label="Play only here: '+esc(r.city)+'" title="'+(selected?'Re-apply lock to ':'Play only here: ')+esc(r.city)+(r.code==='dxb'?' (suggested)':'')+'"'+(state.busy||state.checking||!state.can_lock?' disabled':'')+'>'+lockIcon+'</button>';
  }
  function decorate(pingData) {
    const f = state.firewall;
    const code = f.code;
    if(code && (f.present||f.status==='missing')) {
      const r = pingData.regions.find(r=>r.code===code);
      const prefix = f.status === 'locked' ? 'LOCKED: ' : 'LOCK CHECK: ';
      document.getElementById('sp-summary').innerHTML = '<span class="sp-summary-name">'+esc(prefix+f.city.toUpperCase())+'</span>'+(r?.ping_ms!=null?'<span class="sp-summary-ms">'+Math.round(r.ping_ms)+' ms</span>':'');
      document.getElementById('sp-chip-icon').innerHTML = lockIcon;
      chip.style.setProperty('--sp-tone',tone(r?.ping_ms));
      chip.style.setProperty('--sp-ping-tone',tone(r?.ping_ms));
      chip.title = detailText()+'. '+(f.error||'Only this region’s relay IPs are left unblocked by this tool.');
    }
    const focus = info.contains(document.activeElement) ? document.activeElement.id : '';
    const infoScroll = info.scrollTop;
    const expanded = !!info.querySelector('details')?.open;
    info.innerHTML = '<div class="sl-state"><strong>'+lockIcon+esc(detailText())+'</strong>'+
      (f.present||f.status==='missing'||(!state.checking&&f.status==='unknown')?'<button type="button" class="btn small" id="sl-unlock"'+(state.busy?' disabled':'')+'>Unlock</button>':'')+'</div>'+
      (f.status==='outdated'||f.status==='damaged'||f.status==='missing'?'<button type="button" class="btn small" id="sl-reapply"'+(state.busy||!state.can_lock?' disabled':'')+'>Re-apply lock</button>':'')+
      '<p class="sl-status" role="status">'+esc(message||state.error||state.detail||f.error||'')+'</p>'+
      (state.restart_needed!==false && f.present?'<p>Restart Steam and CS2 to re-measure relays.'+(state.restart_needed===null?' Process restart time could not be verified.':' A process is still running from before the lock.')+'</p>':'')+
      '<p>'+esc(state.advice?.text||'Saved matchmaking max ping: unavailable.')+'</p>'+
      '<details'+(expanded?' open':'')+'><summary id="sl-more">Server detection & recent matches</summary><p>'+esc(state.monitor||'Checking console log…')+'</p>'+
      (!state.condebug?'<p>Close Steam and CS2, then enable console logging for the active account. Console logs stay on your PC.</p><button type="button" class="btn small" id="sl-log">Enable -condebug</button>':'<p>Console logging is enabled. Restart CS2 after enabling it.</p>')+
      '<p>Only new connections with an explicit server datacenter are detected. Relay routes and server IPs alone are not enough. Current CS2 log format still needs verification.</p>'+
      '<ol class="sl-history">'+[...(state.history||[])].reverse().map(h=>'<li><time>'+esc(new Date(h.time*1000).toLocaleString())+'</time><b>'+esc(h.region.toUpperCase())+' · expected '+esc(h.expected.join(' / ').toUpperCase())+'</b><span>'+esc(h.reason.text)+'</span></li>').join('')+'</ol>'+(!state.history?.length?'<p>No new matches detected yet.</p>':'')+'</details>';
    info.querySelector('.sl-status').classList.toggle('sl-error',messageError||!!state.error);
    info.scrollTop = infoScroll;
    if(focus) document.getElementById(focus)?.focus({preventScroll:true});
    info.querySelector('#sl-unlock')?.addEventListener('click',()=>change('unlock'));
    info.querySelector('#sl-reapply')?.addEventListener('click',()=>prepare(f.code||'dxb'));
    info.querySelector('#sl-log')?.addEventListener('click',enableLog);
    info.querySelector('details').addEventListener('toggle',()=>window.dispatchEvent(new Event('resize')));
    notice();
  }
  function notice() {
    const n = state.notice;
    let toast = document.getElementById('sl-toast');
    if(!n||n.id===dismissed) { toast?.remove(); return; }
    if(n.id===lastNotice && toast) return;
    lastNotice=n.id;
    if(!toast) {
      toast=document.createElement('aside'); toast.id='sl-toast'; toast.className='upd-toast sl-toast';
      toast.setAttribute('role','status'); toast.setAttribute('aria-live','polite'); document.body.append(toast);
    }
    toast.innerHTML='<h4><i></i>Different server detected: '+esc(n.region.toUpperCase())+'</h4><p>Expected '+esc(n.expected.join(' / ').toUpperCase())+'. '+esc(n.reason.text)+'</p><div class="upd-actions"><button type="button" class="btn small" id="sl-view">Server regions</button><button type="button" class="btn small" id="sl-dismiss">Dismiss</button></div>';
    toast.querySelector('#sl-dismiss').onclick=()=>{dismissed=n.id;toast.remove();};
    toast.querySelector('#sl-view').onclick=()=>{
      setTab('launcher'); panel.showPopover(); panel.querySelector('input').focus();
    };
  }
  async function poll() {
    clearTimeout(timer);
    if(document.hidden) return;
    try {state=await api('/api/servers/lock');changed();}
    catch(e) {message=e.message;messageError=true;changed();}
    timer=setTimeout(poll,state.busy?1200:10000);
  }
  async function prepare(code) {
    if(pending||state.busy) return;
    pending=true; message='';messageError=false;
    try {
      draft=await api('/api/servers/lock/prepare',{code});
      const running=[...new Set(draft.processes.map(p=>p.name==='cs2'?'CS2':'Steam'))];
      dialog.innerHTML='<h3 id="sl-confirm-title">Play only in '+esc(draft.city)+'?</h3><p>This blocks outbound UDP to '+draft.relay_count+' other Valve relay IPs for all programs, including Steam. The lock stays on after this app closes.</p><ul><li>Queues can take longer.</li><li>If this region is down, you will not find a match until you unlock.</li><li>Restart Steam and CS2 after applying so matchmaking measures the relays again.</li></ul><p>'+esc(running.length?running.join(' and ')+' currently running. Close them before applying to avoid interrupting a live connection.':'Steam and CS2 are not reported running. Restart them after applying.')+'</p><p>'+esc(draft.advice.text)+'</p><small>Valve directory revision '+draft.revision+'. Windows asks for administrator once.</small><div class="sl-confirm-actions"><button type="button" class="btn" id="sl-cancel">Cancel</button><button type="button" class="btn primary" id="sl-apply">Lock to '+esc(draft.city)+'</button></div>';
      panel.hidePopover();dialog.showModal();dialog.querySelector('#sl-cancel').focus();
      dialog.querySelector('#sl-cancel').onclick=()=>dialog.close();
      dialog.querySelector('#sl-apply').onclick=()=>{const id=draft.plan_id;dialog.close();change('apply',id);};
    } catch(e) {message=e.message;messageError=true;changed();}
    finally {pending=false;}
  }
  async function change(action,plan_id) {
    if(state.busy||pending) return;
    pending=true;message='';messageError=false;
    try {state=await api('/api/servers/lock/change',{action,plan_id,confirmed:true});}
    catch(e) {message=e.message;messageError=true;}
    finally {pending=false;changed();poll();}
  }
  async function enableLog() {
    if(pending) return;
    pending=true;
    try {const result=await api('/api/servers/log/enable',{});message=result.detail;messageError=false;}
    catch(e) {message=e.message;messageError=true;}
    finally {pending=false;changed();poll();}
  }
  panel.addEventListener('click',event=>{const b=event.target.closest('[data-lock-code]');if(b)prepare(b.dataset.lockCode);});
  dialog.addEventListener('close',()=>{draft=null;chip.focus({preventScroll:true});});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)clearTimeout(timer);else poll();});
  document.addEventListener('cs2cfg:ready',poll);
  return {rowAction,decorate};
}
