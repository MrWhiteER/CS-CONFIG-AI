"""Local analysis tools: debugging, sync review, benchmarks and diagnostics."""
from __future__ import annotations

import base64
import io
import json
import platform
import re
import secrets
import time
import zipfile
from pathlib import Path

from . import __version__, fileio


def script_debug(state, body):
    from . import scriptdebug, webui

    checked = webui._scriptgen_check(state, body)
    built = checked['built']
    spec = dict(body.get('spec') or {})
    events = body.get('events')
    if events is not None and (not isinstance(events,list) or len(events)>24):
        raise ValueError('Use at most 24 simulated key events.')
    return {'built': built, 'simulation': scriptdebug.simulate(built['lines'], built['entry'],
            scan=state.cfg_scan, events=events, mode=spec.get('mode','press'),
            target=spec.get('target',''), target_before=spec.get('target_now',''))}


def sync_review(state, body):
    from . import autosync, cloud, webui
    from .cli import load_prefs, save_prefs

    if not cloud.signed_in():
        raise ValueError('Connect your Steam account in Accounts before comparing PCs.')
    resolution=str(body.get('resolution') or '')
    loop = webui._sync_loop(state)
    with loop._lock:
        result = autosync.run(
            webui._active_account(state), webui._game_cfg_root(state), state.cfg_folder,
            load_prefs=load_prefs, save_prefs=save_prefs, force=True,
            preview=not resolution, resolution=resolution,
            expected_local=str(body.get('local_hash') or ''),
            expected_remote=body.get('remote_hash'),
        )
        if resolution:
            loop.last = result
    if not result.get('ok'):
        raise ValueError(result.get('reason') or 'The sync comparison could not be completed.')
    if resolution and result.get('action')=='pull' and not result.get('waiting'):
        result['applied']=webui._after_pull(state,result)
    return result


def _context(state):
    from . import profiles, webui
    from .cli import load_prefs

    ui=profiles.ui_for(load_prefs(),webui._active_account(state))
    machine=getattr(state,'machine',None)
    driver=getattr(getattr(machine,'gpu',None),'driver_version','') or ''
    return {'preset':ui.get('intent','balanced'),'system':platform.machine(),
            'cpu':str(getattr(getattr(machine,'cpu',None),'name','')),
            'gpu':str(getattr(getattr(machine,'gpu',None),'name','')), 'driver':str(driver)}


def benchmark_runs(state, body):
    from . import benchmarks, telemetry

    sessions=telemetry.load_sessions(100)
    action=body.get('action')
    if action=='arm':
        benchmarks.arm(str(body.get('slot')),str(body.get('map') or ''),_context(state))
    elif action=='compare':
        result=benchmarks.compare(sessions,body.get('left'),body.get('right'))
        benchmarks.remember(result)
        return {'comparison':result}
    elif action=='cancel':
        with fileio.LOCK:
            data=benchmarks.load(); data.pop('armed',None); benchmarks._save(data)
    return {'plan':benchmarks.load(),'context':_context(state),
            'runs':[{k:s.get(k) for k in ('stamp','started','duration','resolution','intent','overlay','benchmark')} for s in sessions]}


