(() => {
 const {number:n,escape:e}=window.overlayUI;
 window.overlayRenderers.events=(root,d)=>{
 root.innerHTML='<h3>Session events</h3><table><thead><tr><th>Time</th><th>Duration</th><th>Type</th></tr></thead><tbody>'+(d.events||[]).slice().sort((a,b)=>b.at-a.at).map(s=>'<tr><td>'+e(new Date(s.at*1000).toLocaleTimeString())+'</td><td>'+n(s.duration_ms,' ms')+'</td><td>'+(s.type==='not_responding'?'Not responding':'Frame spike')+'</td></tr>').join('')+'</tbody></table>'+(!(d.events||[]).length?'<p>No events this session. Looking good.</p>':'');
 };
})();
