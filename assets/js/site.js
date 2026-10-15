// Diaporamas : carrousel de l'accueil et galeries des pages projets (défilement manuel, comme sur Wix).
(function () {
  function diaporama(racine, options) {
    var diapos = racine.querySelectorAll('.diapo');
    var vignettes = racine.querySelectorAll('.vignette');
    var compteur = racine.querySelector('.compteur');
    var courant = 0;
    var minuteur = null;
    if (diapos.length < 2) {
      racine.querySelectorAll('.fleche').forEach(function (b) { b.hidden = true; });
      return;
    }
    function montrer(i) {
      courant = (i + diapos.length) % diapos.length;
      diapos.forEach(function (d, j) { d.classList.toggle('active', j === courant); });
      vignettes.forEach(function (v, j) { v.classList.toggle('active', j === courant); });
      if (vignettes[courant]) vignettes[courant].scrollIntoView({ block: 'nearest', inline: 'nearest' });
      if (compteur) compteur.textContent = (courant + 1) + '/' + diapos.length;
    }
    function relancer() {
      if (!options.auto) return;
      clearInterval(minuteur);
      minuteur = setInterval(function () { montrer(courant + 1); }, options.auto);
    }
    racine.querySelector('.precedent').addEventListener('click', function () { montrer(courant - 1); relancer(); });
    racine.querySelector('.suivant').addEventListener('click', function () { montrer(courant + 1); relancer(); });
    vignettes.forEach(function (v, j) { v.addEventListener('click', function () { montrer(j); relancer(); }); });
    var departX = null;
    racine.addEventListener('touchstart', function (e) { departX = e.touches[0].clientX; }, { passive: true });
    racine.addEventListener('touchend', function (e) {
      if (departX === null) return;
      var dx = e.changedTouches[0].clientX - departX;
      if (Math.abs(dx) > 40) { montrer(courant + (dx < 0 ? 1 : -1)); relancer(); }
      departX = null;
    });
    montrer(0);
    relancer();
  }
  document.querySelectorAll('[data-carrousel]').forEach(function (r) { diaporama(r, {}); });
  document.querySelectorAll('[data-diaporama]').forEach(function (r) { diaporama(r, {}); });
})();