def config_trace(state, body):
    from . import backup, cfgscan, defaults, gamewatch, history, webui

    result=webui._rescan(state)
    if result is None:
        raise ValueError('Choose a configuration folder first.')
    name=str(body.get('name') or '').strip().lower()[:120]
    kind=str(body.get('kind') or 'setting')
    if not name or kind not in ('setting','key','alias'):
        raise ValueError('Choose a setting, key or alias and enter its name.')
    chain=cfgscan.startup_chain(result)
    rows=[]
    definitions=[]
    if kind=='key':
        physical=cfgscan.physical_key(name)
        definitions=[d for values in result.binds.values() for d in values if cfgscan.physical_key(d.key)==physical]
    elif kind=='alias':
        definitions=result.aliases.get(name) or []
    else:
        definitions=result.settings.get(name) or []
    for item in sorted(definitions,key=lambda d:d.order):
        rows.append({'file':item.file,'line':item.line,'value':getattr(item,'body',getattr(item,'value','')),
                     'startup':item.file in chain and not getattr(item,'nested',False),'order':item.order})
    startup=[r for r in rows if r['startup']]
    winner=startup[-1] if startup else None
    saved=None
    if getattr(state,'steam_root',None) and state.users:
        snap=gamewatch.take(gamewatch.cfg_dir(state.steam_root,webui._active_account(state)))
        values=snap.values.get('Key binds' if kind=='key' else 'In-game settings') or {}
        if kind=='key':
            saved=next((v for k,v in values.items() if cfgscan.physical_key(k)==cfgscan.physical_key(name)),None)
        elif kind=='setting':
            saved=values.get(name)
    stock=defaults.for_key(defaults.load(getattr(state,'cs2_install',None)),name) if kind=='key' else None
    files={str(result.files[k].path.resolve()) for k in result.files if any(r['file']==result.files[k].relative for r in rows)}
    related=[]
    for entry in history.entries(60):
        if entry.get('kind')!='app':
            continue
        stamp=entry['id'].removeprefix('app:')
        matching=next((s for s in backup.list_sets() if s.stamp==stamp),None)
        if matching and any(str(Path(p).resolve()) in files for p in matching.files):
            related.append({'id':entry['id'],'title':entry['title'],'at':entry['at'],
                            'files':[Path(p).name for p in matching.files]})
    return {'name':name,'kind':kind,'definitions':rows,'winner':winner,'saved_game_value':saved,
            'stock':stock,'history':related[:8],
            'explanation':'The winner is the last explicit custom definition in the startup chain. A manually loaded map config or an in-game edit can change the live value afterward; this view does not read game memory.'}


def trace_undo(state, body):
    from . import history, webui

    trace=config_trace(state,body)
    identity=str(body.get('id') or '')
    if identity not in {e['id'] for e in trace['history']}:
        raise ValueError('Reload the trace and select one of its recorded changes.')
    out=history.swing(identity.removeprefix('app:'),history.BACK,force=False)
    if out.get('ok'):
        webui._rescan(state)
        webui._refresh_apply_now(state)
    return out


_PRIVATE=re.compile(r'(password|token|secret|cookie|authorization|email|steam.?id|account|user.?id|api.?key)',re.I)


def redact(value):
    if isinstance(value,dict):
        return {k:('[redacted]' if _PRIVATE.search(str(k)) else redact(v)) for k,v in value.items()}
    if isinstance(value,list):
        return [redact(v) for v in value]
    if isinstance(value,str):
        value=re.sub(r'(?i)\b[A-Z]:[\\/][^\n\r"<>]*','[local path]',value)
        value=re.sub(r'(?i)\bBearer\s+\S+','Bearer [redacted]',value)
        value=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[email]',value)
        value=re.sub(r'\b7656119\d{10}\b','[Steam identity]',value)
        value=re.sub(r'(?i)\b(token|password|secret|cookie|authorization)\s*[:=]\s*\S+',r'\1=[redacted]',value)
        value=re.sub(r'(?i)(access_token|api_key)\s*[:=]\s*\S+',r'\1=[redacted]',value)
        value=re.sub(r'\b[a-fA-F0-9]{32,}\b','[identifier]',value)
    return value


