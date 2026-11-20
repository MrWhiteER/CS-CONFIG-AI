/* Offline preview and browser checks. All output stays inside this worktree. */
const fs=require('fs'),path=require('path');
const {render}=require('./overlay_preview.cjs');
const root=path.resolve(__dirname,'..'),doc=JSON.parse(fs.readFileSync(path.join(root,'cs2cfg/lineups/data/mirage.json'),'utf8'));

// Original schematic fixtures: no Valve artwork or purported real screenshots.
const svgData=svg=>'data:image/svg+xml;base64,'+Buffer.from(svg).toString('base64');
const radarFixture=svgData('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024"><rect width="1024" height="1024" fill="#1e2630"/><g fill="#374654" stroke="#6c8190" stroke-width="9"><path d="M70 80h350v220H70zM520 80h420v260H520zM80 430h290v510H80zM500 480h440v460H500z"/></g><path d="M450 0v1024M0 380h1024" stroke="#a3b19e" stroke-width="25"/><text x="35" y="990" fill="white" font-size="38">Preview diagram</text></svg>');
const pictureFixture=kind=>svgData('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#253340"/><path d="M0 290L320 170L640 290M320 170V40" fill="none" stroke="#68808f" stroke-width="3"/><circle cx="320" cy="180" r="18" fill="none" stroke="#ffff00" stroke-width="4"/><text x="20" y="40" fill="white" font-size="24">Preview '+kind+' picture</text></svg>');
const pictureFixtures=Object.fromEntries(doc.lineups.map(r=>[r.id,{stand:pictureFixture('stand'),aim:pictureFixture('aim')}]));
const setup=`window.overlayPanelActive(false);
 const fixture=window.overlayPreview;
 fixture.manifest.tools.push({id:'lineups',title:'Lineups',icon:'globe',refresh_hz:0,default_size:[980,610],pinnable:true});
 fixture.manifest.settings.overlay_tools.push('lineups');
 fixture.manifest.settings.overlay_layout=Object.fromEntries(fixture.manifest.tools.map(t=>[t.id,{open:false}]));
 fixture.manifest.settings.overlay_layout.lineups={x:90,y:8,width:1000,height:620,open:true,opacity:95};
 fixture.data.lineups={maps:[{id:'mirage',name:'Mirage'},{id:'inferno',name:'Inferno'}],document:${JSON.stringify(doc)},art:{overview:${JSON.stringify(doc.overview)},image:${JSON.stringify(radarFixture)}},pictures:${JSON.stringify(pictureFixtures)},round:{show:true,name:'Mirage',side:'T',buying:true}};
 window.overlayPanelActive(true);`;
