const launcherScene = (() => {
  const hero = document.getElementById('home-hero');
  const screen = document.getElementById('launcher-screenshot');
  const agent = document.getElementById('launcher-agent');
  const choose = document.getElementById('launcher-screenshot-choose');
  const clear = document.getElementById('launcher-screenshot-clear');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const section = hero.closest('[data-panel="launcher"]');
  let active = true, starting = false, connected = false;

  const sides = Math.random() < .5 ? ['ct', 't'] : ['t', 'ct'];

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
