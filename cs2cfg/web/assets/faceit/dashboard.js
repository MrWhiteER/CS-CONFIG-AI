/* Combined stats presentation. API and FACEIT scoreboard handlers stay in index.html. */
let fcMetric = 'kd';
const FC_LEVEL_COLORS = ['', '#eeeeee', '#1ce400', '#1ce400', '#ffc800', '#ffc800', '#ffc800', '#ffc800', '#ff6309', '#ff6309', '#ff1f00'];
const fcNumber = v => typeof v === 'number' && Number.isFinite(v) ? v : null;
const fcValue = (v, digits=0) => fcNumber(v) === null ? '—' : v.toFixed(digits);
const fcKD = m => fcNumber(m.kd);
/* Plain names only: nothing on screen reads like de_dust2 or scrimcomp2v2.
   Mirrors cs2cfg/maps.py (tests/test_maps.py keeps the two in step). */
const FC_MAP_NAMES = {"de_dust2": "Dust II", "de_mirage": "Mirage", "de_inferno": "Inferno", "de_nuke": "Nuke", "de_ancient": "Ancient", "de_ancient_night": "Ancient Night", "de_anubis": "Anubis", "de_vertigo": "Vertigo", "de_overpass": "Overpass", "de_train": "Train", "de_cache": "Cache", "de_cbble": "Cobblestone", "de_tuscan": "Tuscan", "de_basalt": "Basalt", "de_edin": "Edin", "de_palais": "Palais", "de_whistle": "Whistle", "de_thera": "Thera", "de_mills": "Mills", "de_memento": "Memento", "de_assembly": "Assembly", "de_jura": "Jura", "de_grail": "Grail", "de_brewery": "Brewery", "de_dogtown": "Dogtown", "de_golden": "Golden", "de_rooftop": "Rooftop", "de_palacio": "Palacio", "de_shortdust": "Shortdust", "de_lake": "Lake", "de_bank": "Bank", "de_safehouse": "Safehouse", "de_sanctum": "Sanctum", "de_poseidon": "Poseidon", "de_stronghold": "Stronghold", "de_vineyard": "Vineyard", "de_overpass_night": "Overpass Night", "cs_italy": "Italy", "cs_office": "Office", "cs_agency": "Agency", "cs_militia": "Militia", "cs_assault": "Assault", "ar_baggage": "Baggage", "ar_shoots": "Shoots", "ar_shoots_night": "Shoots Night", "ar_pool_day": "Pool Day", "ar_lunacy": "Lunacy", "ar_monastery": "Monastery"};
const FC_MAP_ALIASES = {"de_dustii": "de_dust2", "de_dust_ii": "de_dust2", "de_dust": "de_dust2", "de_cobblestone": "de_cbble", "de_italy": "cs_italy", "de_office": "cs_office", "de_agency": "cs_agency", "de_militia": "cs_militia", "de_baggage": "ar_baggage", "de_shoots": "ar_shoots", "de_pool_day": "ar_pool_day", "de_poolday": "ar_pool_day"};
const FC_MODE_NAMES = {"premier": "Premier", "competitive": "Competitive", "scrimcomp2v2": "Wingman", "wingman": "Wingman", "casual": "Casual", "deathmatch": "Deathmatch", "gungameprogressive": "Arms Race", "armsrace": "Arms Race", "gungametrbomb": "Demolition", "survival": "Danger Zone", "cooperative": "Co-op", "coopmission": "Co-op Strike", "training": "Training", "custom": "Custom", "retakes": "Retakes", "skirmish": "War Games", "faceit": "FACEIT", "5v5": "5v5"};
const FC_MAP_PREFIX = /^(de|cs|ar|dz|gd|aim|fy|awp|mg|wp|coop|lobby)_/i;
const fcFlat = t => String(t || '').toLowerCase().replace(/[^a-z0-9]/g, '');
const FC_MAP_BY_NAME = Object.fromEntries(Object.entries(FC_MAP_NAMES).map(([k,v]) => [fcFlat(v), k]));
function fcMapId(map) {
  const key = String(map || '').trim().toLowerCase().replace(/\\/g,'/').split('/').pop().replace(/\s+/g,'_');
  if (!key) return '';
  if (Object.hasOwn(FC_MAP_NAMES, key)) return key;
  if (Object.hasOwn(FC_MAP_ALIASES, key)) return FC_MAP_ALIASES[key];
  const flat = fcFlat(key.replace(FC_MAP_PREFIX, ''));
  if (Object.hasOwn(FC_MAP_BY_NAME, flat)) return FC_MAP_BY_NAME[flat];
  return FC_MAP_PREFIX.test(key) || key.includes('_') ? key : 'de_' + key;
}
function fcMapName(map) {
  const key = fcMapId(map);
  if (!key) return 'Unknown map';
  if (Object.hasOwn(FC_MAP_NAMES, key)) return FC_MAP_NAMES[key];
  return key.replace(FC_MAP_PREFIX, '').split(/[_-]+/).filter(Boolean).map(w => w[0].toUpperCase() + w.slice(1)).join(' ') || 'Unknown map';
}
/* The mode as CS2 shows it: the game's own icon (from the player's install)
   beside the name. Premier's icon is the game's wide wordmark, so it stands
   in for the word. No icon (no CS2 here): just the name. */