const checks=`(async()=>{try{
 const body=document.querySelector('[data-tool="lineups"] .tool-body'),ui=window.lineupsUI;
 if(body.querySelectorAll('[data-lineup]').length!==fixture.data.lineups.document.lineups.length)throw Error('Seed list missing');
 const assertFits=()=>{
  const panel=body.closest('.tool-window').getBoundingClientRect();
  if(Math.abs(panel.width-1000)>1||Math.abs(panel.height-620)>1)throw Error('Preview must check the actual 1000 by 620 default panel');
  const detail=body.querySelector('.lineup-detail'),end=detail.getBoundingClientRect().bottom,edge=body.getBoundingClientRect().bottom;
  if(detail.scrollHeight>detail.clientHeight+1||end>edge-10||body.scrollHeight>body.clientHeight+1)throw Error('Default panel requires scrolling: '+[detail.scrollHeight,detail.clientHeight,end,edge,body.scrollHeight,body.clientHeight].join(','));
  for(const node of detail.querySelectorAll('li,.lineup-radar,.lineup-thumbnail'))if(node.getBoundingClientRect().bottom>edge-10)throw Error('Detail content clipped');
 };
 for(const row of body.querySelectorAll('[data-lineup]')){row.disabled=false;row.click();assertFits();}
 body.querySelector('[data-lineup]').disabled=false;body.querySelector('[data-lineup]').click();
 if(body.querySelectorAll('.lineup-thumbnail').length!==2)throw Error('Picture thumbnails missing');
 body.querySelector('.lineup-thumbnail').disabled=false;body.querySelector('.lineup-thumbnail').click();
 const dialog=body.querySelector('dialog');if(!dialog?.open)throw Error('Large picture did not open');dialog.querySelector('button').click();
 window.overlayRenderers.lineups(body,{...fixture.data.lineups,picture_status:'Picture 3 of 36 - press F8'},()=>{});
 if(body.querySelector('.lineup-picture-status').textContent!=='Picture 3 of 36 - press F8')throw Error('Picture status missing');assertFits();
 window.overlayRenderers.lineups(body,{...fixture.data.lineups,picture_status:'Done - 36 pictures saved'},()=>{});
 if(!body.querySelector('.lineup-picture-status').textContent.includes('Done - 36'))throw Error('Completion status missing');assertFits();
 let stopped=false;
 window.overlayRenderers.lineups(body,{...fixture.data.lineups,map_request:true,picture_active:true,picture_status:'Picture 3 of 36 - press F8'},async(action)=>{
  if(action!=='stop_pictures')throw Error('Wrong stop action');stopped=true;
  return {...fixture.data.lineups,picture_active:false,picture_status:'Pictures stopped.'};
 });
 const stop=body.querySelector('[data-stop-pictures]');if(stop.hidden||stop.textContent!=='Stop pictures')throw Error('Stop pictures missing');assertFits();
 stop.disabled=false;await stop.onclick({target:stop});
 if(!stopped||!stop.hidden||body.querySelector('.lineup-picture-status').textContent!=='Pictures stopped.')throw Error('Stop pictures failed');assertFits();
 const query=body.querySelector('[data-query]');query.disabled=false;query.value='window';query.dispatchEvent(new Event('input'));
 if(body.querySelectorAll('[data-lineup]').length!==3)throw Error('Type ahead failed');
 query.value='';query.dispatchEvent(new Event('input'));
 const side=body.querySelector('[data-side]');side.disabled=false;side.value='CT';side.dispatchEvent(new Event('change'));
 if(body.querySelectorAll('[data-lineup]').length!==fixture.data.lineups.document.lineups.filter(r=>r.side==='CT'||r.side==='both').length||!body.querySelector('.lineup-detail').textContent.includes('Deep A ramp'))throw Error('Side filter failed');
 const sample={...fixture.data.lineups.document.lineups[0],area:'B',name:'Default corner',type:'fire'};
 for(const q of ['b site molly','B molotov','incendiary'])if(ui.search([sample],q,'T','fire').length!==1)throw Error('Synonym failed');
 query.value='nothing matches';query.dispatchEvent(new Event('input'));
 if(!body.querySelector('.lineups-results').textContent.includes('No lineups match'))throw Error('Empty search missing');
 if(body.textContent.includes('de_mirage')||body.textContent.includes('setpos'))throw Error('Internal text exposed');
 if(!body.querySelector('details').textContent.includes('Rene Rebsdorf'))throw Error('Credit missing');
 const art={image:'data:image/png;base64,',overview:fixture.data.lineups.document.overview};
 if(!ui.radar(art,[sample]).includes('stroke-dasharray'))throw Error('Radar annotation missing');
 if(ui.radar(art,[{...sample,stand:{radar_x:300,radar_y:500},land:null}]).includes('stroke-dasharray'))throw Error('Optional landing must not draw an invented throw arc');
 if(body.querySelector('.lineup-round').hidden)throw Error('Round card missing');
 window.overlayRenderers.lineups(body,{...fixture.data.lineups,round:{show:false}},()=>{});
 if(!body.querySelector('.lineup-round').hidden)throw Error('Live card did not fold');
 if(query!==body.querySelector('[data-query]')||query.value!=='nothing matches')throw Error('Refresh lost search state');
 let requested='';
 window.overlayRenderers.lineups(body,{...fixture.data.lineups,map_request:true},async(action,args)=>{
  requested=args.map;return {maps:fixture.data.lineups.maps,document:null,art:null,map_request:true};
 });
 const map=body.querySelector('[data-map]');map.value='inferno';await map.onchange({target:map});
 if(requested!=='inferno'||body.querySelectorAll('[data-lineup]').length)throw Error('Map switch failed');
 const preview=document.createElement('div');preview.style.width='560px';document.body.append(preview);
 window.overlayRenderers.lineups(preview,{...fixture.data.lineups,art,map_request:true},()=>{});
 const svg=preview.querySelector('.lineup-radar'),bounds=svg.getBoundingClientRect();
 if(Math.abs(bounds.width-bounds.height)>1||bounds.width>241)throw Error('Detail radar must fit a small square');
 if(svg.getAttribute('viewBox')==='0 0 1024 1024')throw Error('Detail radar did not zoom to throw');
 if(preview.textContent.includes('Mid site'))throw Error('Mid site label returned');
 if(preview.querySelectorAll('.lineup-detail li').length!==3)throw Error('Instructions hidden by radar');
 preview.remove();
 const personal=document.createElement('div');document.body.append(personal);
 let saved,editing=false;
 const personalData={...fixture.data.lineups,map_request:true,round:{show:false}};
 const personalCall=async(action,args)=>{
  if(action==='editing'){editing=args.active;return personalData;}
  if(action==='creating')return {text:'Pictures are unavailable. Save with radar markers.'};
  if(action==='change'){
   if(args.action==='delete')return {...personalData,undo_available:true};
   if(args.action==='save')saved=args;
   return {...personalData,document:{...personalData.document,lineups:[{...saved.row,id:'mine-test',mine:true}]}};
  }
  return personalData;
 };
 window.overlayRenderers.lineups(personal,personalData,personalCall);
 await window.lineupsUI.form(personal,personalData,personalCall);
 const editor=personal.querySelector('.lineup-editor');
 if(!editor?.open||!editing||!editor.querySelector('[data-marker="stand"]'))throw Error('New lineup form missing feet or editing subscription');
 const form=editor.querySelector('form');form.elements.name.value='My corner';form.elements.area.value='A site';form.elements.steps.value='Stand beside the wall.\\nAim at the roof.';
 const feet=editor.querySelector('[data-marker="stand"]');feet.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
 editor.querySelector('[data-land]').click();if(!editor.querySelector('[data-marker="land"]'))throw Error('Landing ring missing');
 editor.querySelector('[data-clear-land]').click();
 form.dispatchEvent(new Event('submit',{cancelable:true}));
 await Promise.resolve();await Promise.resolve();await Promise.resolve();
 if(saved?.action!=='save'||saved.row.stand.radar_x!==516||saved.row.land!==null||saved.row.aim!==null||saved.row.steps.length!==2)throw Error('Radar-only save failed');
 if(editing)throw Error('Editing subscription leaked after save');
 if(!personal.textContent.includes('Made by you'))throw Error('Saved personal lineup missing');
 personal.querySelector('[data-edit]').click();await Promise.resolve();await Promise.resolve();
 if(!personal.querySelector('.lineup-editor')?.textContent.includes('Edit lineup'))throw Error('Edit form missing');
 personal.querySelector('[data-cancel]').click();await Promise.resolve();await Promise.resolve();
 personal.querySelector('[data-delete]').click();await Promise.resolve();await Promise.resolve();
 if(!personal.querySelector('[data-undo]'))throw Error('Delete must offer visible Undo');
 personal.querySelector('[data-undo]').click();await Promise.resolve();await Promise.resolve();
 if(!personal.textContent.includes('Made by you'))throw Error('Undo did not restore lineup');
 await window.lineupsUI.form(personal,personalData,personalCall);
 const live={...personalData,map_request:false,position:{map:'mirage',stand:{x:100,y:200,z:30},aim:{pitch:10,yaw:20}}};
 window.overlayRenderers.lineups(personal,live,personalCall);
 if(!personal.querySelector('[data-position-note]').textContent.includes('were placed'))throw Error('Fresh GSI did not automatically place feet');
 personal.querySelector('[data-marker="stand"]').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
 const moved=personal.querySelector('[data-marker="stand"]').getAttribute('transform');
 window.overlayRenderers.lineups(personal,{...live,position:{...live.position,stand:{x:300,y:400,z:30}}},personalCall);
 if(personal.querySelector('[data-marker="stand"]').getAttribute('transform')!==moved)throw Error('GSI overwrote a manually placed marker');
 personal.querySelector('[data-create]').click();await Promise.resolve();await Promise.resolve();
 if(!personal.querySelector('[data-create-note]').textContent.includes('unavailable'))throw Error('Picture fallback missing');
 personal.querySelector('[data-cancel]').click();await Promise.resolve();await Promise.resolve();personal.remove();
 document.body.dataset.lineupsCheck='OK';
 }catch(error){document.body.dataset.lineupsCheck='ERROR: '+error.message;}})();`;
