const fs=require('node:fs'),vm=require('node:vm');
const p=fs.readFileSync('cs2cfg/web/index.html','utf8');
const slice=(a,b)=>p.slice(p.indexOf(a),p.indexOf(b,p.indexOf(a)));
const source=slice('function chooseIntent(','(function wireModeCards')+slice('async function previewPlan()','$("preview").addEventListener("click", previewPlan)')+slice('function homeAnimate(','function homeVisible()')+slice('  function select(name)',"  root.addEventListener('click'");
const py=fs.readFileSync('tests/test_profile_rail_web.py','utf8');let harness=py.split("HARNESS = r'''")[1].split("'''",1)[0];harness=harness.replace('SOURCE',JSON.stringify(source));vm.runInThisContext('(function(require){'+harness+'})',{filename:'profile-rail-regression.cjs'})(require);
console.log('Profile Rail production Node harness executed');

