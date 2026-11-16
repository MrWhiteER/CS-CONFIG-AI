(() => {
 const {number:n}=window.overlayUI;
 window.overlayRenderers.hardware=(root,d)=>{
 const rows=[['CPU load',n(d.cpu_percent,'%')],['GPU load',n(d.gpu_percent,'%')],['GPU temperature',n(d.gpu_temp_c,' °C')],['Video memory',Number.isFinite(d.vram_used_mb)?n(d.vram_used_mb/1024,' / ')+n(d.vram_total_mb/1024,' GB'):'—'],['Memory',Number.isFinite(d.ram_used_mb)?n(d.ram_used_mb/1024,' / ')+n(d.ram_total_mb/1024,' GB'):'—']];
 root.innerHTML=rows.map(([label,value])=>'<div class="resource-row"><span>'+label+'</span><strong>'+value+'</strong></div>').join('')+'<p>Read-only system telemetry. Unavailable sensors appear as —.</p>';
 };
})();