def diagnostics(state, body):
    from . import autosync, mapconfig, webui

    if body.get('action')=='export':
        held=getattr(state,'diagnostic_preview',None)
        if not held or held['token']!=body.get('token') or time.time()-held['at']>600:
            raise ValueError('Preview a fresh diagnostic package before exporting.')
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('diagnostics.json',json.dumps(held['data'],indent=2))
            archive.writestr('README.txt','Local diagnostic snapshot. Tokens, account identifiers, private paths, personal config contents and full logs are excluded. Review before sharing.\n')
        return {'filename':'CS-CONFIG-AI-diagnostics.zip','data':base64.b64encode(buffer.getvalue()).decode('ascii')}
    result=getattr(state,'cfg_scan',None)
    account=webui._active_account(state)
    sync=autosync.load_agreed().get(str(account)) or {}
    data=redact({'app_version':__version__,'system':platform.system(),'os_release':platform.release(),
          'python':platform.python_version(),'capabilities':{'game_install_found':bool(getattr(state,'cs2_install',None)),
          'config_folder_loaded':result is not None,'config_file_count':len(result.files) if result else 0},
          'sync':{'pending':bool(sync.get('pending')), 'failed_files':len(sync.get('failed') or [])},
          'map_restore':{'pending':bool(mapconfig.load().get('needs_reset')),
          'missing_values':mapconfig.restore_missing(result) if result is not None else []}})
    token=secrets.token_urlsafe(20)
    state.diagnostic_preview={'token':token,'data':data,'at':time.time()}
    return {'token':token,'data':data,'excluded':['Credentials and tokens','Account identifiers','Personal config contents','Private paths','Full logs and chat history']}


def _practice_path():
    from .paths import user_data_dir
    return user_data_dir()/'practice-session.json'


def _practice_load():
    try:
        data=json.loads(_practice_path().read_text(encoding='utf-8'))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):
        return {}


def _practice_save(data):
    path=_practice_path(); path.parent.mkdir(parents=True,exist_ok=True)
    fileio.write_text(path,json.dumps(data,indent=1))


