/* Offline shell renderer. All temporary data stays in this worktree.
   node tools/overlay_preview.cjs
   CHROME_PATH may select another Chromium executable. No app server or Steam.
   --sync-themes exports the main app's token rules after theme edits. */
const fs=require('fs'),path=require('path'),cp=require('child_process');
const root=path.resolve(__dirname,'..');
function syncThemes(){
 const app=fs.readFileSync(path.join(root,'cs2cfg/web/index.html'),'utf8');
 const rules=[...app.matchAll(/(:root(?:\[data-theme="[^"]+"\])?)\s*\{([^{}]*)\}/g)].filter(m=>m[2].includes('--')).map(m=>m[0]);
 fs.writeFileSync(path.join(root,'cs2cfg/web/assets/overlay/themes.css'),'/* App theme tokens exported by tools/overlay_preview.cjs --sync-themes. */\n'+rules.join('\n'));
}
function bundle(extra=''){
 let html=fs.readFileSync(path.join(root,'cs2cfg/web/overlay-panel.html'),'utf8');
 html=html.replace(/<link rel="stylesheet" href="([^"]+)">/g,(_,file)=>'<style>'+fs.readFileSync(path.join(root,'cs2cfg/web',file),'utf8')+'</style>');
 html=html.replace(/<script src="([^"]+)"><\/script>/g,(_,file)=>'<script>'+fs.readFileSync(path.join(root,'cs2cfg/web',file),'utf8').replace(/<\/script/gi,'<\\/script')+'</script>');

 return html.replace('</body>','<script>'+extra+'</script></body>');
}
function chrome(){
 const candidates=[process.env.CHROME_PATH,'C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','/usr/bin/chromium','/usr/bin/google-chrome'];
 const found=candidates.find(p=>p&&fs.existsSync(p));if(!found)throw new Error('Chromium not found. Set CHROME_PATH to Chrome or Edge.');return found;
}
function render({name='shell',extra='',screenshot,query='preview=1',width=1440,height=1000,dump=false}){
 const base=path.join(root,'tmp/overlay-shell');fs.mkdirSync(base,{recursive:true});
 const work=fs.mkdtempSync(path.join(base,name+'-')),file=path.join(work,'shell.html');
 fs.writeFileSync(file,bundle(extra).replace('</head>','<style>*,*::before,*::after{animation:none!important;transition:none!important}</style></head>'));
 const args=['--headless','--no-sandbox','--disable-gpu','--disable-background-networking','--disable-crash-reporter','--no-first-run','--no-default-browser-check','--hide-scrollbars','--user-data-dir='+path.join(work,'profile'),'--window-size='+width+','+height,'--force-device-scale-factor=1','--virtual-time-budget=1800'];
 if(screenshot)args.push('--screenshot='+screenshot);
 if(dump)args.push('--dump-dom');
 args.push(require('url').pathToFileURL(file).href+'?'+query);
 try{
  const result=cp.spawnSync(chrome(),args,{encoding:'utf8',timeout:30000,maxBuffer:8*1024*1024,windowsHide:true,env:{...process.env,TEMP:work,TMP:work}});
  if(result.error)throw result.error;if(result.status!==0)throw new Error(result.stderr||'Chromium failed');
  if(screenshot&&!fs.existsSync(screenshot))throw new Error('Chromium did not create '+screenshot);
  return result.stdout;
 }finally{if(!path.resolve(work).startsWith(path.resolve(base)+path.sep))throw new Error('Preview cleanup escaped its workspace');fs.rmSync(work,{recursive:true,force:true,maxRetries:5,retryDelay:100});}
}
// Deterministic, original sunny training-yard scenery; no game artwork.
function gameScene(){
 const canvas=document.createElement('canvas');canvas.width=1440;canvas.height=1000;
 Object.assign(canvas.style,{position:'fixed',inset:'0',width:'100%',height:'100%',zIndex:'-1'});document.body.prepend(canvas);
 const c=canvas.getContext('2d'),sky=c.createLinearGradient(0,0,0,1000);sky.addColorStop(0,'#75c7ed');sky.addColorStop(.47,'#e3f2eb');sky.addColorStop(.48,'#f4dfa7');sky.addColorStop(1,'#c9ad77');c.fillStyle=sky;c.fillRect(0,0,1440,1000);
 c.fillStyle='#fff3cc';c.beginPath();c.arc(1130,150,70,0,Math.PI*2);c.fill();
 function polygon(points,color){c.fillStyle=color;c.beginPath();points.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.closePath();c.fill();}
 polygon([[0,240],[560,365],[560,710],[0,920]],'#d4bd8d');polygon([[1440,210],[880,350],[880,710],[1440,1000]],'#e6d3a4');
 polygon([[0,240],[560,365],[560,395],[0,280]],'#f6e6bd');polygon([[1440,210],[880,350],[880,380],[1440,250]],'#fff0cb');
 c.strokeStyle='#ac956b';c.lineWidth=2;
 for(let row=0;row<12;row++){const y=300+row*52;c.beginPath();c.moveTo(0,y);c.lineTo(560,395+row*27);c.stroke();for(let col=0;col<7;col++){let x=col*95+(row%2)*45;c.beginPath();c.moveTo(x,y);c.lineTo(x,y+50);c.stroke();}}
 c.fillStyle='#7b796c';c.fillRect(610,370,220,200);c.fillStyle='#384c50';c.fillRect(655,410,130,160);c.fillStyle='#efe1bb';c.fillRect(600,360,240,25);
 for(let i=0;i<6;i++){const x=950+i*78,y=430+i*40;c.fillStyle=i%2?'#a89e7b':'#c2ad7a';c.fillRect(x,y,70,130);c.strokeStyle='#706c56';c.strokeRect(x+6,y+6,58,118);c.beginPath();c.moveTo(x+6,y+6);c.lineTo(x+64,y+124);c.stroke();}
 polygon([[910,650],[1440,890],[1440,1000],[680,1000]],'rgba(101,92,74,.22)');
 c.strokeStyle='rgba(100,87,61,.24)';for(let i=0;i<90;i++){const x=(i*193)%1440,y=640+(i*47)%360;c.beginPath();c.moveTo(x,y);c.lineTo(x+20,y+3);c.stroke();}
 c.strokeStyle='rgba(255,255,255,.8)';c.lineWidth=2;c.beginPath();c.moveTo(714,500);c.lineTo(726,500);c.moveTo(720,494);c.lineTo(720,506);c.stroke();
 document.body.style.background='transparent';
}
function pinnedPreview(opacity){
 document.body.innerHTML='';gameScene();
 const fixture=window.overlayPreview.data;
 const rows=[['Performance','FPS 287.0    1% low 182.0','Frame 3.5 ms'],['Hardware','CPU 32.0%    GPU 56.0%','CPU \u2014    GPU 66.0 C','VRAM 4096.0 / 12288.0 MB','RAM 14745.0 / 32768.0 MB'],['Stutters and freezes','14:32:12   Stutter   24.1 ms','14:31:17   Freeze   212.4 ms','14:30:34   Stutter   18.9 ms'],['Profiles','Setup: Balanced','Layout: Competitive'],['Server lock','Coming soon']];
 rows.forEach((lines,i)=>{const widget=document.createElement('div');Object.assign(widget.style,{position:'absolute',left:'28px',top:(28+i*140)+'px',width:'360px',height:'120px',padding:'7px 12px',background:'rgba(19,22,27,'+opacity/100+')',color:'#eaeef4',font:'16px Segoe UI',whiteSpace:'pre',lineHeight:'21px',textShadow:'-1px -1px 0 #0c0c0c,0 -1px 0 #0c0c0c,1px -1px 0 #0c0c0c,-1px 0 0 #0c0c0c,1px 0 0 #0c0c0c,-1px 1px 0 #0c0c0c,0 1px 0 #0c0c0c,1px 1px 0 #0c0c0c'});
 for(const line of lines){const div=document.createElement('div');div.textContent=line;widget.appendChild(div);}
 if(i===0){const values=fixture.performance.history.slice(-60).map(s=>s.frame_time_ms),peak=Math.max(10,...values),points=values.map((v,j)=>(12+Math.round(j*300/(values.length-1)))+','+(111-Math.round(v*34/peak))).join(' ');widget.insertAdjacentHTML('beforeend','<svg style="position:absolute;inset:0;width:360px;height:120px"><polyline points="'+points+'" stroke="#0c0c0c" stroke-width="4" fill="none"/><polyline points="'+points+'" stroke="#c3d0de" stroke-width="2" fill="none"/></svg>');}
 document.body.appendChild(widget);});
 const label=document.createElement('div');label.textContent='PINNED TOOLS \u00b7 BACKGROUND '+opacity+'%';Object.assign(label.style,{position:'fixed',right:'32px',bottom:'28px',font:'12px Segoe UI',letterSpacing:'.12em',color:'#fff',textShadow:'1px 1px 2px #111'});document.body.appendChild(label);
}
const scenery='('+gameScene.toString()+')();';
const pinned=opacity=>'window.gameScene='+gameScene.toString()+';('+pinnedPreview.toString()+')('+opacity+');';
if(require.main===module){
 if(process.argv.includes('--sync-themes'))syncThemes();
 else if(process.argv.includes('--check')){
  const output=render({dump:true,extra:`try{
    for(const id of ['performance','hardware','events','profiles','serverlock','settings']){
      window.overlayShell.showTool(id);
      const body=document.querySelector('.tool-window[data-tool="'+id+'"] .tool-body');
      if(!body||!body.children.length)throw new Error('Empty renderer: '+id);
    }
    for(const theme of ['violet','ember','carbon','acid','crimson','frost','neon','daylight','pro','paper']){
      document.documentElement.dataset.theme=theme;
      const style=getComputedStyle(document.documentElement);
      for(const key of ['--panel','--ink','--accent','--bg','--line'])if(!style.getPropertyValue(key).trim())throw new Error('Missing '+key+' in '+theme);
    }
    document.body.dataset.shellCheck='OK';
  }catch(error){document.body.dataset.shellCheck='ERROR: '+error.message;}`});
  if(!output.includes('data-shell-check="OK"'))throw new Error(output.match(/data-shell-check="[^"]*/)?.[0]||'Smoke check did not finish');
  console.log('Chromium smoke: 6 renderers / 10 themes OK');
 }
 else{
 const out=path.join(root,'docs/overlay/preview/shell');fs.mkdirSync(out,{recursive:true});
 const capture=(name,extra='',opts={})=>{render({name,screenshot:path.join(out,name+'.png'),extra,...opts});console.log(name+'.png');};
 capture('shell-tools');
 capture('dock',`document.querySelectorAll('.tool-window').forEach(w=>w.hidden=true);document.querySelector('.shell-header').hidden=true;document.getElementById('preview').hidden=true;`,{width:1100,height:260});
 capture('settings',`for(const w of document.querySelectorAll('.tool-window'))w.hidden=true;window.overlayShell.layout.settings={x:60,y:0,width:900,height:1100,open:true};window.overlayShell.showTool('settings');`,{width:1100,height:1450});
 capture('shell-nodim',scenery+"window.overlayShell.applySettings({overlay_dim_game:false});");
 capture('pinned-clear',pinned(0),{height:900});
 capture('pinned-60',pinned(60),{height:900});
 }
}
module.exports={render,bundle,syncThemes};