/* FACEIT matches get FACEIT's own wordmark in the same spot, the way Premier
   gets CS2's: an orange badge with the logo (faceit-logo.svg as a mask). */
function fcFaceitBadge() {
  return '<span class="fc-faceit-badge" role="img" aria-label="FACEIT"><i></i></span>';
}
function fcModeLabel(mode) {
  const name = fcModeName(mode);
  if (!name) return '—';
  const key = name.toLowerCase().replace(/[^a-z]+/g, '-').replace(/^-|-$/g, '');
  return '<span class="fc-mode-label" title="'+esc(name)+'"><img class="fc-mode-icon" src="/mode-icon/'+encodeURIComponent(key)+'.svg" alt="" '+
    'onload="if(this.naturalWidth>2*this.naturalHeight)this.parentNode.classList.add(\'fc-wordmark\')" onerror="this.remove()"><span class="fc-mode-name">'+esc(name)+'</span></span>';
}
function fcModeName(mode) {
  const text = String(mode || '').trim();
  if (!text) return '';
  return FC_MODE_NAMES[text.toLowerCase().replace(/[\s_-]/g, '')] ||
    text.split(/[\s_-]+/).filter(Boolean).map(w => w[0].toUpperCase() + w.slice(1).toLowerCase()).join(' ');
}
/* Bundled thumbnails are available as soon as Stats opens. */
const FC_MAP_PLAIN = 'assets/maps/fallback.webp';
function fcMapAsset(map) {
  const key = fcMapId(map);
  return Object.hasOwn(FC_MAP_NAMES, key) ? 'assets/maps/' + key + '.webp' : FC_MAP_PLAIN;
}
function fcMapFallback(img) {
  img.onerror = null;
  img.src = FC_MAP_PLAIN;
}
function fcWhen(m, full=false) {
  return fcNumber(m.played_at) > 0 ? (full || m.played_at>Date.now()/1000 ? new Date(m.played_at*1000).toLocaleString() : ago(m.played_at)) : 'Time unavailable';
}
function fcDelta(v) {
  return fcNumber(v) === null ? '—' : (v>0?'+':'') + v;
}
function fcChartWidth(metric) {
  const width=document.querySelector('[data-panel="faceit"]').clientWidth;
  const elo=statsData?.faceit?.linked===true && fcSource!=='cs2';
  if(width<=700) return Math.max(240,width-36);
  if(width<=900) return metric!=='elo' && elo ? width-36 : (width-14)/2-36;
  return elo ? (width-28)*1.2/3.4-36 : (width-14)*1.6/2.6-36;
}
/* Values stay at their chronological index. A missing ELO breaks the path;
   it is never reconstructed from today's rating or joined across a gap. */
