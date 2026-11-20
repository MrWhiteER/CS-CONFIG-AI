/* Read-only browser. The shell owns fetching, persistence and scheduling. */
(() => {
 const {escape:e}=window.overlayUI;
 const types={smoke:'Smoke',fire:'Fire',flash:'Flash',grenade:'Grenade'};
 const synonyms={molly:'fire',molotov:'fire',incendiary:'fire',nade:'grenade',he:'grenade',pop:'flash'};
 function search(rows,query,side,kind){
  const words=(query.toLowerCase().match(/\w+/g)||[]).filter(w=>w!=='site').map(w=>synonyms[w]||w);
  return rows.filter(r=>(!side||r.side===side||r.side==='both')&&(!kind||(kind==='mine'?r.mine===true:r.type===kind))&&words.every(w=>(r.name+' '+r.area+' '+r.type).toLowerCase().includes(w)));
 }
 function radar(art,rows){
  if(!art)return '<p class="lineup-empty-art">Radar picture unavailable. You can still browse the instructions below.</p>';
  const o=art.overview,p=v=>v.radar_x!==undefined?[v.radar_x,v.radar_y]:[(v.x-o.pos_x)/o.scale,(o.pos_y-v.y)/o.scale];
  let box='0 0 1024 1024';
  if(rows.length===1){const [x,y]=p(rows[0].stand),[u,v]=p(rows[0].land||rows[0].stand),size=Math.min(1024,Math.max(240,Math.abs(u-x)+120,Math.abs(v-y)+210));box=[Math.max(0,Math.min(1024-size,(x+u-size)/2)),Math.max(0,Math.min(1024-size,(y+v-size)/2-40)),size,size].join(' ');}
  return '<svg class="lineup-radar" viewBox="'+box+'" role="img" aria-label="Stand points and landing areas"><image width="1024" height="1024" href="'+e(art.image)+'"/>'+rows.map((r,i)=>{
   const [x,y]=p(r.stand),[u,v]=p(r.land||r.stand),c={smoke:'#dce1eb',fire:'#ff873e',flash:'#ffffff',grenade:'#ff5252'}[r.type];
   return '<g><title>'+e(r.name)+'</title><path d="M'+x+' '+y+' Q'+((x+u)/2)+' '+(Math.min(y,v)-90)+' '+u+' '+v+'" fill="none" stroke="'+c+'" stroke-width="5" stroke-dasharray="12 10"/><circle cx="'+x+'" cy="'+y+'" r="10" fill="white" stroke="#111" stroke-width="4"/><circle cx="'+u+'" cy="'+v+'" r="30" fill="'+c+'" fill-opacity=".4" stroke="'+c+'" stroke-width="5"/><text x="'+u+'" y="'+(v+9)+'" text-anchor="middle" fill="white" stroke="#111" stroke-width="3" paint-order="stroke" font-size="28">'+(i+1)+'</text></g>';
  }).join('')+'</svg><p>White point: where to stand · Dashed line: throw direction · Ring: landing area</p>';
 }
 window.lineupsUI={search,radar};
 window.overlayRenderers.lineups=(root,d,call)=>{
  root.lineupLatest=d;
  const updateRound=()=>{
   const status=root.querySelector('.lineup-picture-status');if(status)status.textContent=d.picture_status||'';
   const stop=root.querySelector('[data-stop-pictures]');if(stop)stop.hidden=!d.picture_active;
   const card=root.querySelector('.lineup-round');if(!card)return;
   const round=d.round||{};card.hidden=!round.show;
   card.innerHTML='<strong>Smokes for this round · '+e(round.name)+' · '+e(round.side)+' side</strong><p>'+(round.pinned?'Pinned through the live round.':'Folds away when the round starts. Pin Lineups to keep it visible.')+'</p>';
  };
  if(root.lineupsState&&root.querySelector('[data-query]')&&!d.map_request){updateRound();if(root.paintPictures)root.paintPictures(d.pictures||{});return;}
  const state=root.lineupsState||={query:'',side:'',kind:'',selected:null,map:d.document?.map||'mirage'};
  const doc=d.document,rows=doc?.lineups||[];root.pictureImages=d.pictures||{};
  const options=(items,value)=>items.map(([key,label])=>'<option value="'+e(key)+'" '+(key===value?'selected':'')+'>'+e(label)+'</option>').join('');
  root.innerHTML='<div class="lineup-own-toolbar"><button data-new>New lineup</button><span role="status">'+e(d.notice||'')+'</span>'+(d.undo_available?'<span role="status">Lineup deleted. <button data-undo>Undo</button></span>':'')+'</div><div class="lineup-picture-progress"><p class="lineup-picture-status" role="status"></p><button data-stop-pictures hidden>Stop pictures</button></div><div class="lineup-round" hidden></div><div class="lineups-controls"><label>Find a lineup<input type="text" data-query placeholder="Search name, area or throw" value="'+e(state.query)+'"></label><label>Map<select data-map>'+options((d.maps||[]).map(m=>[m.id,m.name]),state.map)+'</select></label><label>Side<select data-side>'+options([['','Both sides'],['T','T side'],['CT','CT side']],state.side)+'</select></label><label>Throw<select data-kind>'+options([['','All throws'],['mine','Made by you'],...Object.entries(types)],state.kind)+'</select></label></div><div class="lineups-grid"><div><div class="lineup-count" aria-live="polite"></div><div class="lineups-results"></div></div><article class="lineup-detail"></article></div><details class="lineups-about"><summary>About Lineups</summary><p>Lineup data: Rene Rebsdorf · CS2-annotations · MIT license. Pictures come from your own CS2 files. Throws await checking in the game.</p></details>';
  const undo=root.querySelector('[data-undo]');if(undo)undo.onclick=async()=>window.overlayRenderers.lineups(root,await call('change',{action:'undo',map:state.map}),call);
  root.openLineupForm=row=>window.lineupsUI.form(root,root.lineupLatest,call,row);
  root.querySelector('[data-new]').onclick=()=>root.openLineupForm();
  root.querySelector('[data-stop-pictures]').onclick=async event=>{
   event.target.disabled=true;
   try{window.overlayRenderers.lineups(root,await call('stop_pictures',{}),call);}
   finally{event.target.disabled=false;}
  };
  const pictures=(images)=>{
   const slot=root.querySelector('.lineup-pictures');if(!slot)return;
   root.pictureImages=images;
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
   list.innerHTML=found.map((r,i)=>'<button class="lineup-row" data-lineup="'+e(r.id)+'" aria-pressed="'+(r===selected)+'"><strong>'+e(r.name)+'</strong>'+(r.mine?'<small>Made by you</small>':'')+'<small>'+e(types[r.type])+' · '+e(r.area+(['A','B'].includes(r.area)?' site':''))+' · '+e(r.side==='both'?'Both sides':r.side+' side')+'</small></button>').join('')||'<p>No lineups match. Try another search or side.</p>';
   root.querySelector('.lineup-detail').innerHTML=selected?'<h4>'+e(selected.name)+'</h4>'+(selected.mine?'<div class="lineup-own-actions"><span>Made by you</span> <button data-edit>Edit</button> <button data-delete>Delete</button></div>':'')+'<p class="lineup-meta">'+e(types[selected.type])+' · '+e(selected.throw[0].toUpperCase()+selected.throw.slice(1))+' · '+(selected.checked?'Checked in game':'Awaiting game check')+'</p><div class="lineup-detail-body"><div class="lineup-visual">'+radar(d.art,[selected])+'<div class="lineup-pictures"></div></div><ol>'+selected.steps.map(s=>'<li>'+e(s)+'</li>').join('')+'</ol></div>':'<p>Choose a lineup to see where to stand and how to throw.</p>';
   pictures(root.pictureImages||d.pictures||{});
   const remove=root.querySelector('[data-delete]');if(remove)remove.onclick=async()=>{
    const result=await call('change',{action:'delete',map:state.map,id:selected.id});
    window.overlayRenderers.lineups(root,result,call);
   };
   const edit=root.querySelector('[data-edit]');if(edit)edit.onclick=()=>root.openLineupForm?.(selected);
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
/* Personal lineup editor. Drafts survive ordinary tool refreshes. */
(() => {
 const e=window.overlayUI.escape;
 window.lineupsUI.form=async(root,initial,call,row)=>{
  if(root.querySelector('.lineup-editor'))return;
  const edit=!!row, state=root.lineupsState;
  let d=initial, key=row?state.map:(initial.position?.map||initial.round?.map||state.map);
  if(!(initial.maps||[]).some(m=>m.id===key))key=state.map;
  let stand=row?.stand||null,land=row?.land||null,aim=row?.aim||null,placing='stand';
  const dialog=document.createElement('dialog');dialog.className='lineup-editor';
  const select=(name,label,values,value)=>'<label>'+label+'<select name="'+name+'">'+values.map(([v,t])=>'<option value="'+e(v)+'" '+(v===value?'selected':'')+'>'+e(t)+'</option>').join('')+'</select></label>';
  dialog.innerHTML='<form><header><h3>'+(edit?'Edit lineup':'New lineup')+'</h3><button type="button" data-cancel>Cancel</button></header><div class="lineup-editor-columns"><div class="lineup-editor-fields"><label>Name<input name="name" required maxlength="240" value="'+e(row?.name||'')+'" placeholder="My window smoke"></label><div class="lineup-field-pair">'+select('map','Map',(initial.maps||[]).map(m=>[m.id,m.name]),key)+select('side','Side',[['T','T side'],['CT','CT side']],row?.side||'T')+'</div><div class="lineup-field-pair">'+select('type','Type',[['smoke','Smoke'],['fire','Fire'],['flash','Flash'],['grenade','Grenade']],row?.type||'smoke')+select('throw','Throw',[['left click','Left click'],['right click','Right click'],['both','Both'],['jump throw','Jump throw'],['run throw','Run throw'],['walk throw','Walk throw']],row?.throw||'left click')+'</div><label>Area<input name="area" required maxlength="240" value="'+e(row?.area||'')+'" placeholder="A site"></label><label>Steps and details <small>One step per line</small><textarea name="steps" required rows="5">'+e((row?.steps||[]).join('\n'))+'</textarea></label></div><div class="lineup-editor-places"><h4>Where you stand</h4><p>Drag the feet onto the radar. You can also click a spot or move the marker with arrow keys.</p><div data-edit-radar></div><div class="lineup-marker-tools"><button type="button" data-stand>Place feet</button><button type="button" data-land>Place landing ring</button><button type="button" data-clear-land>Remove ring</button></div><button type="button" data-position>Use my game position</button><p data-position-note role="status"></p><button type="button" data-create>Take two pictures</button><p data-create-note role="status"></p></div></div><footer><p data-error role="status"></p><button type="submit">Save lineup</button></footer></form>';
  root.append(dialog);dialog.showModal();
  const form=dialog.querySelector('form'),field=n=>form.elements.namedItem(n),slot=dialog.querySelector('[data-edit-radar]');
  const overview=()=>d.art?.overview||d.document?.overview;
  const pixel=p=>p?.radar_x!==undefined?[p.radar_x,p.radar_y]:p&&overview()?[(p.x-overview().pos_x)/overview().scale,(overview().pos_y-p.y)/overview().scale]:null;
  const feet='<path transform="scale(2)" d="M-12 -22c-8 0-10 11-8 20l4 14h10l1-17c1-9 0-17-7-17zm24 10c-7 0-8 8-7 17l1 17h10l4-14c2-9 0-20-8-20z" fill="currentColor" stroke="#111" stroke-width="3"/>';
  function paint(){
   const o=overview();
   if(!o){slot.innerHTML='<p class="lineup-empty-art">Radar placement is unavailable for this map. Install CS2 or choose a map with a radar to place your feet.</p>';return;}
   if(!stand)stand={radar_x:o.width/2,radar_y:o.height/2};
   const marker=(point,kind)=>{const p=pixel(point);return p?'<g tabindex="0" role="slider" aria-label="'+(kind==='stand'?'Feet':'Landing ring')+'; use arrow keys to move" data-marker="'+kind+'" transform="translate('+p.join(' ')+')" style="color:'+(kind==='stand'?'#ffdf69':'#97d8ff')+'">'+(kind==='stand'?feet:'<circle r="30" fill="none" stroke="currentColor" stroke-width="8"/>')+'</g>':'';};
   slot.innerHTML='<svg viewBox="0 0 '+o.width+' '+o.height+'" class="lineup-placement" aria-label="Place your lineup markers">'+(d.art?'<image width="'+o.width+'" height="'+o.height+'" href="'+e(d.art.image)+'"/>':'<rect width="100%" height="100%" fill="#26343e"/><path d="M0 512H1024M512 0V1024" stroke="#84919a" stroke-width="2"/><text x="30" y="70" fill="white" font-size="32">Radar picture unavailable</text>')+marker(stand,'stand')+marker(land,'land')+'</svg>';
   const svg=slot.querySelector('svg');
   const move=event=>{const p=svg.createSVGPoint();p.x=event.clientX;p.y=event.clientY;const q=p.matrixTransform(svg.getScreenCTM().inverse());const point={radar_x:Math.max(0,Math.min(o.width,q.x)),radar_y:Math.max(0,Math.min(o.height,q.y))};if(placing==='stand'){stand=point;aim=null;}else land=point;const g=svg.querySelector('[data-marker="'+placing+'"]');if(g)g.setAttribute('transform','translate('+point.radar_x+' '+point.radar_y+')');};
   svg.onpointerdown=event=>{event.preventDefault();placing=event.target.closest('[data-marker]')?.dataset.marker||placing;if(placing==='land'&&!land){land={radar_x:0,radar_y:0};paint();slot.querySelector('svg').dispatchEvent(new PointerEvent('pointerdown',{clientX:event.clientX,clientY:event.clientY,pointerId:event.pointerId,bubbles:true}));return;}svg.setPointerCapture(event.pointerId);move(event);};
   svg.onpointermove=event=>{if(svg.hasPointerCapture(event.pointerId))move(event);};
   svg.onpointerup=event=>{if(svg.hasPointerCapture(event.pointerId))svg.releasePointerCapture(event.pointerId);};
   for(const g of svg.querySelectorAll('[data-marker]'))g.onkeydown=event=>{const delta={ArrowLeft:[-4,0],ArrowRight:[4,0],ArrowUp:[0,-4],ArrowDown:[0,4]}[event.key];if(!delta)return;event.preventDefault();placing=g.dataset.marker;const p=pixel(placing==='stand'?stand:land);const next={radar_x:Math.max(0,Math.min(o.width,p[0]+delta[0])),radar_y:Math.max(0,Math.min(o.height,p[1]+delta[1]))};if(placing==='stand'){stand=next;aim=null;}else land=next;g.setAttribute('transform','translate('+next.radar_x+' '+next.radar_y+')');};
  }
  function position(){const pos=(root.lineupLatest||d).position;if(pos?.map===key){stand=pos.stand;aim=pos.aim;dialog.querySelector('[data-position-note]').textContent='Your game position and aim were placed.';paint();}else dialog.querySelector('[data-position-note]').textContent='Your position is not available. Drag the feet onto the radar.';}
  const close=async()=>{dialog.close();dialog.remove();await call('editing',{active:false,map:state.map});};
  dialog.querySelector('[data-cancel]').onclick=close;dialog.oncancel=event=>{event.preventDefault();close();};
  dialog.querySelector('[data-stand]').onclick=()=>{placing='stand';};
  dialog.querySelector('[data-land]').onclick=()=>{placing='land';if(!land&&overview()){land={radar_x:overview().width*.6,radar_y:overview().height*.4};paint();}};
  dialog.querySelector('[data-clear-land]').onclick=()=>{land=null;placing='stand';paint();};
  dialog.querySelector('[data-position]').onclick=position;
  dialog.querySelector('[data-create]').onclick=async()=>{const result=await call('creating',{map:key});dialog.querySelector('[data-create-note]').textContent=result.text;};
  field('map').disabled=edit;
  field('map').onchange=async()=>{key=field('map').value;stand=land=aim=null;d=await call('data',{map:key});paint();position();};
  form.onsubmit=async event=>{event.preventDefault();if(!stand||!overview()){dialog.querySelector('[data-error]').textContent='Choose a map and place your feet first.';return;}
   const values=Object.fromEntries(new FormData(form));const saved={id:row?.id,name:values.name.trim(),side:values.side,type:values.type,throw:values.throw,area:values.area.trim(),steps:values.steps.split('\n').map(s=>s.trim()).filter(Boolean),stand,land,aim};
   const result=await call('change',{action:'save',map:key,row:saved,overview:overview()});
   if(result.notice){dialog.querySelector('[data-error]').textContent=result.notice;return;}
   state.map=key;await close();window.overlayRenderers.lineups(root,result,call);
  };
  if(key!==d.document?.map)d=await call('data',{map:key});
  paint();
  const fresh=await call('editing',{active:true,map:key});root.lineupLatest=fresh||d;if(!edit)position();
 };
})();
