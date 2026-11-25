const launcherScene = (() => {
  const hero = document.getElementById('home-hero');
  const section = hero.closest('[data-panel="launcher"]');
  const scene = hero.querySelector('.hero-scene');
  const background = scene.querySelector('.hero-background');
  const keypress = scene.querySelector('.hero-keypress');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let active = true, starting = false;

  const side = Math.random() < .5 ? 'ct' : 't';
  scene.dataset.side = side;
  if (side === 't') background.src = 'assets/home/hero-agent-t.webp';
  keypress.src = 'assets/home/hero-keypress-' + side + '.webp';

  function sync() {
    const paused = active || starting || document.hidden || section.classList.contains('hidden') || reduced.matches;
    hero.classList.toggle('scene-paused', paused);
  }

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
  };
})();
