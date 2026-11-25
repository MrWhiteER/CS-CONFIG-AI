(() => {
 const {options}=window.overlayUI;
 window.overlayRenderers.profiles=(root,d,call)=>{
 root.innerHTML='<label>Saved setup</label><div class="picker"><select data-setups aria-label="Saved setup">'+options(d.setups?.setups||[],s=>s.name,s=>s.name,s=>s.name===d.setups.live)+'</select><button data-use-setup class="primary">Use</button></div><p>Sets your choices for the app’s next Apply.</p><label>Keyboard / mouse layout</label><div class="picker"><select data-layouts aria-label="Keyboard and mouse layout">'+options(d.layouts?.profiles||[],s=>s.file,s=>s.label,s=>s.active)+'</select><button data-use-layout class="primary">Use</button></div><p class="tool-status" data-note>Switch a layout, then load it in game.</p><a href="/?tab=keyboard">Open Controls tab ↗</a>';
 root.querySelector('[data-use-setup]').disabled=!(d.setups?.setups||[]).length;
 root.querySelector('[data-use-layout]').disabled=!(d.layouts?.profiles||[]).length;
 root.querySelector('[data-use-setup]').onclick=async()=>{await call('setup',{name:root.querySelector('[data-setups]').value});root.querySelector('[data-note]').textContent='Setup selected for the app’s next Apply.';};
 root.querySelector('[data-use-layout]').onclick=async()=>{const d=await call('layout',{file:root.querySelector('[data-layouts]').value});root.querySelector('[data-note]').textContent=d.apply_keys?.length?'Press '+d.apply_keys.join(' / ')+' in game to load it':'No Apply Saved Settings key is bound. Set one in the Controls tab.';};
 };
})();
