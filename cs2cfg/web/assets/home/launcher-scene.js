const launcherScene = (() => {
  const hero = document.getElementById('home-hero');
  const video = document.getElementById('launcher-clip');
  const picture = hero.querySelector('.hero-background');
  const choose = document.getElementById('launcher-clip-choose');
  const clear = document.getElementById('launcher-clip-clear');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const section = hero.closest('[data-panel="launcher"]');
  let clipUrl = '', position = 0, active = true, starting = false, connected = false;
  let mediaError = false;

  const frame = 'assets/home/hero-player-' + (Math.random() < .5 ? 'navy' : 'sand') + '.webp';
  picture.src = frame;
  hero.style.setProperty('--hero-frame', 'url("' + frame + '")');

  function sync() {
    const paused = active || starting || document.hidden || section.classList.contains('hidden') || reduced.matches;
    hero.classList.toggle('scene-paused', paused);
    if (paused || !clipUrl || mediaError) {
      if (video.hasAttribute('src')) {
        if (Number.isFinite(video.currentTime)) position = video.currentTime;
        video.pause();
        video.removeAttribute('src');
        video.load();
      }
      return;
    }
    if (video.getAttribute('src') !== clipUrl) {
      video.src = clipUrl;
      video.play().catch(() => {});
    }
  }

  video.addEventListener('loadedmetadata', () => {
    if (position > 0 && position < video.duration) video.currentTime = position;
  });
  video.addEventListener('error', () => {
    if (!video.hasAttribute('src')) return;
    mediaError = true;
    choose.textContent = 'Choose another clip';
    sync();
  });
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
          if (result.url !== clipUrl || body.choose || body.clear) {
            video.removeAttribute('src');
            video.load();
            position = 0;
            mediaError = false;
          }
          clipUrl = result.url;
          choose.textContent = result.clip ? 'Change gameplay clip' : 'Add gameplay clip';
          choose.title = result.clip || 'Choose a local MP4 or WebM recording';
          clear.hidden = !result.clip;
          sync();
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
