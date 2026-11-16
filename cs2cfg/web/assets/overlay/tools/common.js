/* Shared rendering only. Tools own no timers and perform no fetches. */
(() => {
  const paths={activity:'M2 12h4l3-8 6 16 3-8h4',cpu:'M7 7h10v10H7z M9 1v4m6-4v4M9 19v4m6-4v4M1 9h4m-4 6h4m14-6h4m-4 6h4',pulse:'M2 12h5l3-6 4 12 3-6h5',layers:'m12 3 10 6-10 6L2 9z M2 14l10 6 10-6',globe:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M3 12h18M12 3c-5 5-5 13 0 18 5-5 5-13 0-18',settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z',pin:'m8 3 8 0-1 6 4 4H5l4-4z M12 13v9',close:'m6 6 12 12M6 18 18 6'};
  window.overlayUI={
    icon:name=>'<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="'+(paths[name]||paths.activity)+'"/></svg>',
    number:(n,unit='')=>Number.isFinite(n)?n.toFixed(1)+unit:'—',
    escape:s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
    options:(entries,value,label,selected)=>entries.map(e=>'<option value="'+window.overlayUI.escape(value(e))+'" '+(selected?.(e)?'selected':'')+'>'+window.overlayUI.escape(label(e))+'</option>').join('')||'<option value="">None saved</option>'
  };
})();
