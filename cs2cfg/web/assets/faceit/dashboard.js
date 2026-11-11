/* FACEIT presentation only. Existing API and scoreboard handlers stay in index.html. */
let fcMetric = 'kd';
const FC_MAPS = ['dust2','mirage','inferno','nuke','ancient','anubis','vertigo','overpass','train','cache'];
const FC_LEVEL_COLORS = ['', '#eeeeee', '#1ce400', '#1ce400', '#ffc800', '#ffc800', '#ffc800', '#ffc800', '#ff6309', '#ff6309', '#ff1f00'];
const fcNumber = v => typeof v === 'number' && Number.isFinite(v) ? v : null;
const fcValue = (v, digits=0) => fcNumber(v) === null ? '—' : v.toFixed(digits);
const fcKD = m => fcNumber(m.kills) !== null && fcNumber(m.deaths) > 0 ? m.kills / m.deaths : null;
const fcMapName = m => String(m || 'Unknown map').replace(/^de_/i,'').replace(/^./, c=>c.toUpperCase());
function fcMapAsset(map) {
  const key = String(map || '').toLowerCase().replace(/^de_/, '');
  return 'assets/maps/' + (FC_MAPS.includes(key) ? key : 'fallback') + '.webp';
}
function fcWhen(m, full=false) {
  return fcNumber(m.played_at) > 0 ? (full || m.played_at>Date.now()/1000 ? new Date(m.played_at*1000).toLocaleString() : ago(m.played_at)) : 'Time unavailable';
}
function fcDelta(v) {
  return fcNumber(v) === null ? '—' : (v>0?'+':'') + v;
}
/* Values stay at their chronological index. A missing ELO breaks the path;
   it is never reconstructed from today's rating or joined across a gap. */
