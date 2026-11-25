const launcherScene = (() => {
  const hero = document.getElementById('home-hero');
  const screen = document.getElementById('launcher-screenshot');
  const agent = document.getElementById('launcher-agent');
  const choose = document.getElementById('launcher-screenshot-choose');
  const clear = document.getElementById('launcher-screenshot-clear');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const section = hero.closest('[data-panel="launcher"]');
  const keys = document.getElementById('launcher-key-lights');
  let active = true, starting = false, connected = false;
  let readLighting = null, lightingPending = false, lightingAgain = false;

  const sides = Math.random() < .5 ? ['ct', 't'] : ['t', 'ct'];

  // Physical ISO/ANSI letters and common CS2 keys, using the same HID usages
  // as the keyboard lighting palette on the server. The row coordinates
  // project those keys onto the photographed keyboard's perspective.
  const rows = [
    [[41,30,31,32,33,34,35,36,37,38,39,45,46,42], [1084,651], [1450,619]],
    [[43,20,26,8,21,23,28,24,12,18,19,47,48,49], [1093,661], [1464,629]],
    [[57,4,22,7,9,10,11,13,14,15,51,52,40], [1103,670], [1475,637]],
    [[225,29,27,6,25,5,17,16,54,55,56,229], [1114,680], [1480,646]],
    [[224,227,226,44,230,231,228], [1126,693], [1478,658]],
  ];
  const leds = [];
  for (const [codes, first, last] of rows) {
    codes.forEach((usage, index) => {
      const led = document.createElement('i');
      const t = index / (codes.length - 1);
      led.style.left = (first[0] + t * (last[0] - first[0])) / 2172 * 100 + '%';
      led.style.top = (first[1] + t * (last[1] - first[1])) / 724 * 100 + '%';
      led.dataset.usage = usage;
      keys.append(led);
      leds.push([usage, led]);
    });
  }
  const rgb = values => Array.isArray(values) && values.length === 3 &&
    values.every(v => Number.isInteger(v) && v >= 0 && v <= 255) ? 'rgb(' + values.join(',') + ')' : '';
  function paintKeyboard(frame) {
    for (const [usage, led] of leds) {
      const color = rgb(frame?.keys?.[usage] || frame?.base);
      if (color) led.style.setProperty('--key-light', color);
      else led.style.removeProperty('--key-light');
    }
  }
  async function refreshLighting() {
    if (!readLighting) return;
    if (lightingPending) { lightingAgain = true; return; }
    lightingPending = true;
    try {
      const result = await readLighting('/api/launcher/lighting', {});
      if (result.ok) paintKeyboard(result.frame);
    } catch (_) {
      // The theme cue stays up when no keyboard configuration is accessible.
    } finally {
      lightingPending = false;
      if (lightingAgain) { lightingAgain = false; refreshLighting(); }
    }
  }

  function sync() {
    const paused = active || starting || document.hidden || section.classList.contains('hidden') || reduced.matches;
    hero.classList.toggle('scene-paused', paused);
  }

  screen.addEventListener('error', () => {
    screen.removeAttribute('src');
    choose.textContent = 'Choose another screenshot';
  });
  agent.addEventListener('load', () => {
    agent.parentElement.hidden = agent.naturalWidth !== agent.naturalHeight * 6;
  });
  agent.addEventListener('error', () => { agent.parentElement.hidden = true; });
  document.addEventListener('visibilitychange', sync);
  reduced.addEventListener('change', sync);
  new MutationObserver(sync).observe(section, {attributes: true, attributeFilter: ['class']});

  return {
    refreshLighting,
    activity(value) {
      active = value;
      sync();
    },
    launching(value) {
      starting = value;
      sync();
    },
    connect(api, status) {
      if (connected) return;
      connected = true;
      readLighting = api;
      refreshLighting();
      async function update(body) {
        choose.disabled = clear.disabled = true;
        try {
          const result = await api('/api/launcher/media', body);
          if (!result.ok) throw Error(result.error);
          if (result.url) screen.src = result.url + (body.choose ? '&v=' + Date.now() : '');
          else screen.removeAttribute('src');
          const actorUrl = sides.map(side => result.agents?.[side]).find(Boolean);
          if (actorUrl && agent.getAttribute('src') !== actorUrl) {
            agent.parentElement.hidden = true;
            agent.src = actorUrl;
          } else if (!actorUrl) {
            agent.parentElement.hidden = true;
            agent.removeAttribute('src');
          }
          choose.textContent = result.screenshot ? 'Change screenshot' : 'Add gameplay screenshot';
          choose.title = result.screenshot || 'Choose a local CS2 screenshot';
          clear.hidden = !result.screenshot;
        } catch (err) {
          if (body.choose || body.clear) status(err.message, true);
        } finally {
          choose.disabled = clear.disabled = false;
        }
      }
      choose.onclick = () => update({choose: true});
      clear.onclick = () => update({clear: true});
      update({});
    },
  };
})();
