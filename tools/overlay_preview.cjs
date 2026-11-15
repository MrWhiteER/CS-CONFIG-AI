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
 }finally{fs.rmSync(work,{recursive:true,force:true,maxRetries:5,retryDelay:100});}
}
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
 capture('settings',`for(const w of document.querySelectorAll('.tool-window'))w.hidden=true;window.overlayShell.layout.settings={x:150,y:0,width:740,height:740,open:true};window.overlayShell.showTool('settings');`,{width:1100,height:1200});
 // Facsimile of the native GDI HUD's exact display_lines content and dimensions.
 capture('pinned-widget',`document.body.innerHTML='<div style="position:absolute;left:28px;top:28px;width:640px;height:120px;background:rgba(18,18,18,.92);color:#eee;font:16px Segoe UI;white-space:pre;padding:9px 12px;line-height:26px"><div>CS CONFIG AI    FPS 287.0    1% low 182.0</div><div>Frame 3.5 ms    CPU 32.0%    GPU 56.0%    Temp 66.0 C</div><div>PresentMon: capturing</div><div>Ctrl+Alt+O: show/hide</div></div>';document.body.style.background='var(--bg)';`,{width:800,height:220});
 }
}
module.exports={render,bundle,syncThemes};

