/* Single WebView scheduler. Hidden shell = zero timers, requests or rendering. */
(() => {
 'use strict';
 const $=id=>document.getElementById(id),{icon,escape:e}=window.overlayUI;
 const params=new URLSearchParams(location.search),preview=params.get('preview')==='1';
 let closing=false,requested=false,active=false,generation=0,controller=null,clockTimer=null,z=1,manifest=null,settings={},layout={},saveChain=Promise.resolve();
 const windows=new Map(),timers=new Map(),requests=new Map();
 function report(error){if(active&&error?.name!=='AbortError')$('error').textContent=error.message||String(error);}
 async function api(path,body,signal=controller?.signal){
  if(preview)throw new Error('Preview changes are disabled');
  const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-CS2CFG-Token':window.overlayToken},...(body===undefined?{}:{body:JSON.stringify(body)}),signal});
  const data=await response.json();if(!response.ok||data.ok===false)throw new Error(data.error||'Request failed');return data;
 }
 function entry(id){const row=layout[id]||={open:['performance','hardware'].includes(id),pinned:false};row.opacity??=60;return row;}
 function visible(id){return active&&settings.overlay_tools.includes(id)&&entry(id).open;}
 function cancelTool(id){clearTimeout(timers.get(id));timers.delete(id);requests.get(id)?.abort();requests.delete(id);}
 async function refresh(tool,epoch){
  if(!visible(tool.id)||epoch!==generation||preview)return;
  const request=new AbortController();requests.set(tool.id,request);
  const abort=()=>request.abort();controller.signal.addEventListener('abort',abort,{once:true});
  try{
   const data=await api('/api/overlay/tool',{id:tool.id,action:'data',args:{}},request.signal);
   if(visible(tool.id)&&epoch===generation&&!request.signal.aborted)render(tool,data);
  }catch(error){report(error);}finally{controller?.signal.removeEventListener('abort',abort);if(requests.get(tool.id)===request)requests.delete(tool.id);}
  if(visible(tool.id)&&epoch===generation&&tool.refresh_hz>0&&!request.signal.aborted){
   // Server lock's adapter polls at <=1 Hz, and only while busy.
   if(tool.id!=='serverlock'||windows.get(tool.id)?.data?.poll)
    timers.set(tool.id,setTimeout(()=>{timers.delete(tool.id);refresh(tool,epoch);},Math.max(100,1000/tool.refresh_hz)));
  }
 }
 function render(tool,data){
  const view=windows.get(tool.id);if(!view||!visible(tool.id))return;view.data=data;
  const call=async(action,args)=>{
   if(preview||!visible(tool.id))throw new Error('Changes unavailable');
   const epoch=generation;
   try{const result=await api('/api/overlay/tool',{id:tool.id,action,args});
    if(!visible(tool.id)||epoch!==generation)throw new DOMException('Tool hidden','AbortError');
    if(tool.id==='serverlock'){cancelTool(tool.id);if(result.poll)timers.set(tool.id,setTimeout(()=>refresh(tool,generation),1000));}
    return result;
   }catch(error){report(error);throw error;}
  };
  window.overlayRenderers[tool.id](view.body,data,call);
  if(preview)for(const control of view.body.querySelectorAll('input,select,button:not([data-range])'))control.disabled=true;
 }
 function setOpacity(id,value){
  const row=entry(id);row.opacity=Math.max(0,Math.min(100,Math.round(Number(value))));
  const view=windows.get(id);if(view){view.element.style.setProperty('--surface-opacity',row.opacity+'%');view.element.dataset.clear=String(row.opacity===0);const input=view.element.querySelector('[data-opacity]');if(input){input.value=row.opacity;input.nextElementSibling.textContent=row.opacity+'%';}}
 }
 function dim(){document.body.classList[settings.overlay_dim_game===false?'add':'remove']('no-dim');}
 function bounds(){return $('workspace').getBoundingClientRect();}
 function place(tool){
  const view=windows.get(tool.id),row=entry(tool.id),area=bounds();
  const width=Math.min(Math.max(240,row.width||tool.default_size[0]),Math.max(240,area.width));
  const height=Math.min(Math.max(180,row.height||tool.default_size[1]),Math.max(180,area.height));
  const x=Math.max(0,Math.min(row.x??(tool.id==='hardware'?560:24+manifest.tools.indexOf(tool)*36),Math.max(0,area.width-width)));
  const y=Math.max(0,Math.min(row.y??(tool.id==='hardware'?12:12+manifest.tools.indexOf(tool)*24),Math.max(0,area.height-height)));
  Object.assign(row,{x,y,width,height});if(row.pinned)Object.assign(row,{pinned_x:x+area.left,pinned_y:y+area.top});Object.assign(view.element.style,{left:x+'px',top:y+'px',width:width+'px',height:height+'px'});
 }
 function persist(){
  if(preview||!active)return Promise.resolve();
  const value=JSON.parse(JSON.stringify(layout)),signal=controller.signal;
  // Serialize writes to prevent an old drag from overwriting a later close/pin.
  saveChain=saveChain.catch(()=>{}).then(()=>signal.aborted?null:api('/api/overlay/settings',{overlay_layout:value},signal)).catch(report);
  return saveChain;
 }
 function dock(){
  $('dock').replaceChildren();
  for(const id of settings.overlay_tools){
   const tool=manifest.tools.find(t=>t.id===id);if(!tool)continue;
   const button=document.createElement('button');button.type='button';button.dataset.launch=id;
   button.innerHTML=icon(tool.icon)+'<span>'+e(tool.title)+'</span>';button.setAttribute('aria-pressed',String(!!entry(id).open));
   button.onclick=()=>toggleTool(tool,!entry(id).open);$('dock').appendChild(button);
  }
  const room=document.createElement('span');room.className='dock-space';room.textContent='+';room.title='Room for future tools';room.setAttribute('aria-hidden','true');$('dock').appendChild(room);
 }
 function toggleTool(tool,open){
  entry(tool.id).open=open;const view=windows.get(tool.id);view.element.hidden=!open;
  cancelTool(tool.id);
  if(!open&&tool.id==='serverlock'&&!preview)api('/api/overlay/panel',{action:'region-close'}).catch(report);
  if(open){view.element.style.zIndex=++z;place(tool);if(preview)render(tool,window.overlayPreview.data[tool.id]);else refresh(tool,generation);}
  dock();persist();
 }
 function createWindow(tool){
  const element=document.createElement('section');element.className='tool-window';element.dataset.tool=tool.id;element.setAttribute('role','region');element.setAttribute('aria-label',tool.title);
  element.innerHTML='<header class="window-head">'+icon(tool.icon)+'<h2>'+e(tool.title)+'</h2>'+(tool.pinnable?'<button data-pin aria-label="Pin '+e(tool.title)+'" title="Keep visible over game">'+icon('pin')+'</button>':'')+'<label class="opacity-control" title="Background opacity"><input data-opacity type="range" min="0" max="100" aria-label="'+e(tool.title)+' background opacity"><output></output></label><button data-close aria-label="Close '+e(tool.title)+'">'+icon('close')+'</button></header><div class="tool-body"></div><button class="resize" aria-label="Resize '+e(tool.title)+'" title="Drag to resize; arrow keys also resize"></button>';
  const view={element,body:element.querySelector('.tool-body'),data:null};windows.set(tool.id,view);$('workspace').appendChild(element);
  const opacity=element.querySelector('[data-opacity]');opacity.oninput=()=>setOpacity(tool.id,opacity.value);opacity.onchange=()=>persist();setOpacity(tool.id,entry(tool.id).opacity);
  element.onpointerdown=()=>element.style.zIndex=++z;
  element.querySelector('[data-close]').onclick=()=>toggleTool(tool,false);
  const pin=element.querySelector('[data-pin]');if(pin){pin.setAttribute('aria-pressed',String(!!entry(tool.id).pinned));pin.onclick=()=>{entry(tool.id).pinned=!entry(tool.id).pinned;pin.setAttribute('aria-pressed',String(entry(tool.id).pinned));place(tool);persist();};}
  const head=element.querySelector('.window-head'),resize=element.querySelector('.resize');
  const drag=(handle,resizing)=>handle.onpointerdown=event=>{
   if(event.button!==0||event.target.closest('button,input,label')!==null&&!resizing)return;
   event.preventDefault();handle.setPointerCapture(event.pointerId);const start={...entry(tool.id)},sx=event.clientX,sy=event.clientY;
   handle.onpointermove=ev=>{const row=entry(tool.id);if(resizing){row.width=start.width+ev.clientX-sx;row.height=start.height+ev.clientY-sy;}else{row.x=start.x+ev.clientX-sx;row.y=start.y+ev.clientY-sy;}place(tool);};
   handle.onpointerup=handle.onpointercancel=()=>{handle.onpointermove=null;handle.onpointerup=null;handle.onpointercancel=null;persist();};
  };
  drag(head,false);drag(resize,true);head.tabIndex=0;head.setAttribute('aria-label','Move '+tool.title+' with arrow keys');
  for(const [handle,resizing] of [[head,false],[resize,true]])handle.onkeydown=ev=>{if(ev.target&&ev.target!==handle&&ev.target.closest('input,button,select'))return;if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(ev.key))return;ev.preventDefault();const row=entry(tool.id),delta=ev.shiftKey?40:10;if(ev.key==='ArrowLeft'||ev.key==='ArrowRight')row[resizing?'width':'x']+=(ev.key==='ArrowLeft'?-delta:delta);else row[resizing?'height':'y']+=(ev.key==='ArrowUp'?-delta:delta);place(tool);persist();};
  element.hidden=!entry(tool.id).open||!settings.overlay_tools.includes(tool.id);place(tool);
 }
 function applySettings(value){
  settings={...settings,...value};dim();
  // Local geometry may have changed since the settings tool was opened.
  settings.overlay_layout=layout;
  for(const tool of manifest.tools){const view=windows.get(tool.id);view.element.hidden=!settings.overlay_tools.includes(tool.id)||!entry(tool.id).open;if(view.element.hidden)cancelTool(tool.id);else if(!requests.has(tool.id)&&!timers.has(tool.id))refresh(tool,generation);}
  for(const tool of manifest.tools)setOpacity(tool.id,entry(tool.id).opacity);
  dock();
 }
 function clock(){if(!active)return;$('clock').textContent=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});if(!preview)clockTimer=setTimeout(clock,1000);}
 async function start(){
  if(active)return;closing=false;active=true;const epoch=++generation;controller=new AbortController();document.body.classList.add('active');
  try{
   manifest=preview?structuredClone(window.overlayPreview.manifest):await api('/api/overlay/tools');
   if(!active||epoch!==generation)return;
   document.documentElement.dataset.theme=params.get('theme')||manifest.theme;
   settings=manifest.settings;settings.overlay_tools||=manifest.tools.map(t=>t.id);layout=structuredClone(settings.overlay_layout||{});
   dim();
   // Migrate the existing telemetry HUD to the native pinned forms.
   if(!Object.keys(layout).length){entry('performance').pinned=true;entry('hardware').pinned=true;}
   windows.clear();$('workspace').replaceChildren();for(const tool of manifest.tools)createWindow(tool);
   dock();clock();$('shortcut').textContent=settings.overlay_panel_hotkey+' to return to game';
   if(preview){document.body.classList.add('preview');$('preview').hidden=false;for(const tool of manifest.tools)if(visible(tool.id))render(tool,window.overlayPreview.data[tool.id]);}
   else for(const tool of manifest.tools)if(visible(tool.id))refresh(tool,epoch);
  }catch(error){report(error);}
 }
 function stop(){
  active=false;generation++;controller?.abort();clearTimeout(clockTimer);clockTimer=null;
  for(const tool of manifest?.tools||[])cancelTool(tool.id);
  for(const view of windows.values())for(const handle of view.element.querySelectorAll('.window-head,.resize')){handle.onpointermove=null;handle.onpointerup=null;handle.onpointercancel=null;}
  document.body.classList.remove('active');
 }
 async function close(){
  if(!active||closing)return;closing=true;
  await persist();if(!active)return;requested=false;
  if(preview){stop();return;}
  stop();
  // Native controller hides after the 120 ms CSS fade. No JS timer remains.
  api('/api/overlay/panel',{action:'close'},null).catch(()=>{});
 }
 window.overlayPanelActive=value=>{requested=!!value;if(value&&!document.hidden)start();else stop();};
 window.overlayShell={get tools(){return manifest?.tools||[];},applySettings,close,showTool:id=>{const tool=manifest.tools.find(t=>t.id===id);if(tool)toggleTool(tool,true);},setOpacity,saveLayout:persist,get layout(){return layout;}};
 $('close').onclick=close;$('backdrop').onclick=close;
 document.addEventListener('keydown',event=>{if(event.key==='Escape')close();});
 document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();else if(requested)start();});
 document.addEventListener('click',event=>{const link=event.target.closest('a');if(!link)return;event.preventDefault();if(preview)return;const action=link.href.includes('keyboard')?'keyboard':'setup';persist().then(()=>{stop();requested=false;api('/api/overlay/panel',{action},null).catch(()=>{});});});
 window.addEventListener('resize',()=>{if(active)for(const tool of manifest?.tools||[])place(tool);});
 window.addEventListener('unhandledrejection',event=>{report(event.reason);event.preventDefault();});
 window.addEventListener('pagehide',stop);
 if(preview)window.overlayPanelActive(true);
})();
