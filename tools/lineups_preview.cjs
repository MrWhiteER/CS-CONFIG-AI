/* Offline preview and browser checks. All output stays inside this worktree. */
const fs=require('fs'),path=require('path');
const {render}=require('./overlay_preview.cjs');
const root=path.resolve(__dirname,'..'),doc=JSON.parse(fs.readFileSync(path.join(root,'cs2cfg/lineups/data/mirage.json'),'utf8'));
const setup=`window.overlayPanelActive(false);
 const fixture=window.overlayPreview;
 fixture.manifest.tools.push({id:'lineups',title:'Lineups',icon:'globe',refresh_hz:0,default_size:[980,610],pinnable:true});
 fixture.manifest.settings.overlay_tools.push('lineups');
 fixture.manifest.settings.overlay_layout=Object.fromEntries(fixture.manifest.tools.map(t=>[t.id,{open:false}]));
 fixture.manifest.settings.overlay_layout.lineups={x:90,y:8,width:1000,height:620,open:true,opacity:95};
 fixture.data.lineups={maps:[{id:'mirage',name:'Mirage'},{id:'inferno',name:'Inferno'}],document:${JSON.stringify(doc)},art:null,round:{show:true,name:'Mirage',side:'T',buying:true}};
 window.overlayPanelActive(true);`;
const checks=`(async()=>{try{
 const body=document.querySelector('[data-tool="lineups"] .tool-body'),ui=window.lineupsUI;
 if(body.querySelectorAll('[data-lineup]').length!==13)throw Error('Seed list missing');
 const query=body.querySelector('[data-query]');query.disabled=false;query.value='window';query.dispatchEvent(new Event('input'));
 if(body.querySelectorAll('[data-lineup]').length!==3)throw Error('Type ahead failed');
 query.value='';query.dispatchEvent(new Event('input'));
 const side=body.querySelector('[data-side]');side.disabled=false;side.value='CT';side.dispatchEvent(new Event('change'));
 if(body.querySelectorAll('[data-lineup]').length!==1||!body.querySelector('.lineup-detail').textContent.includes('Deep A ramp'))throw Error('Side filter failed');
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
 document.body.dataset.lineupsCheck='OK';
 }catch(error){document.body.dataset.lineupsCheck='ERROR: '+error.message;}})();`;
if(process.argv.includes('--check')){
 const result=render({name:'lineups-check',extra:setup+checks,dump:true});
 if(!result.includes('data-lineups-check="OK"'))throw Error(result.match(/data-lineups-check="[^"]*/)?.[0]||'Checks did not complete');
 console.log('Lineups Chromium: list, type ahead, side filter, synonyms, empty state, plain text, credit, radar annotations, round fold, preserved search and map switch OK');
}else{
 const output=path.join(root,'docs/lineups/preview');fs.mkdirSync(output,{recursive:true});
 for(const theme of ['carbon','daylight']){
  render({name:'lineups-'+theme,query:'preview=1&theme='+theme,width:1280,height:900,extra:setup,screenshot:path.join(output,theme+'.png')});
  console.log(path.join(output,theme+'.png'));
 }
}
