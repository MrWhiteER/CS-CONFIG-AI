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
   if(!r.land){const [x,y]=p(r.stand);return '<g><title>'+e(r.name)+'</title><circle cx="'+x+'" cy="'+y+'" r="10" fill="white" stroke="#111" stroke-width="4"/></g>';}
   const [x,y]=p(r.stand),[u,v]=p(r.land||r.stand),c={smoke:'#dce1eb',fire:'#ff873e',flash:'#ffffff',grenade:'#ff5252'}[r.type];
   return '<g><title>'+e(r.name)+'</title><path d="M'+x+' '+y+' Q'+((x+u)/2)+' '+(Math.min(y,v)-90)+' '+u+' '+v+'" fill="none" stroke="'+c+'" stroke-width="5" stroke-dasharray="12 10"/><circle cx="'+x+'" cy="'+y+'" r="10" fill="white" stroke="#111" stroke-width="4"/><circle cx="'+u+'" cy="'+v+'" r="30" fill="'+c+'" fill-opacity=".4" stroke="'+c+'" stroke-width="5"/><text x="'+u+'" y="'+(v+9)+'" text-anchor="middle" fill="white" stroke="#111" stroke-width="3" paint-order="stroke" font-size="28">'+(i+1)+'</text></g>';
  }).join('')+'</svg><p>White point: where to stand · Dashed line: throw direction · Ring: landing area</p>';
 }
 window.lineupsUI={search,radar};
 window.overlayRenderers.lineups=(root,d,call)=>{
  root.lineupLatest=d;
  root.updateLineupPosition?.();
  root.updateLineupCapture?.(d.creating);
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
   const pair=images[state.selected]||{},selected=rows.find(r=>r.id===state.selected);
   const marker=k=>{const m=selected?.pictures?.[k]?.marker||selected?.picture_markers?.[k]||[.5,.5];return '<span class="lineup-image-marker '+(k==='stand'?'feet':'aim')+'" style="left:'+m[0]*100+'%;top:'+m[1]*100+'%" aria-hidden="true">'+(k==='stand'?'?':'')+'</span>';};
   slot.classList.toggle('has-pictures',!!(pair.stand||pair.aim));
   slot.innerHTML=!(pair.stand||pair.aim)?'<div class="lineup-no-pictures"><strong>No pictures yet</strong><button data-take-pictures>'+(selected?.mine?'Take pictures':'Make lineup pictures')+'</button></div>':['stand','aim'].map(k=>'<button class="lineup-thumbnail" data-picture="'+k+'"><span class="lineup-photo"><img alt="'+(k==='stand'?'Where to stand':'Where to aim')+'" src="'+e(pair[k]||'')+'">'+marker(k)+'</span><span>'+(k==='stand'?'Where you stand':'Where you aim')+'</span></button>').join('');
   const take=slot.querySelector('[data-take-pictures]');if(take)take.onclick=async()=>{await root.openLineupForm(selected);root.querySelector('[data-create]')?.click();};
   for(const button of slot.querySelectorAll('[data-picture]'))button.onclick=()=>{
    const dialog=document.createElement('dialog');dialog.className='lineup-picture-large';
    dialog.innerHTML='<button autofocus>Close picture</button><span class="lineup-photo"><img alt="'+button.querySelector('img').alt+'" src="'+e(pair[button.dataset.picture])+'">'+marker(button.dataset.picture)+'</span>';
    dialog.querySelector('button').onclick=()=>dialog.close();dialog.onclose=()=>dialog.remove();root.append(dialog);dialog.showModal();
   };
  };root.paintPictures=pictures;
  const paint=()=>{
   const found=search(rows,state.query,state.side,state.kind);
   const selected=found.find(r=>r.id===state.selected)||found[0];state.selected=selected?.id;
   root.querySelector('.lineup-count').textContent=found.length+' '+(found.length===1?'lineup':'lineups')+' · '+(doc?.name||'Choose a map');
   const list=root.querySelector('.lineups-results');
   list.innerHTML=found.map((r,i)=>'<button class="lineup-row" data-lineup="'+e(r.id)+'" aria-pressed="'+(r===selected)+'"><strong>'+e(r.name)+'</strong>'+(r.mine?'<small>Made by you</small>':'')+'<small>'+e(types[r.type])+' · '+e(r.area+(['A','B'].includes(r.area)?' site':''))+' · '+e(r.side==='both'?'Both sides':r.side+' side')+'</small></button>').join('')||'<p>No lineups match. Try another search or side.</p>';
   root.querySelector('.lineup-detail').innerHTML=selected?'<h4>'+e(selected.name)+'</h4>'+(selected.mine?'<div class="lineup-own-actions"><span>Made by you</span> <button data-edit>Edit</button> <button data-delete>Delete</button></div>':'')+'<p class="lineup-meta">'+e(types[selected.type])+' · '+e(selected.throw[0].toUpperCase()+selected.throw.slice(1))+' · '+(selected.checked?'Checked in game':'Awaiting game check')+'</p><div class="lineup-detail-body"><button class="lineup-corner-map" title="Enlarge map" aria-label="Enlarge map">'+radar(d.art,[selected])+'</button><div class="lineup-pictures"></div><ol>'+selected.steps.map(s=>'<li>'+e(s)+'</li>').join('')+'</ol></div>':'<p>Choose a lineup to see where to stand and how to throw.</p>';
   pictures(root.pictureImages||d.pictures||{});
   const mapButton=root.querySelector('.lineup-corner-map');if(mapButton)mapButton.onclick=()=>{const dialog=document.createElement('dialog');dialog.className='lineup-picture-large';dialog.innerHTML='<button>Close map</button>'+radar(d.art,[selected]);dialog.querySelector('button').onclick=()=>dialog.close();dialog.onclose=()=>dialog.remove();root.append(dialog);dialog.showModal();};
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
  let pictureEdits=null;
  let stand=row?.stand||null,land=row?.land||null,aim=row?.aim||null,placing='stand',placedByUser=!!row;
  const dialog=document.createElement('dialog');dialog.className='lineup-editor';
  const select=(name,label,values,value)=>'<label>'+label+'<select name="'+name+'">'+values.map(([v,t])=>'<option value="'+e(v)+'" '+(v===value?'selected':'')+'>'+e(t)+'</option>').join('')+'</select></label>';
  dialog.innerHTML='<form><header><h3>'+(edit?'Edit lineup':'New lineup')+'</h3><button type="button" data-cancel>Cancel</button></header><div class="lineup-editor-columns"><div class="lineup-editor-fields"><label>Name<input name="name" required maxlength="240" value="'+e(row?.name||'')+'" placeholder="My window smoke"></label><div class="lineup-field-pair">'+select('map','Map',(initial.maps||[]).map(m=>[m.id,m.name]),key)+select('side','Side',[['T','T side'],['CT','CT side']],row?.side||'T')+'</div><div class="lineup-field-pair">'+select('type','Type',[['smoke','Smoke'],['fire','Fire'],['flash','Flash'],['grenade','Grenade']],row?.type||'smoke')+select('throw','Throw',[['left click','Left click'],['right click','Right click'],['both','Both'],['jump throw','Jump throw'],['run throw','Run throw'],['walk throw','Walk throw']],row?.throw||'left click')+'</div><label>Area<input name="area" required maxlength="240" value="'+e(row?.area||'')+'" placeholder="A site"></label><label>Steps and details <small>One step per line</small><textarea name="steps" required rows="5">'+e((row?.steps||[]).join('\n'))+'</textarea></label></div><div class="lineup-editor-places"><h4>Where you stand</h4><p>Drag the feet onto the radar. You can also click a spot or move the marker with arrow keys.</p><div data-edit-radar></div><div class="lineup-marker-tools"><button type="button" data-stand>Place feet</button><button type="button" data-land>Place landing ring</button><button type="button" data-clear-land>Remove ring</button></div><button type="button" data-position>Use my game position</button><p data-position-note role="status"></p><button type="button" data-create>Take pictures</button><p data-create-note role="status"></p></div></div><footer><p data-error role="status"></p><button type="submit">Save lineup</button></footer></form>';
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
   const move=event=>{const p=svg.createSVGPoint();p.x=event.clientX;p.y=event.clientY;const q=p.matrixTransform(svg.getScreenCTM().inverse());const point={radar_x:Math.max(0,Math.min(o.width,q.x)),radar_y:Math.max(0,Math.min(o.height,q.y))};if(placing==='stand'){stand=point;aim=null;placedByUser=true;}else land=point;const g=svg.querySelector('[data-marker="'+placing+'"]');if(g)g.setAttribute('transform','translate('+point.radar_x+' '+point.radar_y+')');};
   svg.onpointerdown=event=>{event.preventDefault();placing=event.target.closest('[data-marker]')?.dataset.marker||placing;if(placing==='land'&&!land){land={radar_x:0,radar_y:0};paint();slot.querySelector('svg').dispatchEvent(new PointerEvent('pointerdown',{clientX:event.clientX,clientY:event.clientY,pointerId:event.pointerId,bubbles:true}));return;}svg.setPointerCapture(event.pointerId);move(event);};
   svg.onpointermove=event=>{if(svg.hasPointerCapture(event.pointerId))move(event);};
   svg.onpointerup=event=>{if(svg.hasPointerCapture(event.pointerId))svg.releasePointerCapture(event.pointerId);};
   for(const g of svg.querySelectorAll('[data-marker]'))g.onkeydown=event=>{const delta={ArrowLeft:[-4,0],ArrowRight:[4,0],ArrowUp:[0,-4],ArrowDown:[0,4]}[event.key];if(!delta)return;event.preventDefault();placing=g.dataset.marker;const p=pixel(placing==='stand'?stand:land);const next={radar_x:Math.max(0,Math.min(o.width,p[0]+delta[0])),radar_y:Math.max(0,Math.min(o.height,p[1]+delta[1]))};if(placing==='stand'){stand=next;aim=null;placedByUser=true;}else land=next;g.setAttribute('transform','translate('+next.radar_x+' '+next.radar_y+')');};
  }
  function position(){const pos=(root.lineupLatest||d).position;if(pos?.map===key){stand=pos.stand;aim=pos.aim;placedByUser=true;dialog.querySelector('[data-position-note]').textContent='Your game position and aim were placed.';paint();}else dialog.querySelector('[data-position-note]').textContent=(pos?'Choose your current game map to use your position.':(root.lineupLatest||d).position_notice||'The game has not shared your position yet. Move a step and press again.');}
  root.updateLineupPosition=()=>{if(!placedByUser)position();};
  const close=async()=>{await call('creating',{action:'cancel'});delete root.updateLineupCapture;delete root.updateLineupPosition;dialog.close();dialog.remove();await call('editing',{active:false,map:state.map});};
  dialog.querySelector('[data-cancel]').onclick=close;dialog.oncancel=event=>{event.preventDefault();close();};
  dialog.querySelector('[data-stand]').onclick=()=>{placing='stand';};
  dialog.querySelector('[data-land]').onclick=()=>{placing='land';if(!land&&overview()){land={radar_x:overview().width*.6,radar_y:overview().height*.4};paint();}};
  dialog.querySelector('[data-clear-land]').onclick=()=>{land=null;placing='stand';paint();};
  dialog.querySelector('[data-position]').onclick=position;
  let shownShot=null,shownSession=null;const dropped=new Set();
  const removePictures=async()=>{if(shownSession)dropped.add(shownSession);dialog.querySelector('.lineup-review')?.remove();pictureEdits=null;shownShot=null;await call('creating',{action:'cancel'});dialog.querySelector('.lineup-editor-columns').hidden=false;dialog.querySelector('[data-create-note]').textContent='Pictures removed. Take pictures again or save without them.';};
  root.updateLineupCapture=capture=>{
   if(!capture?.review||dropped.has(capture.session)||(capture.session===shownSession&&capture.shot===shownShot))return;
   const replaced=shownShot!==null&&capture.session===shownSession;shownShot=capture.shot;shownSession=capture.session;dialog.querySelector('.lineup-review')?.remove();
   pictureEdits={stand:replaced&&pictureEdits?pictureEdits.stand:{crop:[0,0,1,1],marker:[.5,.5]},aim:replaced&&pictureEdits?pictureEdits.aim:{crop:[0,0,1,1],marker:[.5,.5]}};
   const review=document.createElement('section');review.className='lineup-review';
   review.innerHTML='<h3>Review pictures</h3><p>Crop removes the game HUD. Drag a crop box, then place the feet or aim ring. Keep whole leaves the full picture.</p><div class="lineup-review-pair">'+['stand','aim'].map(k=>'<div><h4>'+(k==='stand'?'Where you stand':'Where you aim')+'</h4><canvas data-review="'+k+'" aria-label="Drag to crop or place marker"></canvas><button type="button" data-crop="'+k+'">Crop</button> <button type="button" data-whole="'+k+'">Keep whole</button> <button type="button" data-mark="'+k+'">Place '+(k==='stand'?'feet':'aim ring')+'</button> <button type="button" data-retake="'+k+'">Retake</button></div>').join('')+'</div><button type="button" data-done-review>Keep pictures</button> <button type="button" data-remove-pictures>Remove pictures</button>';
   dialog.querySelector('footer').before(review);dialog.querySelector('.lineup-editor-columns').hidden=true;
   review.querySelector('[data-done-review]').onclick=()=>{review.hidden=true;dialog.querySelector('.lineup-editor-columns').hidden=false;};
   review.querySelector('[data-remove-pictures]').onclick=removePictures;
   for(const kind of ['stand','aim']){
    const canvas=review.querySelector('[data-review="'+kind+'"]'),image=new Image();let mode='marker',origin=null,box=null;
    const draw=()=>{const ctx=canvas.getContext('2d'),ed=pictureEdits[kind],c=ed.crop,w=canvas.width,h=canvas.height;ctx.clearRect(0,0,w,h);ctx.drawImage(image,c[0]*image.width,c[1]*image.height,c[2]*image.width,c[3]*image.height,0,0,w,h);ctx.strokeStyle='#ffe36a';ctx.fillStyle='#ffe36a';ctx.lineWidth=3;const [x,y]=ed.marker.map((v,i)=>v*(i?h:w));ctx.beginPath();if(kind==='aim')ctx.arc(x,y,12,0,Math.PI*2);else{ctx.ellipse(x-5,y,3,9,-.2,0,Math.PI*2);ctx.ellipse(x+5,y+4,3,9,.2,0,Math.PI*2);}ctx.stroke();if(box)ctx.strokeRect(box[0]*w,box[1]*h,box[2]*w,box[3]*h);};
    image.onload=()=>{canvas.width=600;canvas.height=Math.round(600*image.height/image.width);draw();};image.src=capture.frames[kind];
    const point=ev=>{const b=canvas.getBoundingClientRect();return [Math.max(0,Math.min(1,(ev.clientX-b.left)/b.width)),Math.max(0,Math.min(1,(ev.clientY-b.top)/b.height))];};
    canvas.onpointerdown=ev=>{canvas.setPointerCapture(ev.pointerId);origin=point(ev);if(mode==='marker'){pictureEdits[kind].marker=origin;draw();}};
    canvas.onpointermove=ev=>{if(!canvas.hasPointerCapture(ev.pointerId))return;const p=point(ev);if(mode==='marker')pictureEdits[kind].marker=p;else box=[Math.min(origin[0],p[0]),Math.min(origin[1],p[1]),Math.abs(p[0]-origin[0]),Math.abs(p[1]-origin[1])];draw();};
    canvas.onpointerup=ev=>{canvas.releasePointerCapture(ev.pointerId);if(mode==='crop'&&box&&box[2]>.01&&box[3]>.01){const ed=pictureEdits[kind],c=ed.crop;ed.crop=[c[0]+box[0]*c[2],c[1]+box[1]*c[3],box[2]*c[2],box[3]*c[3]];ed.marker=[.5,.5];}box=null;mode='marker';draw();};
    review.querySelector('[data-crop="'+kind+'"]').onclick=()=>{mode='crop';};
    review.querySelector('[data-mark="'+kind+'"]').onclick=()=>{mode='marker';};
    review.querySelector('[data-whole="'+kind+'"]').onclick=()=>{pictureEdits[kind].crop=[0,0,1,1];draw();};
    review.querySelector('[data-retake="'+kind+'"]').onclick=async()=>{review.hidden=true;pictureEdits[kind]={crop:[0,0,1,1],marker:[.5,.5]};const result=await call('creating',{action:'retake',kind});dialog.querySelector('[data-create-note]').textContent=result.text||'';if(!result.active)dialog.querySelector('.lineup-editor-columns').hidden=false;};
   }
  };
  dialog.querySelector('[data-create]').onclick=async()=>{if(shownSession)dropped.add(shownSession);dialog.querySelector('.lineup-review')?.remove();pictureEdits=null;shownShot=null;shownSession=null;const result=await call('creating',{action:'start',map:key,builtin:row&&!row.mine?row.id:null});dialog.querySelector('[data-create-note]').textContent=result.text||'';};
  field('map').disabled=edit;
  field('map').onchange=async()=>{key=field('map').value;stand=land=aim=null;placedByUser=false;d=await call('data',{map:key});paint();position();};
  form.noValidate=true;
  form.onsubmit=async event=>{event.preventDefault();const err=dialog.querySelector('[data-error]');dialog.querySelector('.lineup-review')?.setAttribute('hidden','');dialog.querySelector('.lineup-editor-columns').hidden=false;
   const missing=[...form.querySelectorAll('[required]')].find(f=>!f.disabled&&!String(f.value).trim());if(missing){err.textContent='Fill in '+(missing.closest('label')?.firstChild?.textContent||'every field').trim()+' first.';missing.focus();return;}
   if(!stand||!overview()){dialog.querySelector('[data-error]').textContent='Choose a map and place your feet first.';return;}
   const values=Object.fromEntries(new FormData(form));const saved={id:row?.id,name:(values.name??row?.name??'').trim(),side:values.side??row?.side,type:values.type??row?.type,throw:values.throw??row?.throw,area:(values.area??row?.area??'').trim(),pictures:row?.pictures,steps:(values.steps??row?.steps?.join('\n')??'').split('\n').map(s=>s.trim()).filter(Boolean),stand,land,aim};
   let result;try{result=await call('change',{action:row&&!row.mine?'save_pictures':'save',map:key,row:saved,overview:overview(),picture_edits:pictureEdits});}catch(_){err.textContent='Could not save your change. Try again.';return;}
   if(!result||result.available===false){err.textContent='Open the overlay panel, then save again.';return;}
   if(result.notice){err.textContent=result.notice;return;}
   state.map=key;await close();window.overlayRenderers.lineups(root,result,call);
  };
  if(key!==d.document?.map)d=await call('data',{map:key});
  paint();
  if(row&&!row.mine){for(const element of dialog.querySelectorAll('.lineup-editor-fields input,.lineup-editor-fields textarea,.lineup-editor-fields select'))element.disabled=true;dialog.querySelector('h3').textContent='Make lineup pictures';}
  const fresh=await call('editing',{active:true,map:key});root.lineupLatest=fresh||d;if(!edit)position();
 };
})();
