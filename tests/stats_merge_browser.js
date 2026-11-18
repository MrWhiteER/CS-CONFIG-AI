/* Offline integration fixture. Loaded before the real renderer and handlers. */
const $=id=>document.getElementById(id);
const esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
const calls=[],checks=[],toasts=[];
function check(name,ok){checks.push({name,ok:!!ok});if(!ok)throw Error(name);}
const settle=()=>new Promise(r=>setTimeout(r,30));
let cs2IsRunning=false,whoData={accounts:[{active:true,account:'test',name:'Edy'}]},launches=0;
function status(s){toasts.push(s);} function noteChange(){} async function loadWho(){}
const fixture={ok:true,linked:true,player:{player_id:'p1',nickname:'Edy',avatar:'',country:'AE',elo:2100,level:9},matches:Array.from({length:12},(_,i)=>({source:i%3===2?'cs2':'faceit',match_id:'match-'+i,map:'de_'+['mirage','inferno','nuke','ancient','anubis','dust2'][i%6],mode:i%2?'Competitive':'Premier',won:i%3!==1,tied:i===5,score:i===5?'13 / 13':i%3===1?'9 / 13':'13 / 9',rounds:22,elo:i%3===2?null:2100-i*5,elo_delta:i%3===2?null:i%3===1?-25:25,played_at:1794902400-i*86400,kills:20+i%6,deaths:14+i%4,assists:6,kd:1.43,kr:.91,adr:85.2+i%9,hs_percent:47,mvps:3,double:2,triple:1,quadro:0,penta:0,team:'team_Edy'}))};
// Deliberately distinctive server summaries: the UI must not recompute these.
const summaries={all:{matches:12,wins:7,win_rate:58,kd:1.17,adr:84.2,hs_percent:47},faceit:{matches:8,wins:5,win_rate:63,kd:1.29,adr:88.6,hs_percent:51},cs2:{matches:4,wins:2,win_rate:50,kd:1.04,adr:75.4,hs_percent:39}};
// CS2 rows from Steam's history carry the ten-player Tab screen. The first is a
// recording made on this PC: own line only, and GSI's raw mode id.
fixture.matches.forEach((m,i)=>{if(m.source!=='cs2')return;m.mode=i===2?'scrimcomp2v2':'Premier';m.map=i===2?'de_dustii':m.map;if(i===2)return;m.players=Array.from({length:10},(_,k)=>({name:k===2?'Edy':'Player '+k,kills:10+k,assists:3,deaths:12,mvps:k%3,hs_percent:40,score:20+k,ping:30+k,team:k<5?0:1,avatar:'',you:k===2}));});
let answer=structuredClone(fixture),recording=true,failStats=false,deferStats=null,failProfile=false;
let disk={ok:true,folder:'C:/CS2/replays',demos:[{name:'faceit_tch-0_demirage.dem',size:184549376,when:1794902400}],picked:'',key:'F9',job:null};
const scoreboard={match_id:'match-0',map:'de_mirage',score:'13 / 9',rounds:22,played_at:1794902400,mode:'5v5',region:'EU',teams:[{name:'team_Edy',score:13,won:true,players:Array.from({length:5},(_,i)=>({nickname:i?'Player '+i:'Edy',kills:20,deaths:14,assists:6,adr:85.2,kd:1.43,kr:.91,hs_percent:50,mvps:3}))},{name:'Opponents',score:9,won:false,players:Array.from({length:5},(_,i)=>({nickname:'Rival '+i,kills:14,deaths:20,assists:3,adr:70,kd:.7,kr:.64,hs_percent:40,mvps:1}))}]};
function statsReply(source){
  const all=answer.linked===false?answer.matches.filter(m=>m.source==='cs2'):answer.matches;
  const matches=all.filter(m=>source==='all'||source===m.source);
  return {ok:true,source,matches,summary:matches.length?summaries[answer.linked===false?'cs2':source]:{matches:0},counts:{all:all.length,faceit:all.filter(m=>m.source==='faceit').length,cs2:all.filter(m=>m.source==='cs2').length},faceit:{linked:answer.linked,player:answer.player,error:answer.error,stale:answer.stale},cs2:{recording}};
}
async function api(route,body={}){
  calls.push({route,body});
  if(route==='/api/stats'){
    if(failStats)throw Error('Stats offline');
    const reply=structuredClone(statsReply(body.source));
    if(deferStats){const pending=deferStats;deferStats=null;await pending;}
    return reply;
  }
  if(route==='/api/faceit'){
    if(failProfile)throw Error('FACEIT offline');
    if(body.nickname)answer={...structuredClone(fixture),player:{...fixture.player,nickname:body.nickname}};
    return {...structuredClone(answer),matches:answer.matches.filter(m=>m.source==='faceit')};
  }
  if(route==='/api/faceit/forget'){answer={...answer,linked:false,player:null};return {ok:true};}
  if(route==='/api/demos')return structuredClone(disk);
  if(route==='/api/demos/stats')return structuredClone(scoreboard);
  if(route==='/api/demos/pick'){disk.picked=body.name;return {ok:true};}
  if(route==='/api/demos/waiting')return {waiting:null};
  if(route==='/api/demos/get')return {already:true,name:disk.demos[0].name};
  return {ok:true};
}
async function choose(source){document.querySelector('[data-fc-source="'+source+'"]').click();await settle();}
async function setStatsPreview(name){
  answer=structuredClone(fixture);fcSource='all';recording=true;
  if(name==='faceit'||name==='cs2')fcSource=name;
  if(name==='cs2-empty'){fcSource='cs2';answer.matches=answer.matches.filter(m=>m.source!=='cs2');}
  if(name==='faceit-not-linked')answer.linked=false;
  sessionStorage.setItem('stats-source:test',fcSource);
  document.documentElement.dataset.theme=name==='daylight'?'daylight':'violet';
  await loadFaceit();
  if(name==='cs2')document.querySelector('.fc-match-actions [data-fc-board]').click();
  if(name!=='cs2')$('mstat-back').classList.add('hidden');
  document.querySelector('.scroll').scrollTop=0;
  await new Promise(r=>setTimeout(r,750));
}
async function runStatsChecks(){
 document.documentElement.dataset.boot='ready';document.querySelector('.boot-screen')?.remove();$('status')?.remove();
 document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('hidden',p.dataset.panel!=='faceit'));
 document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.tab==='faceit')));
 $('play').addEventListener('click',()=>launches++);
 sessionStorage.clear();
 try{
  await loadDemos();await loadFaceit();await settle();
  check('All calls combined endpoint',calls.some(c=>c.route==='/api/stats'&&c.body.source==='all'));
  check('12 combined rows',document.querySelectorAll('.fc-match').length===12);
  check('server headline summary',[...document.querySelectorAll('.fc-stat strong')].map(e=>e.textContent).join('|')==='1.17|84.2|58%|47%');
  check('source counts',[...document.querySelectorAll('.fc-count')].map(e=>e.textContent).join('|')==='12|8|4');
  check('source mark on every match',document.querySelectorAll('.fc-match-source .fc-source-icon').length===12);
  check('source mark on form',document.querySelectorAll('.fc-form .fc-source-icon').length===5);
  check('source marks on summary',document.querySelectorAll('.fc-stat-sources .fc-source-icon').length===8);
  check('ELO chart excludes CS2',document.querySelector('.fc-chart .fc-plot').getAttribute('aria-label').includes('8 matches'));
  check('no map or mode ids on screen',!/\b(de|cs|ar)_[a-z]|scrimcomp|premier-/.test($('fc-wrap').textContent));
  check('Dust II by its name',$('fc-wrap').textContent.includes('Dust II')&&$('fc-wrap').textContent.includes('Wingman'));
  check('map picture from the game',document.querySelector('.fc-map-art').getAttribute('src').startsWith('/map-art/de_'));
  document.querySelector('[data-fc-board]').click();
  check('CS2 Tab scoreboard opens',!$('mstat-back').classList.contains('hidden')&&document.querySelectorAll('#mstat-teams tbody tr').length===10);
  check('CS2 scoreboard columns',[...document.querySelectorAll('#mstat-teams thead th')].slice(0,9).map(e=>e.textContent).join('|')==='Player|Ping|K|A|D|MVP|HS%|Score|K/D');
  check('CS2 scoreboard marks you',document.querySelectorAll('#mstat-teams tr.is-you').length===1&&$('mstat-teams').textContent.includes('Your team'));
  check('CS2 scoreboard has no FACEIT parts',!document.querySelector('#mstat-teams .mstat-level')&&!$('mstat-get')&&!$('mstat-body').textContent.includes('FACEIT'));
  check('CS2 scoreboard plain header',!/\b(de|cs)_|scrimcomp/.test($('mstat-title').textContent+$('mstat-when').textContent));
  $('mstat-back').classList.add('hidden');statsShown=null;
  check('draw has D',document.querySelectorAll('.fc-match')[5].querySelector('.fc-result').textContent==='D');
  document.querySelector('[data-fc-expand]').click();await loadFaceit();
  check('expanded row survives refresh',!$('fc-detail-0').hidden);
  document.querySelector('[data-fc-metric="adr"]').click();
  check('trend switch uses combined list',$('fc-trend-plot').querySelector('svg').getAttribute('aria-label').startsWith('ADR over 12'));
  document.querySelector('[data-match]').click();await settle();
  check('FACEIT scoreboard preserved',!$('mstat-back').classList.contains('hidden')&&document.querySelectorAll('.mstat-grid tbody tr').length===10&&calls.some(c=>c.route==='/api/demos/stats'));
  hideStats();
  document.querySelector('[data-pick]').click();await settle();
  check('replay choice preserved',disk.picked===disk.demos[0].name);
  document.querySelector('[data-pick]').click();await settle();check('replay choice clears',disk.picked==='');
  document.querySelector('[data-watch]').click();await settle();check('Watch launches once',launches===1&&calls.some(c=>c.route==='/api/demos/pick'&&c.body.once));
  $('demo-link').value='https://www.faceit.com/en/cs2/room/'+fixture.matches[0].match_id;$('demo-fetch').click();await settle();
  check('Get demo retains scoreboard and download',calls.some(c=>c.route==='/api/demos/get')&&!$('mstat-back').classList.contains('hidden'));hideStats();
  await choose('cs2');
  check('CS2 requests source',calls.at(-2).body.source==='cs2'||calls.some(c=>c.route==='/api/stats'&&c.body.source==='cs2'));
  check('CS2 rows only',document.querySelectorAll('.fc-match').length===4&&![...document.querySelectorAll('.fc-match-source')].some(e=>e.textContent.includes('FACEIT')));
  check('CS2 summary from server',document.querySelector('.fc-stat strong').textContent==='1.04');
  check('CS2 hides profile',!document.querySelector('.fc-player'));
  check('CS2 hides ELO',!$('fc-wrap').textContent.includes('ELO history'));
  check('CS2 mode column',document.querySelector('.fc-mode').textContent.includes('Wingman'));
  const before=calls.filter(c=>c.route==='/api/demos/stats').length;
  document.querySelector('.fc-match-actions button').click();
  check('CS2 Stats expands own line',!$('fc-detail-0').hidden&&$('fc-detail-0').textContent.includes('MVPs')&&$('fc-detail-0').textContent.includes('5K'));
  check('CS2 never requests scoreboard',calls.filter(c=>c.route==='/api/demos/stats').length===before);
  check('both expansion controls sync',document.querySelectorAll('[aria-controls="fc-detail-0"][aria-expanded="true"]').length===2);
  check('session filter saved',sessionStorage.getItem('stats-source:test')==='cs2');
  await choose('faceit');
  check('FACEIT rows only',document.querySelectorAll('.fc-match').length===8);
  check('FACEIT profile visible',!!document.querySelector('.fc-player'));
  check('FACEIT summary',document.querySelector('.fc-stat strong').textContent==='1.29');
  check('filter changes have no new-match toast',!toasts.some(s=>s.startsWith('New match:')));
  $('fc-refresh').click();await settle();
  check('Refresh forces stats',calls.some(c=>c.route==='/api/stats'&&c.body.force));
  answer.matches.unshift({...fixture.matches[0],match_id:'new-faceit',played_at:fixture.matches[0].played_at+100});await loadFaceit();
  check('FACEIT new match toast',toasts.at(-1).includes('FACEIT'));
  await choose('cs2');answer.matches.unshift({...fixture.matches[2],match_id:'new-cs2',played_at:fixture.matches[0].played_at+200});await loadFaceit();
  check('CS2 new match toast',toasts.at(-1).includes('CS2'));
  const count=toasts.length;await loadFaceit();check('repeat poll no duplicate toast',toasts.length===count);
  await setStatsPreview('cs2-empty');
  check('CS2 empty explains modes',$('fc-wrap').textContent.includes('Competitive, Premier or Wingman'));
  check('CS2 empty explains restart',$('fc-wrap').textContent.includes('Restart CS2 once'));
  recording=false;await loadFaceit();check('no restart when recording disabled',!$('fc-wrap').textContent.includes('Restart CS2 once'));
  answer.matches=[{...fixture.matches[2],match_id:'first',played_at:fixture.matches[0].played_at+500}];await loadFaceit();
  check('first recorded match toast',toasts.length===count+1);
  await setStatsPreview('faceit-not-linked');
  check('unlinked still shows CS2',document.querySelectorAll('.fc-match').length===4&&!!$('fc-nick'));
  $('fc-nick').value='Unfinished';$('fc-nick').focus();$('fc-nick').setSelectionRange(3,3);await loadFaceit();
  check('poll preserves draft focus and caret',$('fc-nick').value==='Unfinished'&&document.activeElement===$('fc-nick')&&$('fc-nick').selectionStart===3);
  $('fc-nick').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));await settle();
  check('Enter follows via existing endpoint',calls.some(c=>c.route==='/api/faceit'&&c.body.nickname==='Unfinished'));
  $('fc-forget').click();await settle();check('unfollow keeps CS2',!!$('fc-nick')&&document.querySelectorAll('.fc-match').length===4);
  answer={...structuredClone(fixture),stale:true,error:'FACEIT temporarily unavailable'};await loadFaceit();
  check('FACEIT warning leaves combined history',!!document.querySelector('.fc-warning')&&document.querySelectorAll('.fc-match').length===12);
  failStats=true;await loadFaceit();check('transport failure keeps last history',$('fc-wrap').textContent.includes('Stats offline')&&document.querySelectorAll('.fc-match').length===12);failStats=false;
  delete answer.error;failProfile=true;await loadFaceit();check('profile failure leaves CS2 history',document.querySelectorAll('.fc-match').length===12&&$('fc-wrap').textContent.includes('FACEIT offline'));failProfile=false;
  answer=structuredClone(fixture);answer.matches=[{...fixture.matches[2],kills:null,deaths:null,assists:null,kd:null,adr:null,hs_percent:null,mvps:null,kr:null,double:null,triple:null,quadro:null,penta:null,mode:'Wingman'}];fcSource='cs2';await loadFaceit();
  document.querySelector('.fc-match-actions button').click();check('missing values remain dashes',$('fc-detail-0').textContent.includes('—')&&!$('fc-wrap').innerHTML.match(/NaN|Infinity|undefined/));
  check('null KDA is never zero',document.querySelectorAll('.fc-match-value')[1].textContent.includes('— / — / —'));
  summaries.cs2={matches:1,wins:null,win_rate:null,kd:null,adr:null,hs_percent:null};await loadFaceit();
  check('null summary values remain dashes',[...document.querySelectorAll('.fc-stat strong')].every(e=>e.textContent==='—'));
  summaries.cs2={matches:4,wins:2,win_rate:50,kd:1.04,adr:75.4,hs_percent:39};
  let release;deferStats=new Promise(r=>release=r);fcSource='faceit';const older=loadFaceit();await settle();fcSource='cs2';await loadFaceit();release();await older;
  check('late filter response discarded',statsData.source==='cs2');
  sessionStorage.setItem('stats-source:other','faceit');whoData.accounts=[{active:true,account:'other'}];await loadFaceit();
  check('filter scoped per account',fcSource==='faceit');whoData.accounts=[{active:true,account:'test'}];await loadFaceit();check('account preference restored',fcSource==='all');
  await setStatsPreview('all');
  for(const theme of ['violet','ember','carbon','acid','daylight','pro','crimson','frost','neon']){
    document.documentElement.dataset.theme=theme;await settle();
    check('theme '+theme+' fits',document.documentElement.scrollWidth<=innerWidth&&document.querySelector('.scroll').scrollWidth<=document.querySelector('.scroll').clientWidth);
  }
  check('row controls fit',[...document.querySelectorAll('.fc-match')].every(card=>{const a=card.querySelector('.fc-match-toggle').getBoundingClientRect(),b=card.querySelector('.fc-match-actions').getBoundingClientRect();return a.right<=b.left+1&&b.right<=card.getBoundingClientRect().right+1;}));
  clearInterval(fcTimer);fcTimer=null;
  const interval=window.setInterval;let poll,period,timers=0;
  window.setInterval=(fn,ms)=>{poll=fn;period=ms;timers++;return 123;};startFaceitWatch();startFaceitWatch();window.setInterval=interval;
  check('one 60-second poll timer',timers===1&&period===60000);
  let polled=calls.filter(c=>c.route==='/api/stats').length;poll();await settle();
  check('visible pane polls stats',calls.filter(c=>c.route==='/api/stats').length===polled+1);
  Object.defineProperty(document,'hidden',{configurable:true,value:true});polled=calls.length;poll();await settle();check('hidden window skips polling',calls.length===polled);delete document.hidden;
  const pane=document.querySelector('[data-panel="faceit"]');pane.classList.add('hidden');fcPauseMotion();check('hidden pane pauses motion',document.documentElement.classList.contains('fc-paused'));pane.classList.remove('hidden');fcPauseMotion();
  pane.classList.add('hidden');polled=calls.length;poll();await settle();check('hidden pane skips polling',calls.length===polled);pane.classList.remove('hidden');fcPauseMotion();
  check('reduced motion rule',[...document.styleSheets].some(s=>{try{return [...s.cssRules].some(r=>r.conditionText?.includes('prefers-reduced-motion')&&r.cssText.includes('faceit'))}catch{return false}}));
  if(matchMedia('(prefers-reduced-motion: reduce)').matches)check('reduced motion removes animation',getComputedStyle(document.querySelector('.fc-draw')).animationName==='none');
  await setStatsPreview('all');
 }catch(e){checks.push({error:e.stack});}
 document.body.insertAdjacentHTML('beforeend','<pre id="checks">'+JSON.stringify(checks)+'</pre>');
}
