/* App pages share existing companion/FACEIT/Crosshair endpoints. No remote art. */
let appTilesData = null, appFaceitData = {}, appMatchData = {}, appSelected = '', appLoading = null;
const APP_NAMES = {faceit:'FACEIT',discord:'Discord',teamspeak:'TeamSpeak',crosshairx:'Crosshair X'};
function appLogo(kind) { return kind === 'faceit' ? 'assets/faceit/faceit-mark.svg' : kind === 'crosshairx' ? 'assets/apps/crosshairx-logo.png' : 'assets/apps/'+kind+'-logo.svg'; }
function appState(d) { return !d ? 'Checking…' : d.error ? 'Status unavailable' : d.running ? 'Running' : d.installed ? 'Ready to launch' : 'Not found · choose app'; }
function paintAppTiles() {
  const states = {faceit:appFaceitData['faceit-client'],discord:appTilesData?.apps?.discord,teamspeak:appTilesData?.apps?.teamspeak,crosshairx:typeof xhairData==='undefined'?null:xhairData};
  for(const [kind,d] of Object.entries(states)) {
    const statusEl=document.querySelector('[data-app-status="'+kind+'"]');
    if(statusEl)statusEl.textContent=appState(d);
  }
  // Polls update status only. Never replace an in-progress server form.
  document.querySelectorAll('[data-app-live]').forEach(el=>{const kind=el.dataset.appLive;el.textContent=appState(appFaceitData[kind]||states[kind]);});
}
async function loadAppTiles() {
  if(appLoading)return appLoading;
  appLoading=(async()=>{
    const results=await Promise.allSettled([api('/api/apps',{}),api('/api/faceit/apps',{}),api('/api/match/settings',{})]);
    appTilesData=results[0].status==='fulfilled'&&results[0].value.ok ? results[0].value : {apps:{discord:{error:true},teamspeak:{error:true}}};
    appFaceitData=results[1].status==='fulfilled'&&results[1].value.ok ? results[1].value.apps : {'faceit-client':{error:true},'faceit-ac':{error:true}};
    appMatchData=results[2].status==='fulfilled'?results[2].value:{error:true};
    paintAppTiles();
  })();
  try{await appLoading;}finally{appLoading=null;}
}
function appToggle(key,checked,label,disabled=false) {return '<label class="opt"><input type="checkbox" data-app-with="'+key+'" aria-label="'+esc(label)+'"'+(checked?' checked':'')+(disabled?' disabled':'')+'> Start with CS2</label>';}
function appRow(title,description,controls) {return '<div class="app-setting"><span><b>'+title+'</b><small>'+description+'</small></span>'+controls+'</div>';}
function appLaunchRow(kind,d) {return appRow(esc(kind==='faceit-ac'?'Anti-cheat':kind==='faceit-client'?'FACEIT client':APP_NAMES[kind]),'<span data-app-live="'+kind+'">'+appState(d)+'</span>', '<div class="actions"><button class="btn small" data-app-launch="'+kind+'"'+(!d?.installed?' disabled':'')+'>Launch now</button>'+appToggle(kind,!!d?.with_game,'Start '+(APP_NAMES[kind]||kind)+' with CS2',!d?.installed)+'</div>');}
function openAppPage(kind) {
  if(!APP_NAMES[kind])return;
  appSelected=kind;
  $('apps-overview').hidden=true;$('companions-card').classList.add('hidden');$('app-detail').hidden=false;
  $('app-detail-title').textContent=APP_NAMES[kind];$('app-detail-logo').src=appLogo(kind);
  $('app-detail-caption').textContent=kind==='faceit'?'Client, anti-cheat & match alerts':kind==='crosshairx'?'Your overlay, ready for the game':'Ready when you play.';
  const box=$('app-controls');let content='';
  if(kind==='faceit') {
    content=appLaunchRow('faceit-client',appFaceitData['faceit-client'])+appLaunchRow('faceit-ac',appFaceitData['faceit-ac']);
    content+=appRow('Match-found alert','For FACEIT and CS2 · accept your FACEIT match in its own client.','<label class="opt"><input id="app-alert-enabled" type="checkbox"'+(appMatchData.enabled?' checked':'')+(appMatchData.error?' disabled':'')+'> Alert me</label>');
    content+=appRow('Alert options','Changes apply to the next match alert.','<div><label class="opt"><input type="checkbox" id="app-alert-sound"'+(appMatchData.sound!==false?' checked':'')+'> Sound</label><label class="opt"><input type="checkbox" id="app-alert-top"'+(appMatchData.on_top!==false?' checked':'')+'> Always on top</label></div>');
    content+='<p class="app-tips">FACEIT not found? <button class="btn small" data-app-pick="faceit-client">Choose client</button> <button class="btn small" data-app-pick="faceit-ac">Choose anti-cheat</button></p>';
  } else if(kind==='discord'||kind==='teamspeak') {
    content=appLaunchRow(kind,appTilesData?.apps?.[kind]);
    content+='<p class="app-tips"><button class="btn small" data-app-pick="'+kind+'">Choose executable…</button> <button class="btn small" data-app-refresh>Refresh status</button></p>';
    if(kind==='discord')content+='<div class="app-tips"><b>In Discord’s settings</b><p><a href="discord://-/settings/overlay" target="_blank" rel="noopener">Game Overlay ↗</a> — turning the overlay off may reduce game overhead.</p><p><a href="discord://-/settings/advanced" target="_blank" rel="noopener">Hardware acceleration ↗</a> — compare on/off on your PC.</p><p><a href="discord://-/settings/voice" target="_blank" rel="noopener">Voice & Video ↗</a> — set input sensitivity or push-to-talk.</p><small>If a link opens Discord’s home, use User Settings to find the named page. Discord stays open after CS2; quit it in Discord when you’re done.</small></div>';
    else {
      const ts=appTilesData?.teamspeak||{};
      content+=appRow('Auto-join my server','Open your saved TeamSpeak URL when you launch CS2 here.','<label class="opt"><input id="app-ts-enabled" type="checkbox"'+(ts.enabled?' checked':'')+'> Auto-join</label>');
      content+='<div class="app-server"><label>Host<input id="app-ts-host" type="text" placeholder="voice.example.com" maxlength="253" value="'+esc(ts.host||'')+'"></label><label>Port<input id="app-ts-port" type="number" min="1" max="65535" value="'+esc(ts.port||9987)+'"></label><label>Nickname<input id="app-ts-nickname" type="text" maxlength="64" value="'+esc(ts.nickname||'')+'"></label></div><div class="actions"><button class="btn primary" id="app-ts-save">Save server</button><button class="btn" data-app-launch="teamspeak-join">Join saved server</button></div><p class="app-tips">Uses <code>ts3server://</code> · TeamSpeak 3, 5 or 6 must handle the link.</p>';
    }
  }
  box.innerHTML=content;
  $('xhair-card').classList.toggle('hidden',kind!=='crosshairx');
  if(kind==='crosshairx')renderCrosshairX();
  $('app-feedback').textContent='';$('app-detail-title').focus({preventScroll:true});
}
function closeAppPage() {const was=appSelected;appSelected='';$('apps-overview').hidden=false;$('app-detail').hidden=true;$('companions-card').classList.remove('hidden');document.querySelector('[data-app-tile="'+was+'"]')?.focus({preventScroll:true});}
function appFeedback(text,error=false) {const el=$('app-feedback');el.textContent=text;el.classList.toggle('error',error);}
document.addEventListener('click',async e=>{
  const tile=e.target.closest('[data-app-tile]');if(tile){if(!appTilesData)await loadAppTiles();openAppPage(tile.dataset.appTile);return;}
  if(e.target.closest('#app-back')){closeAppPage();return;}
  const launch=e.target.closest('[data-app-launch]'),pick=e.target.closest('[data-app-pick]'),save=e.target.closest('#app-ts-save'),refresh=e.target.closest('[data-app-refresh]');
  if(!launch&&!pick&&!save&&!refresh)return;
  const button=launch||pick||save||refresh;button.disabled=true;
  try {
    let r;
    if(launch){const kind=launch.dataset.appLaunch;r=await api(kind.startsWith('faceit-')?'/api/faceit/apps/launch':'/api/apps/launch',{app:kind});}
    else if(pick){const picked=await api('/api/companions/browse',{});if(!picked.path||picked.cancelled)return;const kind=pick.dataset.appPick;r=await api(kind.startsWith('faceit-')?'/api/faceit/apps/set':'/api/apps/set',{app:kind,exe:picked.path,...(kind.startsWith('faceit-')?{with_game:!!appFaceitData[kind]?.with_game}:{})});}
    else if(save){r=await api('/api/apps/set',{server:{host:$('app-ts-host').value,port:$('app-ts-port').value,nickname:$('app-ts-nickname').value,enabled:$('app-ts-enabled').checked}});}
    else {await loadAppTiles();openAppPage(appSelected);return;}
    appFeedback(r.detail||r.error||(r.ok?'Saved.':'Could not complete that action.'),!r.ok);
    if(r.ok){await loadAppTiles();if(pick)openAppPage(appSelected);loadCompanions();}
  }catch(err){appFeedback(err.message||String(err),true);}finally{button.disabled=false;}
});
document.addEventListener('change',async e=>{
  const toggle=e.target.closest('[data-app-with]'),alert=e.target.closest('#app-alert-enabled,#app-alert-sound,#app-alert-top');
  if(!toggle&&!alert)return;
  const el=toggle||alert;el.disabled=true;
  try{let r;if(toggle){const kind=toggle.dataset.appWith;r=await api(kind.startsWith('faceit-')?'/api/faceit/apps/set':'/api/apps/set',{app:kind,with_game:toggle.checked});}
    else r=await api('/api/match/settings',{enabled:$('app-alert-enabled').checked,sound:$('app-alert-sound').checked,on_top:$('app-alert-top').checked});
    if(!r.ok)throw Error(r.error||'Could not save');appFeedback('Saved.');await loadAppTiles();loadCompanions();
  }catch(err){el.checked=!el.checked;appFeedback(err.message||String(err),true);}finally{el.disabled=false;}
});
function pauseAppsMotion(){const pane=document.querySelector('.subpane[data-sub="apps"]');document.documentElement.classList.toggle('apps-paused',document.hidden||!pane||!!pane.closest('.hidden'));}
document.addEventListener('visibilitychange',pauseAppsMotion);
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&appSelected&&activeTab==='settings'&&settingsSub==='apps'){e.preventDefault();closeAppPage();}});
document.addEventListener('DOMContentLoaded',()=>{new MutationObserver(pauseAppsMotion).observe(document.querySelector('[data-panel="settings"]'),{attributes:true,subtree:true,attributeFilter:['class']});pauseAppsMotion();});
