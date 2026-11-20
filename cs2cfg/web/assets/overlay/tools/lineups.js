/* Read-only browser. The shell owns fetching, persistence and scheduling. */
(() => {
 const {escape:e}=window.overlayUI;
 const types={smoke:'Smoke',fire:'Fire',flash:'Flash',grenade:'Grenade'};
 const synonyms={molly:'fire',molotov:'fire',incendiary:'fire',nade:'grenade',he:'grenade',pop:'flash'};
 function search(rows,query,side,kind){
  const words=(query.toLowerCase().match(/\w+/g)||[]).filter(w=>w!=='site').map(w=>synonyms[w]||w);
  return rows.filter(r=>(!side||r.side===side||r.side==='both')&&(!kind||r.type===kind)&&words.every(w=>(r.name+' '+r.area+' '+r.type).toLowerCase().includes(w)));
 }
 function radar(art,rows){
  if(!art)return '<p class="lineup-empty-art">Radar picture unavailable. You can still browse the instructions below.</p>';
  const o=art.overview,p=v=>[(v.x-o.pos_x)/o.scale,(o.pos_y-v.y)/o.scale];
  let box='0 0 1024 1024';
  if(rows.length===1){const [x,y]=p(rows[0].stand),[u,v]=p(rows[0].land),size=Math.min(1024,Math.max(240,Math.abs(u-x)+120,Math.abs(v-y)+210));box=[Math.max(0,Math.min(1024-size,(x+u-size)/2)),Math.max(0,Math.min(1024-size,(y+v-size)/2-40)),size,size].join(' ');}
  return '<svg class="lineup-radar" viewBox="'+box+'" role="img" aria-label="Stand points and landing areas"><image width="1024" height="1024" href="'+e(art.image)+'"/>'+rows.map((r,i)=>{
   const [x,y]=p(r.stand),[u,v]=p(r.land),c={smoke:'#dce1eb',fire:'#ff873e',flash:'#ffffff',grenade:'#ff5252'}[r.type];
   return '<g><title>'+e(r.name)+'</title><path d="M'+x+' '+y+' Q'+((x+u)/2)+' '+(Math.min(y,v)-90)+' '+u+' '+v+'" fill="none" stroke="'+c+'" stroke-width="5" stroke-dasharray="12 10"/><circle cx="'+x+'" cy="'+y+'" r="10" fill="white" stroke="#111" stroke-width="4"/><circle cx="'+u+'" cy="'+v+'" r="30" fill="'+c+'" fill-opacity=".4" stroke="'+c+'" stroke-width="5"/><text x="'+u+'" y="'+(v+9)+'" text-anchor="middle" fill="white" stroke="#111" stroke-width="3" paint-order="stroke" font-size="28">'+(i+1)+'</text></g>';
  }).join('')+'</svg><p>White point: where to stand · Dashed line: throw direction · Ring: landing area</p>';
 }
 window.lineupsUI={search,radar};
 window.overlayRenderers.lineups=(root,d,call)=>{
  const updateRound=()=>{
   const status=root.querySelector('.lineup-picture-status');if(status)status.textContent=d.picture_status||'';
   const card=root.querySelector('.lineup-round');if(!card)return;
   const round=d.round||{};card.hidden=!round.show;
   card.innerHTML='<strong>Smokes for this round · '+e(round.name)+' · '+e(round.side)+' side</strong><p>'+(round.pinned?'Pinned through the live round.':'Folds away when the round starts. Pin Lineups to keep it visible.')+'</p>';
  };
  if(root.lineupsState&&root.querySelector('[data-query]')&&!d.map_request){updateRound();if(root.paintPictures)root.paintPictures(d.pictures||{});return;}
  const state=root.lineupsState||={query:'',side:'',kind:'',selected:null,map:d.document?.map||'mirage'};
  const doc=d.document,rows=doc?.lineups||[];
  const options=(items,value)=>items.map(([key,label])=>'<option value="'+e(key)+'" '+(key===value?'selected':'')+'>'+e(label)+'</option>').join('');
  root.innerHTML='<p class="lineup-picture-status" role="status"></p><div class="lineup-round" hidden></div><div class="lineups-controls"><label>Find a lineup<input type="text" data-query placeholder="Search name, area or throw" value="'+e(state.query)+'"></label><label>Map<select data-map>'+options((d.maps||[]).map(m=>[m.id,m.name]),state.map)+'</select></label><label>Side<select data-side>'+options([['','Both sides'],['T','T side'],['CT','CT side']],state.side)+'</select></label><label>Throw<select data-kind>'+options([['','All throws'],...Object.entries(types)],state.kind)+'</select></label></div><div class="lineups-grid"><div><div class="lineup-count" aria-live="polite"></div><div class="lineups-results"></div></div><article class="lineup-detail"></article></div><details class="lineups-about"><summary>About Lineups</summary><p>Lineup data: Rene Rebsdorf · CS2-annotations · MIT license. Pictures come from your own CS2 files. Throws await checking in the game.</p></details>';
  const pictures=(images)=>{
   const slot=root.querySelector('.lineup-pictures');if(!slot)return;
   const pair=images[state.selected]||{};
   slot.innerHTML=['stand','aim'].filter(k=>pair[k]).map(k=>'<button class="lineup-thumbnail" data-picture="'+k+'"><img alt="'+(k==='stand'?'Where to stand':'Where to aim')+'" src="'+e(pair[k])+'"><span>'+(k==='stand'?'Stand picture':'Aim picture')+'</span></button>').join('');
   for(const button of slot.querySelectorAll('[data-picture]'))button.onclick=()=>{
    const dialog=document.createElement('dialog');dialog.className='lineup-picture-large';
    dialog.innerHTML='<button autofocus>Close picture</button><img alt="'+button.querySelector('img').alt+'" src="'+e(pair[button.dataset.picture])+'">';
    dialog.querySelector('button').onclick=()=>dialog.close();dialog.onclose=()=>dialog.remove();root.append(dialog);dialog.showModal();
   };
  };root.paintPictures=pictures;
  const paint=()=>{
   const found=search(rows,state.query,state.side,state.kind);
   const selected=found.find(r=>r.id===state.selected)||found[0];state.selected=selected?.id;
   root.querySelector('.lineup-count').textContent=found.length+' '+(found.length===1?'lineup':'lineups')+' · '+(doc?.name||'Choose a map');
   const list=root.querySelector('.lineups-results');
   list.innerHTML=found.map((r,i)=>'<button class="lineup-row" data-lineup="'+e(r.id)+'" aria-pressed="'+(r===selected)+'"><strong>'+e(r.name)+'</strong><small>'+e(types[r.type])+' · '+e(r.area+(['A','B'].includes(r.area)?' site':''))+' · '+e(r.side==='both'?'Both sides':r.side+' side')+'</small></button>').join('')||'<p>No lineups match. Try another search or side.</p>';
   root.querySelector('.lineup-detail').innerHTML=selected?'<h4>'+e(selected.name)+'</h4><p class="lineup-meta">'+e(types[selected.type])+' · '+e(selected.throw[0].toUpperCase()+selected.throw.slice(1))+' · '+(selected.checked?'Checked in game':'Awaiting game check')+'</p>'+radar(d.art,[selected])+'<ol>'+selected.steps.map(s=>'<li>'+e(s)+'</li>').join('')+'</ol><div class="lineup-pictures"></div>':'<p>Choose a lineup to see where to stand and how to throw.</p>';
   pictures(d.pictures||{});
   for(const button of list.querySelectorAll('[data-lineup]'))button.onclick=()=>{state.selected=button.dataset.lineup;paint();};
  };
  root.querySelector('[data-query]').oninput=event=>{state.query=event.target.value;paint();};
  for(const key of ['side','kind'])root.querySelector('[data-'+key+']').onchange=event=>{state[key]=event.target.value;paint();};
  root.querySelector('[data-map]').onchange=async event=>{
   state.map=event.target.value;state.selected=null;
   const result=await call('data',{map:state.map});window.overlayRenderers.lineups(root,result,call);
  };
  paint();
  updateRound();
 };
})();
