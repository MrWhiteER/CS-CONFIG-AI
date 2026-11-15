(() => {
 const {escape:e}=window.overlayUI;
 const fields={fps:'FPS',one_percent_low:'1% low',frame_time_ms:'Frame time',cpu_percent:'CPU',gpu_percent:'GPU',gpu_temp_c:'GPU temperature'};
 window.overlayRenderers.settings=(root,d,call)=>{
 const s=d.settings||{},tools=window.overlayShell.tools;
 const check=(key,label)=>'<label class="check"><input type="checkbox" data-setting="'+key+'" '+(s[key]?'checked':'')+'>'+label+'</label>';
 root.innerHTML='<div class="settings-section"><h3>Shortcuts</h3><label>Open overlay<input type="text" data-setting="overlay_panel_hotkey" value="'+e(s.overlay_panel_hotkey)+'"></label><label>Toggle pinned telemetry<input type="text" data-setting="overlay_hotkey" value="'+e(s.overlay_hotkey)+'"></label></div><div class="settings-section"><h3>While you play</h3>'+check('overlay_auto_hide','Auto hide during live rounds')+check('overlay_always_visible','Always visible')+check('overlay_hide_from_capture','Hide from capture')+'<label>Widget corner<select data-setting="overlay_corner">'+['top_left','top_right','bottom_left','bottom_right'].map(c=>'<option '+(s.overlay_corner===c?'selected':'')+' value="'+c+'">'+c.replace('_',' ')+'</option>').join('')+'</select></label></div><div class="settings-section"><h3>Pinned telemetry fields</h3><div class="field-options">'+Object.entries(fields).map(([key,label])=>'<label class="check"><input type="checkbox" data-field="'+key+'" '+((s.overlay_fields||[]).includes(key)?'checked':'')+'>'+label+'</label>').join('')+'</div></div><div class="settings-section"><h3>Your dock</h3><div data-tool-order></div><p>Use the arrows to reorder tools. Settings stays available.</p></div><button class="primary" data-save>Save settings</button><p data-status class="tool-status"></p>';
 let order=[...(s.overlay_tools||tools.map(t=>t.id)),...tools.filter(t=>!(s.overlay_tools||[]).includes(t.id)).map(t=>t.id)];order=[...new Set(order)];
 const enabled=new Set(s.overlay_tools||tools.map(t=>t.id));
 const renderOrder=()=>{
 const list=root.querySelector('[data-tool-order]');list.innerHTML=order.map((id,i)=>'<div class="dock-setting"><label class="check"><input type="checkbox" data-tool="'+id+'" '+(enabled.has(id)?'checked':'')+' '+(id==='settings'?'disabled':'')+'>'+e(tools.find(t=>t.id===id).title)+'</label><button data-up="'+id+'" aria-label="Move '+id+' up" '+(!i?'disabled':'')+'>↑</button><button data-down="'+id+'" aria-label="Move '+id+' down" '+(i===order.length-1?'disabled':'')+'>↓</button></div>').join('');
 for(const box of list.querySelectorAll('[data-tool]'))box.onchange=()=>box.checked?enabled.add(box.dataset.tool):enabled.delete(box.dataset.tool);
 for(const button of list.querySelectorAll('[data-up],[data-down]'))button.onclick=()=>{const id=button.dataset.up||button.dataset.down,i=order.indexOf(id),j=i+(button.dataset.up?-1:1);[order[i],order[j]]=[order[j],order[i]];renderOrder();};
 };renderOrder();
 root.querySelector('[data-save]').onclick=async()=>{
 const args={overlay_tools:order.filter(id=>enabled.has(id)),overlay_fields:[...root.querySelectorAll('[data-field]')].filter(b=>b.checked).map(b=>b.dataset.field)};
 for(const input of root.querySelectorAll('[data-setting]'))args[input.dataset.setting]=input.type==='checkbox'?input.checked:input.value;
 const result=await call('save',args);window.overlayShell.applySettings(result.settings);root.querySelector('[data-status]').textContent='Settings saved';
 };
 };
})();