def practice(state, body):
    from . import cfgscan, gamewatch, mapconfig, maps, quickfix, webui

    result=webui._rescan(state)
    action=body.get('action')
    held=_practice_load()
    mismatches = []
    if action=='start':
        if held.get('status') in ('active','restore_pending'):
            raise ValueError('Finish and verify the current practice session first.')
        if result is None:
            raise ValueError('Choose your config folder first.')
        if quickfix._game_running():
            raise ValueError('Close CS2 before capturing the normal baseline and starting guided practice.')
        if mapconfig.load().get('needs_reset'):
            raise ValueError('Finish the pending map restoration before starting another practice session.')
        file=str(body.get('file') or '')
        map_id=maps.canonical(str(body.get('map') or '')).lower()
        if not map_id or not cfgscan.is_match_profile(result,file):
            raise ValueError('Choose a map and an eligible practice config.')
        webui._map_capture_baseline(state)
        previous=next((s for s in mapconfig.load()['setups'] if s.get('file')==file),None)
        out=mapconfig.set_setup(result,file,True,[map_id])
        if out['restore_missing']:
            mapconfig.set_setup(result,file,bool(previous),(previous or {}).get('maps',[]))
            raise ValueError('The normal baseline is incomplete: '+', '.join(out['restore_missing'])+'. Save your normal game settings and review Map configs first.')
        held={'status':'active','started':time.time(),'file':file,'map':map_id,'previous':previous,
              'root':str(result.root.resolve()),'done':[],
              'steps':['Start an offline practice map: '+maps.display(map_id),
                       'Load your selected config: exec '+file,
                       'Practise your chosen lineups using the overlay',
                       'Leave the map, return to the main menu and let the reset run',
                       'Close CS2, then verify that the saved normal values are back']}
        _practice_save(held)
        webui._refresh_apply_now(state)
    elif action=='step':
        if held.get('status')!='active':
            raise ValueError('Start a practice session first.')
        index=int(body.get('index',-1))
        if not 0<=index<len(held['steps']):
            raise ValueError('Unknown practice step.')
        done=set(held.get('done') or [])
        if body.get('done'): done.add(index)
        else: done.discard(index)
        held['done']=sorted(done); _practice_save(held)
    elif action=='end':
        if held.get('status')!='active':
            raise ValueError('There is no active practice session.')
        if result is None or held.get('root') != str(result.root.resolve()):
            raise ValueError('Open the configuration folder used for the current practice session.')
        mapconfig.update({'needs_reset':True})
        mapconfig.write_reset(result); webui._refresh_apply_now(state)
        held['status']='restore_pending'; _practice_save(held)
    elif action=='verify':
        if held.get('status') not in ('active','restore_pending') or result is None or held.get('root')!=str(result.root.resolve()):
            raise ValueError('Open the configuration folder used for the current practice session.')
        if quickfix._game_running():
            raise ValueError('Close CS2 first so its saved settings can be checked.')
        if not getattr(state,'steam_root',None) or not state.users:
            raise ValueError('Steam account data is unavailable; saved game values cannot be verified.')
        folder=gamewatch.cfg_dir(state.steam_root,webui._active_account(state))
        snap=gamewatch.take(folder)
        touched=mapconfig.touched(result,[held['file']])
        baseline=mapconfig._baseline(result)
        normal,taken_off=mapconfig._normal_binds(result)
        keys={cfgscan.physical_key(k):v for k,v in (snap.values.get('Key binds') or {}).items()}
        settings=snap.values.get('In-game settings') or {}
        mismatches=[]
        for physical,(spelled,_) in touched['keys'].items():
            original=normal.get(physical)
            expected='' if physical in taken_off else original.body if original else (baseline.get('keys') or {}).get(physical)
            if expected is None:
                from .scriptgen import STOCK_FALLBACK
                expected=STOCK_FALLBACK.get(spelled.lower())
            if expected is None or keys.get(physical,'')!=expected:
                mismatches.append(spelled)
        chain=cfgscan.startup_chain(result)
        for name in touched['settings']:
            if mapconfig._server_only(name) or name in mapconfig.cfglang.EXECUTABLE:
                continue
            defs=[d for d in result.settings.get(name,[]) if d.file in chain]
            expected=max(defs,key=lambda d:d.order).value if defs else (baseline.get('settings') or {}).get(name)
            if expected is None or settings.get(name)!=expected:
                mismatches.append(name)
        relevant=['cs2_user_keys_0_slot0.vcfg'] if touched['keys'] else []
        if any(not mapconfig._server_only(name) and name not in mapconfig.cfglang.EXECUTABLE
               for name in touched['settings']):
            relevant.append('cs2_user_convars_0_slot0.vcfg')
        if any(not (folder/f).is_file() or (folder/f).stat().st_mtime<held['started'] for f in relevant):
            raise ValueError('The game has not saved fresh settings since practice started. Play, return to the menu, close CS2 and check again.')
        if not mismatches:
            current = next((s for s in mapconfig.load()['setups'] if s.get('file') == held['file']), None)
            if current == {'file': held['file'], 'maps': [held['map']]}:
                previous = held.get('previous')
                mapconfig.set_setup(result, held['file'], bool(previous), (previous or {}).get('maps', []))
            mapconfig.update({'needs_reset': False})
            held['status'] = 'verified'
            held['verified_at'] = time.time()
            _practice_save(held)
    options=mapconfig.summary(result) if result else {'setups':[],'maps':[]}
    lineups=[]
    if held.get('map') in ('de_mirage','mirage'):
        catalogue=json.loads((Path(__file__).parent/'lineups'/'data'/'mirage.json').read_text(encoding='utf-8'))
        lineups=[{'name':r['name'],'area':r.get('area'),'type':r.get('type')} for r in catalogue.get('lineups',[])][:12]
    return {'session':held,'options':options,'lineups':lineups,
            'verified':held.get('status')=='verified','mismatches':mismatches}


ROUTES={'/api/tools/script-debug':script_debug,'/api/tools/sync':sync_review,
        '/api/tools/benchmarks':benchmark_runs,'/api/tools/trace':config_trace,
        '/api/tools/trace/undo':trace_undo,'/api/tools/diagnostics':diagnostics,
        '/api/tools/practice':practice}