function fcLineChart(matches, metric, mini=false) {
  const values = matches.map(m => metric==='kd' ? fcKD(m) :
    metric==='elo' ? (fcNumber(m.elo)>0 ? m.elo : null) : fcNumber(m.adr));
  const valid = values.filter(v=>v!==null);
  if (!valid.length) return '<p class="fc-caption">No '+(metric==='elo'?'ELO':metric.toUpperCase())+' readings in these matches.</p>';
  const w=mini?600:Math.round(fcChartWidth(metric)), h=mini?100:170, left=mini?5:40, right=mini?5:15, top=14, bottom=mini?5:29;
  let lo=Math.min(...valid), hi=Math.max(...valid);
  const pad = Math.max((hi-lo)*.15, metric==='elo'?10:metric==='kd'?.1:5);
  lo=Math.max(0,lo-pad); hi+=pad;
  const x=i=>left + (w-left-right)*(values.length===1?.5:i/(values.length-1));
  const y=v=>h-bottom-(v-lo)/(hi-lo)*(h-top-bottom);
  let path='', connected=false;
  values.forEach((v,i)=>{if(v===null){connected=false;return;} path+=(connected?'L':'M')+x(i).toFixed(2)+','+y(v).toFixed(2)+' ';connected=true;});
  const label=metric==='kd'?'K/D':metric.toUpperCase();
  const ticks=mini?'':[lo,(lo+hi)/2,hi].map(v=>'<line class="fc-grid" x1="'+left+'" x2="'+(w-right)+'" y1="'+y(v)+'" y2="'+y(v)+'"/><text x="'+(left-8)+'" y="'+(y(v)+4)+'" text-anchor="end">'+fcValue(v,metric==='kd'?2:0)+'</text>').join('');
  const points=values.map((v,i)=>v===null?'':'<circle cx="'+x(i)+'" cy="'+y(v)+'" r="'+(mini?2.5:3.5)+'"'+(mini?'':' tabindex="0" role="img" aria-label="'+esc(fcWhen(matches[i],true)+', '+label+' '+fcValue(v,metric==='kd'?2:metric==='adr'?1:0))+'"')+'><title>'+esc(fcWhen(matches[i],true)+' · '+fcMapName(matches[i].map)+' · '+label+' '+fcValue(v,metric==='kd'?2:metric==='adr'?1:0))+'</title></circle>').join('');
  return '<svg class="'+(mini?'fc-mini':'fc-plot')+'" viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none" role="img" aria-label="'+label+' over '+matches.length+' matches, oldest to newest"><title>'+label+' · oldest to newest</title>'+ticks+'<g class="fc-draw"><path d="'+path+'" fill="none" stroke="currentColor" stroke-width="2.5" vector-effect="non-scaling-stroke"/>'+points+'</g>'+(mini?'':'<text x="'+left+'" y="'+(h-5)+'">Oldest</text><text x="'+(w-right)+'" y="'+(h-5)+'" text-anchor="end">Latest</text>')+'</svg>';
}
function fcChartTable(matches, metric) {
  return '<details class="fc-chart-table"><summary>View match values</summary><table><thead><tr><th>Date</th><th>Map</th><th>'+ (metric==='kd'?'K/D':metric.toUpperCase())+'</th></tr></thead><tbody>'+matches.map(m=>{
    const n=metric==='kd'?fcKD(m):metric==='elo'?(fcNumber(m.elo)>0?m.elo:null):m.adr;
    return '<tr><td>'+esc(fcWhen(m,true))+'</td><td>'+esc(fcMapName(m.map))+'</td><td>'+fcValue(n,metric==='kd'?2:metric==='adr'?1:0)+'</td></tr>';
  }).join('')+'</tbody></table></details>';
}
function fcMapBars(matches) {
  const groups=new Map();
  matches.forEach(m=>{const key=m.map||'';const row=groups.get(key)||{n:0,w:0};row.n++;if(m.won)row.w++;groups.set(key,row);});
  return '<div class="fc-maps">'+[...groups].sort((a,b)=>b[1].n-a[1].n).map(([map,g])=>{
    const pct=g.w/g.n*100;
    return '<div class="fc-map-bar"><span>'+esc(fcMapName(map))+'</span><svg viewBox="0 0 100 9" preserveAspectRatio="none" role="img" aria-label="'+esc(fcMapName(map))+': '+Math.round(pct)+' percent wins, '+g.w+' of '+g.n+' matches"><rect width="100" height="9" rx="3" fill="var(--line)"/><g class="fc-draw"><rect width="'+pct+'" height="9" rx="3" fill="currentColor"/></g></svg><small>'+Math.round(pct)+'% · '+g.w+'/'+g.n+'</small></div>';
  }).join('')+'</div>';
}
function fcRenderTrend(matches) {
  return fcLineChart(matches,fcMetric)+fcChartTable(matches,fcMetric);
}
/* The list and headline values come from /api/stats. FACEIT's separate
   payload is retained only for profile identity and ELO history. */
