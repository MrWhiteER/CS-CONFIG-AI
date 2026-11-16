(() => {
 const {options,number:n,escape:e,icon}=window.overlayUI;
 window.overlayRenderers.serverlock=(root,d,call)=>{
 if(!d.available){root.innerHTML='<div class="empty">'+icon('globe')+'<h3>Coming soon</h3><p>Choose where you play.<br>Server region lock will appear here when available.</p></div>';return;}
 const selected=root.querySelector('select')?.value||d.status?.firewall?.code;
 // Preserve the picker during completion polls.
 if(!root.querySelector('select'))root.innerHTML='<p data-region-text></p><label>Server region</label><select aria-label="Server region"></select><p><button data-lock class="primary">Lock region</button> <button data-unlock>Unlock</button></p><a href="/?tab=settings">Open app setup ↗</a>';
 root.querySelector('[data-region-text]').textContent=d.text;
 const select=root.querySelector('select');select.innerHTML=options(d.regions||[],r=>r.code,r=>r.city+', '+r.country+' · '+n(r.ping_ms,' ms')+' · loss '+n(r.loss)+' · '+(r.status||''),r=>r.code===selected);
 const busy=!!d.status?.busy;select.disabled=busy;
 root.querySelector('[data-lock]').disabled=busy||!(d.regions||[]).length;root.querySelector('[data-unlock]').disabled=busy;
 root.querySelector('[data-lock]').onclick=async()=>window.overlayRenderers.serverlock(root,await call('lock',{code:select.value}),call);
 root.querySelector('[data-unlock]').onclick=async()=>window.overlayRenderers.serverlock(root,await call('unlock',{}),call);
 };
})();
