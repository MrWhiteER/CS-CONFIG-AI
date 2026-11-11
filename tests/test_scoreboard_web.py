"""Exercise the real scoreboard JS with a minimal DOM, without a live account."""
from pathlib import Path
import json
import shutil
import subprocess

import pytest


def test_scoreboard_rendering_and_async_lifetime():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to exercise the scoreboard renderer")
    page = Path("cs2cfg/web/index.html").read_text(encoding="utf-8")
    source = page[page.index("let statsRequest = 0;"):page.index("/* The download strip")]
    harness = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const elements = new Map();
const element = () => ({innerHTML:'', textContent:'', className:'', hidden:false,
  classList:{add(){},remove(){},toggle(){},contains(){return false;}}, focus(){}});
const $ = id => {if(!elements.has(id))elements.set(id,element());return elements.get(id);};
const deferred = () => {let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject};};
let replies=[], calls=[];
const context = {console,document:{activeElement:null,hidden:false,addEventListener(){}}, $, 
  fcData:{player:{player_id:'owner',nickname:'DifferentName'}},whoData:null,
  FC_LEVEL_COLORS:['','#eee','#1ce400','#1ce400','#ffc800','#ffc800','#ffc800','#ffc800','#ff6309','#ff6309','#ff1f00'],
  esc:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
  fcMapAsset:()=> 'assets/maps/dust2.webp',fcMapName:()=> 'Dust2',
  paintGetRow(){},checkWaiting(){},stopWaitingWatch(){},
  statsShown:null,statsWaiting:null,
  api:(url,body)=>{calls.push([url,body]);return replies.shift().promise;}
};
vm.createContext(context);
vm.runInContext(SOURCE,context);
const player=(id,k,d)=>({player_id:id,nickname:id,kills:k,deaths:d,assists:2,adr:100,kd:1.5,kr:.8,headshots:5,hs_percent:50,penta:0,quadro:0,triple:1,double:2,mvps:3});
const match={match_id:'match',map:'de_dust2',score:'6 / 13',page:'https://faceit.com/match',teams:[
  {name:'team_owner',won:false,score:6,first_half:5,second_half:1,players:[player('owner',10,14),player('a',8,13),player('b',8,13),player('c',8,13),player('d',8,13)]},
  {name:'other',won:true,score:13,first_half:7,second_half:6,players:[player('e',20,10),player('f',20,10),player('g',8,13),player('h',8,13),player('i',8,13)]}]};
context.match=match;
const rendered=context.renderStatsTeams(match);
assert.equal((rendered.match(/data-stat="kills" class="mstat-best"/g)||[]).length,2,'kill leaders tie across players');
assert.equal((rendered.match(/data-stat="deaths" class="mstat-best"/g)||[]).length,2,'lowest deaths wins');
assert.equal((rendered.match(/data-stat="adr" class="mstat-best"/g)||[]).length,10,'all equal values win');
assert.equal((rendered.match(/class="is-you"/g)||[]).length,1,'owner identified by FACEIT id');
assert.equal((rendered.match(/class="mstat-level"/g)||[]).length,10);
assert.equal((rendered.match(/class="mstat-kill"/g)||[]).length,20,'only nonzero multi kills get chips');
assert.ok(rendered.includes('★ 3'));
assert.ok(rendered.includes('scaleX(1)'));
context.paintStatsHeader(match);
assert.equal($('mstat-result').textContent,'LOSS');
assert.equal($('mstat-title').textContent,'Dust2  6 : 13');
assert.ok(!context.statsBadge('evil','javascript:alert(1)','').includes('<img'));
assert.ok(context.statsBadge('<b>','https://cdn/a" onload="bad','').includes('&quot;'));
const missing=structuredClone(match);missing.teams[0].players[0].adr=null;
assert.ok(!context.renderStatsTeams(missing).includes('NaN'));
(async()=>{
  const stats=deferred(),identities=deferred();replies=[stats,identities];
  const pending=context.openStats('match');
  assert.ok($('mstat-body').innerHTML.includes('mstat-skeleton'));
  stats.resolve(match);await pending;
  assert.ok($('mstat-body').innerHTML.includes('mstat-teams'),'numbers render before identities resolve');
  assert.equal(calls[1][0],'/api/demos/identities');
  identities.resolve({teams:[{avatar:'https://cdn/team',players:[{player_id:'owner',avatar:'https://cdn/player',level:10}]}]});
  await Promise.resolve();await Promise.resolve();
  assert.ok($('mstat-teams').innerHTML.includes('https://cdn/player'));
  assert.equal(match.teams[0].avatar,'https://cdn/team');
  const late=deferred();replies=[late];
  const closing=context.openStats('late');
  vm.runInContext('++statsRequest',context); // hideStats invalidates the request.
  $('mstat-body').innerHTML='closed';
  late.resolve(match);await closing;
  assert.equal($('mstat-body').innerHTML,'closed','late stats cannot reopen or overwrite after close');
  const failure=deferred();replies=[failure];
  const failed=context.openStats('failed');failure.reject(Error('offline'));await failed;
  assert.ok($('mstat-body').innerHTML.includes('role="alert"'));
  assert.ok($('mstat-body').innerHTML.includes('mstat-retry'));
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    result = subprocess.run([node, "-e", harness.replace("SOURCE", json.dumps(source))],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
