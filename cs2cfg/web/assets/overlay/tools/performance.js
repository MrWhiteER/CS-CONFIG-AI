(() => {
 const {number:n,escape:e}=window.overlayUI;
 window.overlayRenderers.performance=(root,data,call)=>{
  if(!root.dataset.built){
   root.innerHTML='<h3 data-capture></h3><div class="figures"><div class="current"><strong data-fps>—</strong><span>FRAMES / SEC</span></div><dl><div><dt>Average</dt><dd data-average></dd></div><div><dt>1% low</dt><dd data-low></dd></div><div><dt>Frame time</dt><dd data-frame></dd></div></dl></div><div class="graph-head"><span>Frame time · ms</span><div role="group" aria-label="History range"><button data-range="120">2 min</button><button data-range="300">5 min</button><button data-range="600">10 min</button></div></div><svg class="graph" viewBox="0 0 460 130" role="img" aria-label="Frame time history"></svg><div class="graph-foot"><span data-range-label></span><span>Now</span></div><p data-hint></p><button data-dismiss hidden>Dismiss reminder</button><a data-setup href="/?tab=settings" hidden>Open app setup ?</a><p data-notice></p>';
   root.dataset.built='1';root.dataset.range='120';
   for(const b of root.querySelectorAll('[data-range]')) b.onclick=()=>{root.dataset.range=b.dataset.range;draw(root,root.overlayData);};
   root.querySelector('[data-dismiss]').onclick=async()=>{const d=await call('dismiss',{});window.overlayRenderers.performance(root,{...root.overlayData,...d},call);};
  }
  root.overlayData=data;
  const set=(sel,value)=>root.querySelector(sel).textContent=value;
  const c=data.current||{},s=data.summary||{},ready=data.frame_capture_ready;
  set('[data-capture]',data.game_running?'Current session':'Waiting for Counter-Strike 2');
  set('[data-fps]',ready?n(c.fps):'—');set('[data-average]',ready?n(s.avg_fps):'—');
  set('[data-low]',ready?n(s.one_percent_low):'—');set('[data-frame]',ready?n(c.frame_time_ms,' ms'):'—');
  set('[data-hint]',data.frame_capture_hint||'');root.querySelector('[data-dismiss]').hidden=!data.frame_capture_hint_dismissible;
  root.querySelector('[data-setup]').hidden=!data.frame_capture_hint;
  set('[data-notice]',[data.notice,data.error,data.hud_warning,data.panel_warning,s.worst_frame_ms!=null?'Worst frame '+n(s.worst_frame_ms,' ms'):''].filter(Boolean).join(' · '));
  draw(root,data);
 };
 function draw(root,data){
  // Shell refresh is capped at 10 Hz. Coalesce rapid range clicks without timers.
  const now=performance.now();if(root.lastGraphAt!=null&&now-root.lastGraphAt<100)return;root.lastGraphAt=now;
  const range=Number(root.dataset.range),end=data.now||Date.now()/1000;
  const samples=data.frame_capture_ready?(data.history||[]).filter(s=>s.at>=end-range&&Number.isFinite(s.frame_time_ms)):[];
  const max=Math.max(10,...samples.map(s=>s.frame_time_ms))*1.1;
  let html='';for(let i=0;i<4;i++){let y=8+i*36;html+='<line class="grid" x1="28" x2="460" y1="'+y+'" y2="'+y+'"/><text x="0" y="'+(y+4)+'">'+Math.round(max*(1-i/3))+'</text>';}
  let prev=null;const path=samples.map(s=>{const move=prev==null||s.at-prev>2;prev=s.at;return (move?'M':'L')+(28+Math.max(0,Math.min(1,(s.at-end+range)/range))*432).toFixed(2)+','+(116-s.frame_time_ms/max*108).toFixed(2);}).join(' ');
  html+=path?'<path class="trace" d="'+path+'"/>':'<text x="80" y="65">'+(data.frame_capture_ready?'Waiting for frame data':'Frame stats unavailable')+'</text>';
  root.querySelector('svg.graph').innerHTML=html;root.querySelector('[data-range-label]').textContent=range/60+' minutes ago';
  for(const b of root.querySelectorAll('[data-range]'))b.setAttribute('aria-pressed',String(Number(b.dataset.range)===range));
 }
})();
