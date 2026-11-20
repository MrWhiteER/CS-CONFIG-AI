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
 document.body.dataset.lineupsCheck='OK';
 }catch(error){document.body.dataset.lineupsCheck='ERROR: '+error.message;}})();`;
if(process.argv.includes('--check')){
 for(const theme of ['carbon','daylight']){
  const result=render({name:'lineups-check-'+theme,query:'preview=1&theme='+theme,extra:setup+checks,width:1280,height:1100,dump:true});
  if(!result.includes('data-lineups-check="OK"'))throw Error(theme+': '+(result.match(/data-lineups-check="[^"]*/)?.[0]||'Checks did not complete'));
 }
 console.log('Lineups Chromium: list, type ahead, side filter, synonyms, empty state, plain text, credit, radar annotations, round fold, preserved search, map switch, all 18 details fit without scrolling, picture status and thumbnail enlargement OK');
}else{
 const output=path.join(root,'docs/lineups/preview');fs.mkdirSync(output,{recursive:true});
 for(const theme of ['carbon','daylight']){
  render({name:'lineups-'+theme,query:'preview=1&theme='+theme,width:1280,height:1100,extra:setup,screenshot:path.join(output,theme+'.png')});
  console.log(path.join(output,theme+'.png'));
 }
}