function fcLineChart(matches, metric, mini=false) {
  const values = matches.map(m => metric==='kd' ? fcKD(m) :
    metric==='elo' ? (fcNumber(m.elo)>0 ? m.elo : null) : fcNumber(m.adr));
  const valid = values.filter(v=>v!==null);
  if (!valid.length) return '<p class="fc-caption">No '+(metric==='elo'?'ELO':metric.toUpperCase())+' readings in these matches.</p>';
  const w=mini||metric==='elo'?600:1000, h=mini?100:metric==='elo'?170:130, left=mini?5:48, right=mini?5:15, top=14, bottom=mini?5:29;
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
function fcRenderDashboard() {
  const wrap=$('fc-wrap'); if(!wrap) return;
  const expanded=new Set([...wrap.querySelectorAll('[data-fc-expand][aria-expanded="true"]')].map(b=>b.dataset.fcExpand));
  if(fcData && (fcData.ok===false || (!fcData.player && fcData.error))) {
    wrap.innerHTML='<div class="fc-empty fc-surface"><h3>Could not load your FACEIT account</h3><p role="alert">'+esc(fcData.error||'FACEIT is unavailable. Try again shortly.')+'</p><div class="actions"><button class="btn small" id="fc-refresh">Try again</button><button class="btn small" id="fc-forget">Use another name</button></div></div>';
    return;
  }
  if(!fcData || fcData.linked===false) {
    if($('fc-nick')) return; // Polling never discards a half-entered nickname.
    wrap.innerHTML='<div class="fc-empty fc-surface"><h3>Bring your matches into focus</h3><p>Follow a FACEIT nickname to see recent form, ELO and match stats. No FACEIT sign-in needed. Your replay library works without a followed account.</p><div class="fc-follow"><input id="fc-nick" type="text" spellcheck="false" aria-label="FACEIT nickname" placeholder="FACEIT nickname"><button class="btn" id="fc-link">Follow</button></div></div>';
    return;
  }
  const p=fcData.player||{}, matches=Array.isArray(fcData.matches)?fcData.matches:[];
  const chronological=[...matches].reverse();
  const have=new Set((demoData&&demoData.demos||[]).map(d=>d.name));
  const wins=matches.filter(m=>m.won).length;
  const total=key=>matches.reduce((sum,m)=>sum+(fcNumber(m[key])??0),0);
  const kd=matches.length && total('deaths')>0 ? total('kills')/total('deaths') : null;
  const adrs=matches.map(m=>fcNumber(m.adr)).filter(v=>v!==null);
  const adr=adrs.length?adrs.reduce((a,b)=>a+b,0)/adrs.length:null;
  const level=Number.isInteger(p.level)&&p.level>=1&&p.level<=10?p.level:null;
  const sample=matches.length+' recent '+(matches.length===1?'match':'matches');
  const avatar=p.avatar && /^https?:\/\//i.test(p.avatar) ? '<img src="'+esc(p.avatar)+'" alt="" onerror="this.remove()">' : '';
  const head='<div class="fc-player fc-surface fc-entry"><div class="fc-avatar"><span>'+esc(String(p.nickname||'?').slice(0,1).toUpperCase())+'</span>'+avatar+'</div><div class="fc-identity"><div class="fc-caption">CS2'+(p.country?' · '+esc(p.country):'')+'</div><h3>'+esc(p.nickname||'FACEIT player')+'</h3><span class="fc-caption">'+esc(sample)+'</span></div>'+(level?'<span class="fc-level" style="--level:'+FC_LEVEL_COLORS[level]+'" title="FACEIT skill level '+level+'" aria-label="Skill level '+level+'">'+level+'</span>':'<span class="fc-caption">Unranked</span>')+'<div class="fc-rating">'+(matches.length?fcLineChart(chronological,'elo',true):'')+'<div><span class="fc-label">Current ELO</span><strong>'+fcValue(fcNumber(p.elo)>0?p.elo:null)+'</strong></div></div><div class="actions"><button class="btn small" id="fc-refresh">Refresh</button><button class="btn small" id="fc-forget">Unfollow</button></div></div>';
  const form=matches.slice(0,5).map(m=>'<span class="fc-result '+(m.won?'fc-win':'fc-loss')+'" title="'+esc(fcMapName(m.map)+' · '+fcWhen(m,true))+'">'+(m.won?'W':'L')+'</span>').join('');
  const stats='<div class="fc-stats fc-entry"><div class="fc-stat fc-surface"><span class="fc-label">K/D ratio</span><strong>'+fcValue(kd,2)+'</strong><span class="fc-caption">Total kills ÷ deaths</span></div><div class="fc-stat fc-surface"><span class="fc-label">Average ADR</span><strong>'+fcValue(adr,1)+'</strong><span class="fc-caption">Mean of match ADR</span></div><div class="fc-stat fc-surface"><span class="fc-label">Win rate</span><strong>'+(matches.length?Math.round(wins/matches.length*100)+'%':'—')+'</strong><span class="fc-caption">'+wins+' wins / '+matches.length+' matches</span></div><div class="fc-stat fc-surface"><span class="fc-label">Recent form</span><div class="fc-form">'+(form||'<span class="fc-caption">No matches yet</span>')+'</div><span class="fc-caption">Latest first</span></div></div>';
  const charts=matches.length?'<div class="fc-charts fc-entry"><section class="fc-chart fc-surface"><div class="fc-chart-head"><h3>ELO history</h3><span class="fc-caption">'+esc(sample)+' · after each match</span></div>'+fcLineChart(chronological,'elo')+fcChartTable(chronological,'elo')+'</section><section class="fc-chart fc-surface"><div class="fc-chart-head"><h3>Performance by map</h3><span class="fc-caption">Win rate · wins / played</span></div>'+fcMapBars(matches)+'</section></div><section class="fc-chart fc-surface fc-trend fc-entry"><div class="fc-chart-head"><h3>Performance trend</h3><div class="fc-metric" role="group" aria-label="Trend metric"><button class="btn small" data-fc-metric="kd" aria-pressed="'+(fcMetric==='kd')+'">K/D</button><button class="btn small" data-fc-metric="adr" aria-pressed="'+(fcMetric==='adr')+'">ADR</button></div></div><div id="fc-trend-plot">'+fcRenderTrend(chronological)+'</div></section>':'';
  const rows=matches.map((m,i)=>{
    const id='fc-detail-'+i, open=expanded.has(m.match_id), got=have.has(demoNameFor(m));
    const detail=[['Team',m.team||'Unavailable'],['Rounds',fcValue(m.rounds)],['K/D',fcValue(fcKD(m),2)],['ELO after match',fcValue(fcNumber(m.elo)>0?m.elo:null)],['Played',fcWhen(m,true)]];
    return '<article class="fc-match fc-surface '+(m.won?'won':'lost')+'"><div class="fc-match-row"><button class="fc-match-toggle" data-fc-expand="'+esc(m.match_id)+'" aria-expanded="'+open+'" aria-controls="'+id+'"><img class="fc-map-art" src="'+fcMapAsset(m.map)+'" alt="" loading="lazy" onerror="this.onerror=null;this.src=\'assets/maps/fallback.webp\'"><span class="fc-match-map"><b>'+esc(fcMapName(m.map))+'</b><small>'+esc(fcWhen(m))+(got?' · Downloaded':'')+'</small></span><span class="fc-result '+(m.won?'fc-win':'fc-loss')+'">'+(m.won?'W':'L')+'</span><span class="fc-match-value"><small>Score</small>'+esc(m.score||'—')+'</span><span class="fc-match-value"><small>K / D / A</small>'+[m.kills,m.deaths,m.assists].map(v=>fcValue(v)).join(' / ')+'</span><span class="fc-match-value"><small>ADR</small>'+fcValue(m.adr,1)+'</span><span class="fc-match-value fc-delta '+(m.elo_delta>0?'up':m.elo_delta<0?'down':'')+'"><small>ELO</small>'+fcDelta(m.elo_delta)+'<span class="fc-chevron" aria-hidden="true">⌄</span></span></button><div class="fc-match-actions"><button class="btn small" data-match="'+esc(m.match_id)+'" aria-label="Stats for '+esc(fcMapName(m.map)+' '+fcWhen(m,true))+'">Stats</button></div></div><div class="fc-match-detail" id="'+id+'"'+(open?'':' hidden')+'>'+detail.map(([k,v])=>'<div><small>'+k+'</small><b>'+esc(v)+'</b></div>').join('')+'</div></article>';
  }).join('');
  wrap.innerHTML=head+(fcData.stale?'<p class="fc-warning" role="status">Offline / last good read. '+esc(fcData.error||'Refresh to try again.')+'</p>':'')+stats+charts+'<div class="fc-section-head"><h3>Match history</h3><span class="fc-caption">'+esc(sample)+' · latest first</span></div><div class="fc-history">'+(rows||'<div class="fc-empty fc-surface">No CS2 matches on that account yet. Your matches will appear here after you play.</div>')+'</div>';
}
document.addEventListener('click', e=>{
  const toggle=e.target.closest('[data-fc-expand]');
  if(toggle) {const open=toggle.getAttribute('aria-expanded')!=='true';toggle.setAttribute('aria-expanded',String(open));document.getElementById(toggle.getAttribute('aria-controls')).hidden=!open;}
  const metric=e.target.closest('[data-fc-metric]');
  if(metric) {fcMetric=metric.dataset.fcMetric;document.querySelectorAll('[data-fc-metric]').forEach(b=>b.setAttribute('aria-pressed',String(b===metric)));$('fc-trend-plot').innerHTML=fcRenderTrend([...(fcData.matches||[])].reverse());}
});
document.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.id==='fc-nick') $('fc-link').click();});
function fcPauseMotion() {
  const pane=document.querySelector('[data-panel="faceit"]');
  document.documentElement.classList.toggle('fc-paused',document.hidden||!pane||pane.classList.contains('hidden'));
}
document.addEventListener('visibilitychange',fcPauseMotion);
document.addEventListener('DOMContentLoaded',()=>{const pane=document.querySelector('[data-panel="faceit"]');if(pane)new MutationObserver(fcPauseMotion).observe(pane,{attributes:true,attributeFilter:['class']});fcPauseMotion();});
