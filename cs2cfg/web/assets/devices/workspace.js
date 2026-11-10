/* Pointer-driven command assignment, sharing the existing bind transaction. */
let kbOpenInspector = false;
let kbAssignedCode = null;
let kbWorkspaceObserver = null;

function kbFitLayout(scene) {
  const width = scene.clientWidth || 900;
  kbLayout.board = { x:10, y:65, s:Math.min(1.15, Math.max(.25,(width-32)/850)) };
  kbLayout.mouse = { x:Math.max(8,width-365), y:Math.max(300,65+285*kbLayout.board.s), s:Math.min(1,width/365) };
}

function kbDecorateWorkspace() {
  const out = document.getElementById('kb-out');
  if (!out) return;
  const inspector = out.querySelector('.kb-inspector');
  if (kbOpenInspector && inspector) {
    inspector.classList.add('is-opening');
    kbOpenInspector = false;
  }
  const counts = {script:0,custom:0,bound:0,free:0};
  out.querySelectorAll('[data-kbcode]').forEach(el => {
    for (const state of Object.keys(counts)) if (el.classList.contains(state)) counts[state]++;
    if (el.dataset.kbcode === kbAssignedCode) el.classList.add('kb-assigned');
  });
  kbAssignedCode = null;
  Object.entries(counts).forEach(([state,count]) => {
    const dot = out.querySelector('.kb-legend .dot.'+state);
    if (dot) dot.parentElement.insertAdjacentHTML('beforeend','<b class="kb-state-count">'+count+'</b>');
  });
  out.querySelectorAll('.kbsw-tab .kb-ico-art').forEach(el => el.classList.add('kbsw-device-icon'));
  if (!kbWorkspaceObserver && typeof ResizeObserver !== 'undefined') {
    let previous = out.clientWidth;
    kbWorkspaceObserver = new ResizeObserver(() => {
      if (!out.clientWidth || Math.abs(out.clientWidth-previous)<2) return;
      previous = out.clientWidth;
      const scene = document.getElementById('kb-scene');
      if (!scene) return;
      const board = scene.querySelector('[data-piece="board"]');
      if (board) kbLayout.board.s = Math.min(kbLayout.board.s,(scene.clientWidth-32)/board.offsetWidth);
      ['board','mouse'].forEach(kbPlace);
    });
    kbWorkspaceObserver.observe(out);
  }
}

(function kbCommandInteraction() {
  let drag = null, preview = null, timer = 0, suppressUntil = 0;
  function hidePreview() { clearTimeout(timer); if (preview) preview.remove(); preview=null; }
  function clearDrag(cancel = true) {
    if (!drag) return;
    const old = drag; drag=null;
    if (cancel !== false && old.ghost) suppressUntil=performance.now()+400;
    if (old.target) old.target.classList.remove('kb-drop-target');
    if (old.ghost) old.ghost.remove();
    try { old.source.releasePointerCapture(old.id); } catch (_) {}
  }
  document.addEventListener('pointerdown', e => {
    const command = e.target.closest('[data-bindcmd]');
    if (!command || command.disabled || kbBusy || e.button!==0) return;
    hidePreview();
    drag = {id:e.pointerId,source:command,command:command.dataset.bindcmd,x:e.clientX,y:e.clientY};
  });
  document.addEventListener('pointermove', e => {
    if (!drag || e.pointerId!==drag.id) return;
    if (!drag.ghost && Math.hypot(e.clientX-drag.x,e.clientY-drag.y)<7) return;
    if (!drag.ghost) {
      drag.ghost=document.createElement('div'); drag.ghost.className='kb-drag-ghost';
      drag.ghost.textContent=drag.command; document.body.append(drag.ghost);
      try { drag.source.setPointerCapture(drag.id); } catch (_) {}
    }
    drag.ghost.style.left=Math.min(innerWidth-200,e.clientX+16)+'px';
    drag.ghost.style.top=e.clientY+16+'px';
    const target = document.elementFromPoint(e.clientX,e.clientY)?.closest('#kb-out [data-kbcode]');
    if (drag.target!==target) {
      if (drag.target) drag.target.classList.remove('kb-drop-target');
      drag.target=target;
      if (target) target.classList.add('kb-drop-target');
    }
    e.preventDefault();
  },{passive:false});
  document.addEventListener('pointerup', e => {
    if (!drag || e.pointerId!==drag.id) return;
    const {target,command,ghost}=drag;
    clearDrag(false);
    if (!ghost) return; // A click still assigns to the selected control.
    suppressUntil=performance.now()+400;
    if (!target || kbBusy) return;
    pickedKey={code:target.dataset.kbcode,label:target.dataset.kblabel};
    kbOptions=null; kbOpenInspector=true;
    kbAssign({code:pickedKey.code,command}, a=>pickedKey.label+' now runs '+a.command);
  });
  document.addEventListener('click',e=>{
    if(performance.now()<suppressUntil){e.preventDefault();e.stopImmediatePropagation();}
  },true);
  document.addEventListener('pointercancel',clearDrag);
  document.addEventListener('lostpointercapture',()=>{if(drag?.ghost)clearDrag();});
  document.addEventListener('keydown',e=>{
    if(e.key==='Escape'){clearDrag();hidePreview();}
    const zone=e.target.closest('.ms-zone');
    if(zone && (e.key==='Enter'||e.key===' ')){
      e.preventDefault();zone.dispatchEvent(new MouseEvent('click',{bubbles:true}));
    }
  });
  function showPreview(el) {
    hidePreview();
    if (drag || kbBusy) return;
    timer=setTimeout(()=>{
      if (!el.isConnected) return;
      preview=document.createElement('div'); preview.className='kb-hover-preview';
      const label=document.createElement('b');label.textContent=el.dataset.kblabel;
      preview.append(label,document.createTextNode(el.dataset.kbpreview||'Free'));
      document.body.append(preview);
      const box=el.getBoundingClientRect();
      preview.style.left=Math.max(8,Math.min(innerWidth-preview.offsetWidth-8,box.left))+'px';
      preview.style.top=Math.max(8,box.top-preview.offsetHeight-10)+'px';
    },200);
  }
  document.addEventListener('pointerover',e=>{
    const el=e.target.closest('[data-kbpreview]');
    if(el&&!el.contains(e.relatedTarget))showPreview(el);
  });
  document.addEventListener('pointerout',e=>{
    const el=e.target.closest('[data-kbpreview]');
    if(el&&!el.contains(e.relatedTarget))hidePreview();
  });
  document.addEventListener('focusin',e=>{const el=e.target.closest('[data-kbpreview]');if(el)showPreview(el);});
  document.addEventListener('focusout',hidePreview);
  document.addEventListener('scroll',hidePreview,true);
  document.addEventListener('visibilitychange',()=>{
    document.documentElement.classList.toggle('kb-motion-paused',document.hidden);
    if(document.hidden){clearDrag();hidePreview();}
  });
  window.addEventListener('blur',()=>{clearDrag();hidePreview();});
})();