let statsData = null;
let fcSource = 'all';
let fcAccount = null;
let fcLoading = false;
let fcLoadError = '';
const fcSources = ['all','faceit','cs2'];
const fcSourceName = source => source === 'faceit' ? 'FACEIT' : source === 'cs2' ? 'CS2' : 'All';
function fcSourceIcon(source) {
  return '<span class="fc-source-icon '+(source==='cs2'?'fc-cs2-logo':'fc-logo')+'" role="img" aria-label="'+fcSourceName(source)+'"></span>';
}
function fcSyncAccount() {
  const key = String((whoData && whoData.accounts || []).find(a=>a.active)?.account || 'session');
  if (key === fcAccount) return key;
  fcAccount = key;
  try { const saved=sessionStorage.getItem('stats-source:'+key); fcSource=fcSources.includes(saved)?saved:'all'; } catch (_) { fcSource='all'; }
  statsData=null;
  fcData=null;
  fcSeen={};
  // Drafts and expanded rows belong to the account that was on screen.
  if($('fc-wrap')) $('fc-wrap').innerHTML='';
  return key;
}
/* A CS2 match from Steam's history, shaped for the same scoreboard window the
   FACEIT matches use, laid out like CS2's own Tab screen. Steam's page has no
   ADR, multi-kills or halves, so those columns are left out for CS2. */
