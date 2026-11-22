"""Profile Rail contracts and real selection/plan JS, without a desktop service."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import unittest

PAGE = Path(__file__).resolve().parents[1] / "cs2cfg" / "web" / "index.html"


class ProfileRailWeb(unittest.TestCase):
    def test_legacy_notch_is_removed(self):
        page = PAGE.read_text(encoding="utf-8")
        for obsolete in ("NOTCH_PATH", "modenotch", "paintModeBadge", "mode-badge", "modemark", "MODE_WORD"):
            self.assertNotIn(obsolete, page)

    def test_selection_plan_and_motion_lifetimes(self):
        node = shutil.which("node")
        if not node:
            candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "nodejs/node.exe"
            if candidate.is_file():
                node = str(candidate)
        if not node:
            self.skipTest("Node is needed to exercise the profile selection path")
        page = PAGE.read_text(encoding="utf-8")
        choose = page[page.index("function chooseIntent("):page.index("(function wireModeCards")]
        preview = page[page.index("let planRevision = 0"):page.index("/* The live \"applying\" list")]
        start = page.index("async function applyProfile(")
        preview += page[start:page.index("/* Profile Rail:", start)]
        motion = page[page.index("function homeAnimate("):page.index("function homeVisible()")]
        rail_select = page[page.index("  function select(name)"):page.index("  root.addEventListener('click'", page.index("const profileRail ="))]
        harness = HARNESS.replace("SOURCE", json.dumps(choose + preview + motion + rail_select))
        result = subprocess.run([node, "-e", harness], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rail_uses_live_status_and_accessible_manual_selection(self):
        page = PAGE.read_text(encoding="utf-8")
        rail = page[page.index("const profileRail ="):page.index("// --- common settings")]
        self.assertIn("box.hidden ? 'unknown' : box.dataset.state", rail)
        self.assertIn("profileApplyBusy ? 'applying'", rail)
        self.assertIn("attributeFilter:['data-state','hidden']", rail)
        self.assertIn("setTimeout(peek,120)", rail)
        self.assertIn('role="radiogroup"', rail)
        self.assertIn('aria-controls="profile-shelf"', rail)
        self.assertIn("root.addEventListener('focusout'", rail)
        self.assertIn("buttons[at].focus()", rail)
        key_handler = rail[rail.index("root.addEventListener('keydown'"):rail.index("document.addEventListener('pointerdown'")]
        self.assertNotIn("chooseIntent", key_handler)
        self.assertNotIn("select(", key_handler)


HARNESS = r'''
const assert = require('node:assert/strict');
let intent='competitive', planned=null, verificationRevision=0, verificationDirty=false, settingsSub='look';
const INTENTS=['competitive','balanced','quality'];
const verification={hidden:true,dataset:{}};
const $=id=>id==='verification'?verification:null;
let calls=[],undo,begin=0,home=false,open=false,notes=[],pending=[],feed=[],settled=0;
const homeVisible=()=>home;
const paintIntent=()=>{};
const rememberPrefs=()=>{};
const noteChange=(label,revert)=>{undo=revert;notes.push(label)};
const presetBegin=()=>begin++;
const busy=()=>{};
const presetClose=()=>{};
const status=()=>{};
const esc=s=>s;
const toggle=()=>{};
const settleChanges=()=>settled++;
const renderVerification=()=>{};
const profileRail={syncStatus(){}};
const applyFeed={start:t=>feed.push(['start',t]),play:(r)=>feed.push(['play',r.intent]),fail:t=>feed.push(['fail',t])};
const requestBody=()=>({intent});
const api=(url,body)=>{calls.push([url,body]);return new Promise((resolve,reject)=>pending.push({url,resolve,reject}));};
const renderPlan=p=>{planned=p;};
const document={hidden:false};
const homeMotion={reduced:{matches:false},animations:new Set()};
const tick=async()=>{for(let i=0;i<6;i++)await Promise.resolve();};
const source=SOURCE;
// Direct eval keeps the production functions in this test's scope.
eval(source+`\n
(async()=>{
  // Picking a mode applies it straight away: no preview step, no question.
  select('balanced');
  assert.equal(intent,'balanced');assert.equal(begin,0);assert.equal(notes.length,1);
  assert.equal(calls[0][0],'/api/apply');assert.equal(calls[0][1].intent,'balanced');
  assert.deepEqual(feed[0],['start','Applying Balanced']);
  // A second pick while the first is still applying waits, then applies the newest.
  select('quality');assert.equal(intent,'quality','selection is never locked');
  assert.equal(calls.length,1,'one apply at a time');
  pending.shift().resolve({ok:true,steps:[],verification:{}});await tick();
  assert.deepEqual(feed[1],['play','balanced']);
  assert.equal(calls[1][0],'/api/plan');
  assert.equal(calls[2][0],'/api/apply');assert.equal(calls[2][1].intent,'quality','queued pick applies the latest mode');
  pending.shift().resolve({intent:'balanced'});
  pending.shift().resolve({ok:true,steps:[],verification:{}});await tick();
  assert.equal(settled,2);
  // Undo from the leave-the-app window puts the old mode back and applies it.
  undo();assert.equal(intent,'balanced');
  const last=calls[calls.length-1];
  assert.equal(last[0],'/api/apply');assert.equal(last[1].intent,'balanced');
  // A failed apply says so in the list rather than pretending.
  pending.splice(0).forEach(p=>p.url==='/api/apply'?p.reject(Error('offline')):p.resolve({intent}));await tick();
  assert.deepEqual(feed[feed.length-1],['fail','offline']);
  home=true;
  const el={getClientRects:()=>[{}],animate(frames,timing){return {frames,timing,addEventListener(){}}}};
  let animation=homeAnimate(el,[{transform:'translateX(0)'},{transform:'translateX(20px)'}],560);
  assert.equal(animation.timing.duration,560);assert.ok(homeMotion.animations.has(animation));
  homeMotion.reduced.matches=true;animation=homeAnimate(el,[{transform:'translateX(20px)'}],560);
  assert.equal(animation.timing.duration,80);assert.deepEqual(animation.frames,[{opacity:0},{opacity:1}]);
  document.hidden=true;assert.equal(homeAnimate(el,[],560),undefined,'hidden windows never start motion');
  document.hidden=false;el.getClientRects=()=>[];assert.equal(homeAnimate(el,[],560),undefined,'hidden controls never start motion');
})().catch(e=>{console.error(e);process.exitCode=1});`);
'''


if __name__ == "__main__":
    unittest.main()
