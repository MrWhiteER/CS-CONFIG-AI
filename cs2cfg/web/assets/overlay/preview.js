/* Inert fixtures shared by the shell and screenshot runner. */
(() => {
 const now=Date.now()/1000;
 const ids=['performance','hardware','events','profiles','serverlock','settings'];
 const titles=['Performance','Hardware','Stutters and freezes','Profiles','Server lock','Settings'];
 const icons=['activity','cpu','pulse','layers','globe','settings'];
 const sizes=[[510,390],[330,420],[430,265],[350,330],[350,320],[700,650]];
 const settings={overlay_enabled:false,overlay_hotkey:'Ctrl+Alt+O',overlay_panel_hotkey:'Ctrl+Alt+P',overlay_auto_hide:true,overlay_always_visible:false,overlay_hide_from_capture:true,overlay_fields:['fps','one_percent_low','frame_time_ms','cpu_percent','gpu_percent','gpu_temp_c'],overlay_corner:'top_left',overlay_tools:ids,overlay_layout:{performance:{x:35,y:14,width:500,height:385,open:true,pinned:true},hardware:{x:560,y:14,width:300,height:430,open:true,pinned:false},profiles:{open:false},events:{x:885,y:14,width:430,height:320,open:true,pinned:false}}};
 window.overlayPreview={manifest:{tools:ids.map((id,i)=>({id,title:titles[i],icon:icons[i],refresh_hz:['profiles','settings'].includes(id)?0:1,default_size:sizes[i],pinnable:i<2})),settings,theme:'carbon'},data:{
 performance:{now,game_running:true,frame_capture_ready:true,current:{fps:287,frame_time_ms:3.5},summary:{avg_fps:281,one_percent_low:182,worst_frame_ms:24.1},history:Array.from({length:600},(_,i)=>({at:now-599+i,frame_time_ms:i%97===0?20.5:3.55+Math.sin(i*2.7)*.7+Math.cos(i*.9)*.4}))},
 hardware:{cpu_percent:32,gpu_percent:56,gpu_temp_c:66,vram_used_mb:4096,vram_total_mb:12288,ram_used_mb:14745,ram_total_mb:32768},
 events:{events:[{at:now-18,duration_ms:24.1,type:'frame_spike'},{at:now-73,duration_ms:212.4,type:'not_responding'},{at:now-116,duration_ms:18.9,type:'frame_spike'}]},
 profiles:{setups:{setups:[{name:'Balanced'}],live:'Balanced'},layouts:{profiles:[{file:'competitive',label:'Competitive',active:true}]}},
 serverlock:{available:false,text:'Coming soon'},settings:{settings}
 }};
})();
