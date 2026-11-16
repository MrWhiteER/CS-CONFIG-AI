/* Readiness only. The server owns permission, running-game checks and backups. */
let configsData = null, configsBusy = false;
function configIcon(kind) {
  const paths={ready:'M5 3H15L20 8V21H5ZM15 3V8H20M8 14L11 17L17 11',file:'M5 3H15L20 8V21H5ZM15 3V8H20M8 12H16M8 16H14',folder:'M3 6H10L12 8H21V20H3ZM3 6V4H10L12 6',merge:'M5 3V8Q5 12 12 12H19M12 3V21M9 18L12 21L15 18',drop:'M7 7L17 17M17 7L7 17M12 2A10 10 0 1 0 12 22A10 10 0 1 0 12 2',bind:'M3 7H21V18H3ZM6 10H7M10 10H11M14 10H15M18 10H19M7 14H17',alias:'M8 4L3 12L8 20M16 4L21 12L16 20M14 3L10 21',performance:'M4 19V12M10 19V5M16 19V9M22 19V3'};
  return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="'+(paths[kind]||paths.file)+'"/></svg>';
}
function renderConfigs() {
  const d=configsData, card=$('config-ready');
  if(!card)return;
  card.classList.toggle('config-is-busy',configsBusy);card.setAttribute('aria-busy',String(configsBusy));
  $('configs-refresh').disabled=configsBusy;
  $('configs-title').textContent=configsBusy?'Preparing your configs…':!d?.root?'Configs need another try':d.installed?'Your configs are ready in CS2':'Your configs are ready in the app';
  $('configs-state').textContent=d?.reason||'Refresh to prepare your files. You can keep using the app.';
  $('configs-location').textContent=d?.root?'App copy: '+d.root+(d.installed?' · CS2 copy: '+d.folder:''):'';
  $('configs-allow').hidden=!!d?.installed||prefsNow.cfg_write_ok===true;
}
async function prepareConfigs({choose=false}={}) {
  if(configsBusy)return null;
  configsBusy=true;renderConfigs();
  try {
    const d=await api('/api/configs/prepare',{});
    if(!d.ok)throw Error(d.error||'Could not prepare config files.');
    configsData=d;
    // An explicit personal collection remains selected. The prepared copy gives
    // a fresh/offline account a real collection for Keyboard and Scripts.
    if(choose&&$('cfg-folder')&&(!$('cfg-folder').value.trim()||$('cfg-folder').value===d.root)) {
      $('cfg-folder').value=d.folder;
      if(typeof rememberPrefs==='function')rememberPrefs();
    }
    return d;
  } catch(e) { configsData={reason:e.message};return null; }
  finally {configsBusy=false;renderConfigs();}
}
document.getElementById('configs-refresh')?.addEventListener('click',()=>prepareConfigs());
document.getElementById('configs-allow')?.addEventListener('click',()=>openSetupWizard({step:'permission'}));
document.getElementById('configs-import')?.addEventListener('click',()=>openSetupWizard({step:'import'}));
document.addEventListener('visibilitychange',()=>document.documentElement.classList.toggle('config-paused',document.hidden));