if(process.argv.includes('--check')){
 for(const theme of ['carbon','daylight']){
  const result=render({name:'lineups-check-'+theme,query:'preview=1&theme='+theme,extra:setup+checks,width:1280,height:1100,dump:true});
  if(!result.includes('data-lineups-check="OK"'))throw Error(theme+': '+(result.match(/data-lineups-check="[^"]*/)?.[0]||'Checks did not complete'));
 }
 console.log('Lineups Chromium: catalogue, filters, 18 details, picture view, new/edit/save, radar-only points, landing ring, delete/Undo, GSI placement and picture fallback OK (Carbon and Daylight)');
}else{
 const output=path.join(root,'docs/lineups/preview');fs.mkdirSync(output,{recursive:true});
 for(const theme of ['carbon','daylight']){
  render({name:'lineups-'+theme,query:'preview=1&theme='+theme,width:1280,height:1100,extra:setup,screenshot:path.join(output,theme+'.png')});
  console.log(path.join(output,theme+'.png'));
 }
 const newForm=setup+`(async()=>{const body=document.querySelector('[data-tool="lineups"] .tool-body');await window.lineupsUI.form(body,fixture.data.lineups,async()=>fixture.data.lineups);const f=body.querySelector('form');f.elements.name.value='My window smoke';f.elements.area.value='Mid';f.elements.steps.value='Stand beside the wall.\\nAim at the roof corner.\\nJump and throw.';})();`;
 render({name:'lineups-new',query:'preview=1&theme=carbon',width:1280,height:1100,extra:newForm,screenshot:path.join(output,'new-lineup.png')});
}