function fcCs2Scoreboard(m) {
  const players=(m.players||[]).map(p=>({...p,nickname:p.name||'Player',
    kd:fcNumber(p.kills)!==null&&fcNumber(p.deaths)!==null?(p.deaths?p.kills/p.deaths:p.kills):null}));
  const hasTeams=players.some(p=>p.team===1);
  const half=Math.ceil(players.length/2);
  const sides=[0,1].map(t=>players.filter((p,i)=>hasTeams?(p.team||0)===t:(t===0?i<half:i>=half)));
  const [ours,theirs]=String(m.score||'').split('/').map(v=>parseInt(v,10));
  const mine=Math.max(0,sides.findIndex(side=>side.some(p=>p.you)));
  const score=side=>side===mine?ours:theirs;
  const teams=sides.map((side,t)=>({name:t===mine?'Your team':'Opponents',score:Number.isFinite(score(t))?score(t):'—',
    won:t===mine?m.won===true:m.won===false&&!m.tied,players:side.sort((a,b)=>(b.score||0)-(a.score||0))}));
  if(mine===1) teams.reverse();
  return {source:'cs2',tied:!!m.tied,match_id:m.match_id,map:m.map,mode:m.mode,rounds:m.rounds,played_at:m.played_at,teams,score:m.score};
}
function fcOutcome(m) { return m.tied ? 'D' : m.won===true ? 'W' : m.won===false ? 'L' : '—'; }
function fcOutcomeClass(m) { return m.tied || typeof m.won!=='boolean' ? 'fc-draw-result' : m.won ? 'fc-win' : 'fc-loss'; }
function fcPercent(v) { return fcNumber(v)===null ? '—' : fcValue(v)+'%'; }
function fcRenderDashboard() {
  const wrap=$('fc-wrap'); if(!wrap) return;
  const expanded=new Set([...wrap.querySelectorAll('[data-fc-expand][aria-expanded="true"]')].map(b=>b.dataset.fcExpand));
  const draft=$('fc-nick')?.value || '', focused=document.activeElement?.id==='fc-nick';
  const selection=focused?[$('fc-nick').selectionStart,$('fc-nick').selectionEnd]:null;
  const data=statsData||{}, faceit=data.faceit||{}, p=faceit.player||{};
  const matches=Array.isArray(data.matches)?data.matches:[], summary=data.summary||{};
  const chronological=[...matches].reverse();
  const faceitMatches=(fcData?.matches||[]).filter(m=>m.source!=='cs2').slice().reverse();
  const showFaceit=faceit.linked===true && fcSource!=='cs2';
  const sample=fcValue(summary.matches)+' '+(summary.matches===1?'match':'matches');
  const filters='<div class="fc-toolbar"><div class="fc-sources" role="group" aria-label="Match source">'+fcSources.map(source=>
    '<button type="button" data-fc-source="'+source+'" aria-pressed="'+(fcSource===source)+'">'+(source==='all'?'':fcSourceIcon(source))+'<span>'+fcSourceName(source)+'</span><span class="fc-count">'+fcValue(data.counts?.[source])+'</span></button>').join('')+
    '</div><div class="fc-toolbar-end"><span class="fc-caption" role="status">'+(fcLoading?'Updating stats…':fcSource==='cs2'?(data.cs2?.recording?'Recording on this PC':'Local match history'):'One record. Every match.')+'</span><button class="btn small" id="fc-refresh"'+(fcLoading?' disabled':'')+'>Refresh</button></div></div>';
  const level=Number.isInteger(p.level)&&p.level>=1&&p.level<=10?p.level:null;
  const avatar=p.avatar && /^https?:\/\//i.test(p.avatar) ? '<img src="'+esc(p.avatar)+'" alt="" onerror="this.remove()">' : '';
  const head=showFaceit?'<div class="fc-player fc-surface fc-entry"><div class="fc-avatar"><span>'+esc(String(p.nickname||'?').slice(0,1).toUpperCase())+'</span>'+avatar+'</div><div class="fc-identity"><div class="fc-caption">'+fcSourceIcon('faceit')+' FACEIT'+(p.country?' · '+esc(p.country):'')+'</div><h3>'+esc(p.nickname||'FACEIT player')+'</h3></div>'+(level?'<span class="fc-level" title="FACEIT skill level '+level+'" aria-label="Skill level '+level+'">'+level+'</span>':'<span class="fc-caption">Unranked</span>')+'<div class="fc-rating">'+(faceitMatches.length?fcLineChart(faceitMatches,'elo',true):'')+'<div><span class="fc-label">Current ELO</span><strong>'+fcValue(fcNumber(p.elo)>0?p.elo:null)+'</strong></div></div><button class="btn small" id="fc-forget">Unfollow</button></div>':'';
  const follow=faceit.linked!==true?'<section class="fc-follow-card fc-surface"><div>'+fcSourceIcon('faceit')+'</div><div><h3>Add your FACEIT matches</h3><p>Follow a nickname to bring ELO and FACEIT history into this view.</p></div><div class="fc-follow"><input id="fc-nick" type="text" spellcheck="false" aria-label="FACEIT nickname" placeholder="FACEIT nickname" value="'+esc(draft)+'"><button class="btn small" id="fc-link">Follow</button></div></section>':'';
  const sourceLegend='<span class="fc-stat-sources" aria-label="Stats sources">'+(fcSource==='all'?[fcSourceIcon('faceit'),fcSourceIcon('cs2')].join(''):fcSourceIcon(fcSource))+'</span>';
  const form=matches.slice(0,5).map(m=>'<span class="fc-result '+fcOutcomeClass(m)+'" title="'+esc(fcSourceName(m.source)+' · '+fcMapName(m.map)+' · '+fcWhen(m,true))+'">'+fcSourceIcon(m.source)+fcOutcome(m)+'</span>').join('');
  const card=(label,value,caption)=>'<div class="fc-stat fc-surface"><span class="fc-label">'+label+sourceLegend+'</span><strong>'+value+'</strong><span class="fc-caption">'+caption+'</span></div>';
  const stats='<div class="fc-stats fc-entry">'+card('K/D ratio',fcValue(summary.kd,2),'Total kills ÷ deaths')+card('Average ADR',fcValue(summary.adr,1),'Damage per round')+card('Win rate',fcPercent(summary.win_rate),fcValue(summary.wins)+' wins / '+sample)+card('Headshots',fcPercent(summary.hs_percent),'Average HS%')+'<div class="fc-stat fc-surface"><span class="fc-label">Recent form</span><div class="fc-form">'+(form||'<span class="fc-caption">No matches yet</span>')+'</div><span class="fc-caption">Latest first</span></div></div>';
  const elo=showFaceit?'<section class="fc-chart fc-surface"><div class="fc-chart-head"><h3>'+fcSourceIcon('faceit')+' ELO history</h3><span class="fc-caption">FACEIT · after each match</span></div>'+fcLineChart(faceitMatches,'elo')+fcChartTable(faceitMatches,'elo')+'</section>':'';
  const charts=matches.length?'<div class="fc-charts fc-entry '+(showFaceit?'':'fc-charts-solo')+'">'+elo+'<section class="fc-chart fc-surface"><div class="fc-chart-head"><h3>Performance by map</h3><span class="fc-caption">Win rate · wins / played</span></div>'+fcMapBars(matches)+'</section><section class="fc-chart fc-surface fc-trend"><div class="fc-chart-head"><h3>Performance trend</h3><div class="fc-metric" role="group" aria-label="Trend metric"><button class="btn small" data-fc-metric="kd" aria-pressed="'+(fcMetric==='kd')+'">K/D</button><button class="btn small" data-fc-metric="adr" aria-pressed="'+(fcMetric==='adr')+'">ADR</button></div></div><div id="fc-trend-plot">'+fcRenderTrend(chronological)+'</div></section></div>':'';
  const have=new Set((demoData?.demos||[]).map(d=>d.name));
  const rows=matches.map((m,i)=>{
    const id='fc-detail-'+i, key=m.source+':'+m.match_id, open=expanded.has(key), local=m.source==='cs2';
    const detail=local?[['MVPs',fcValue(m.mvps)],['HS%',fcPercent(m.hs_percent)],['K/R',fcValue(m.kr,2)],['2K',fcValue(m.double)],['3K',fcValue(m.triple)],['4K',fcValue(m.quadro)],['5K',fcValue(m.penta)]]:
      [['Team',String(m.team||'').replace(/^team_/i,'')||'Unavailable'],['ELO after match',fcValue(fcNumber(m.elo)>0?m.elo:null)]];
    detail.unshift(['Rounds',fcValue(m.rounds)],['K/D',fcValue(m.kd,2)]);
    detail.push(['Played',fcWhen(m,true)]);
    const toggleAttrs=' data-fc-expand="'+esc(key)+'" aria-expanded="'+open+'" aria-controls="'+id+'"';
    return '<article class="fc-match fc-surface '+(m.tied?'tied':m.won===true?'won':m.won===false?'lost':'unknown')+'"><div class="fc-match-row"><button class="fc-match-toggle"'+toggleAttrs+'><img class="fc-map-art" src="'+fcMapAsset(m.map)+'" alt="" loading="lazy" onerror="fcMapFallback(this)"><span class="fc-match-map"><b>'+esc(fcMapName(m.map))+'</b><span class="fc-match-source">'+fcSourceIcon(m.source)+fcSourceName(m.source)+'</span><small>'+esc(fcWhen(m))+(!local&&have.has(demoNameFor(m))?' · Downloaded':'')+'</small></span><span class="fc-result '+fcOutcomeClass(m)+'">'+fcOutcome(m)+'</span><span class="fc-match-value"><small>Score</small>'+esc(m.score||'—')+'</span><span class="fc-match-value"><small>K / D / A</small>'+[m.kills,m.deaths,m.assists].map(v=>fcValue(v)).join(' / ')+'</span><span class="fc-match-value"><small>ADR</small>'+fcValue(m.adr,1)+'</span><span class="fc-match-value fc-mode '+(!local?(m.elo_delta>0?'up':m.elo_delta<0?'down':''):'')+'"><small>'+ (local?'Mode':'ELO')+'</small>'+(local?fcModeLabel(m.mode):fcFaceitBadge()+'<span class="fc-elo-delta">'+fcDelta(m.elo_delta)+'</span>')+'<span class="fc-chevron" aria-hidden="true">⌄</span></span></button><div class="fc-match-actions"><button class="btn small"'+(local?(local&&Array.isArray(m.players)&&m.players.length)?' data-fc-board="'+esc(m.match_id)+'"':toggleAttrs:' data-match="'+esc(m.match_id)+'"')+' aria-label="'+(local&&!(local&&Array.isArray(m.players)&&m.players.length)?'Your stats':'Scoreboard')+' for '+esc(fcMapName(m.map)+' '+fcWhen(m,true))+'">Stats</button></div></div><div class="fc-match-detail" id="'+id+'"'+(open?'':' hidden')+'>'+(local?'<p class="fc-own-line">Your match stats <span>CS2 records your own line on this PC.</span></p>':'')+detail.map(([k,v])=>'<div><small>'+k+'</small><b>'+esc(v)+'</b></div>').join('')+'</div></article>';
  }).join('');
  const empty=fcSource==='faceit'?'<h3>No FACEIT matches yet</h3><p>'+(faceit.linked===true?'Your recent FACEIT matches will appear here when available.':'Follow a nickname above to see FACEIT matches. Your local CS2 history is available under All or CS2.')+'</p>':
    '<h3>Your next match starts the story</h3><p>CS2 matches appear here after your next Competitive, Premier or Wingman game. Connect Steam in Accounts at the bottom left to bring in your older games too.</p>'+(data.cs2?.recording?'<p class="fc-restart">Restart CS2 once after this update to activate match recording.</p>':'');
  const warning=fcLoadError?'<p class="fc-warning" role="alert">'+esc(fcLoadError)+(statsData?' Your last loaded stats remain below.':'')+' Use Refresh to try again.</p>':
    faceit.error?'<p class="fc-warning" role="status">FACEIT'+(faceit.stale?' · last good read':'')+': '+esc(faceit.error)+'</p>':'';
  wrap.setAttribute('aria-busy',String(fcLoading));
  wrap.innerHTML=filters+warning+head+follow+stats+charts+'<div class="fc-section-head"><h3>Match history <span class="fc-caption">'+sample+'</span></h3><span class="fc-caption">'+fcSourceName(fcSource)+' · latest first</span></div><div class="fc-history">'+(rows||'<div class="fc-empty fc-surface">'+(fcLoading?'Loading your stats…':empty)+'</div>')+'</div>';
  if(focused && $('fc-nick')) {$('fc-nick').focus();$('fc-nick').setSelectionRange(...selection);}
}
document.addEventListener('click', async e=>{
  const source=e.target.closest('[data-fc-source]');
  if(source && source.dataset.fcSource!==fcSource) {
    fcSource=source.dataset.fcSource;
    try {sessionStorage.setItem('stats-source:'+fcAccount,fcSource);} catch (_) {}
    // Clear the previous filter's rows while its replacement is loading.
    statsData=statsData?{...statsData,matches:[],summary:{}}:null;
    await loadFaceit();
  }
  const board=e.target.closest('[data-fc-board]');
  if(board) {
    const m=(statsData?.matches||[]).find(r=>r.source==='cs2'&&r.match_id===board.dataset.fcBoard);
    if(m) {statsFocus=board;showStats(fcCs2Scoreboard(m));$('mstat-close').focus();}
    return;
  }
  const toggle=e.target.closest('[data-fc-expand]');
  if(toggle) {
    const open=toggle.getAttribute('aria-expanded')!=='true';
    document.querySelectorAll('[data-fc-expand]').forEach(b=>{if(b.dataset.fcExpand===toggle.dataset.fcExpand)b.setAttribute('aria-expanded',String(open));});
    document.getElementById(toggle.getAttribute('aria-controls')).hidden=!open;
  }
  const metric=e.target.closest('[data-fc-metric]');
  if(metric) {fcMetric=metric.dataset.fcMetric;document.querySelectorAll('[data-fc-metric]').forEach(b=>b.setAttribute('aria-pressed',String(b===metric)));$('fc-trend-plot').innerHTML=fcRenderTrend([...(statsData?.matches||[])].reverse());}
});
document.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.id==='fc-nick') $('fc-link').click();});
function fcPauseMotion() {
  const pane=document.querySelector('[data-panel="faceit"]');
  document.documentElement.classList.toggle('fc-paused',document.hidden||!pane||pane.classList.contains('hidden'));
}
document.addEventListener('visibilitychange',fcPauseMotion);
document.addEventListener('DOMContentLoaded',()=>{
  const pane=document.querySelector('[data-panel="faceit"]');
  if(pane) {
    new MutationObserver(fcPauseMotion).observe(pane,{attributes:true,attributeFilter:['class']});
    let width=0;
    new ResizeObserver(()=>{
      if(pane.clientWidth && pane.clientWidth!==width) {
        width=pane.clientWidth;
        if(statsData) fcRenderDashboard();
      }
    }).observe(pane);
  }
  fcPauseMotion();
});
