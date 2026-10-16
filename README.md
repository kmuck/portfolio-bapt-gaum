# Portfolio de Baptiste Gaumont

Site statique Jekyll, publié par GitHub Pages (Settings → Pages → Deploy from a branch → `main`, dossier `/`)
à chaque push sur `main`, sur `https://kmuck.github.io/portfolio-bapt-gaum/`.

Pour un nom de domaine : le renseigner dans Settings → Pages → Custom domain, puis mettre `baseurl: ""`
dans `_config.yml`.

## Modifier le contenu

- Projets : un fichier par projet dans `_projets/` (titre, catégorie, image de couverture, puis le texte et les images).
  La mise en page reprend celle de Wix : chaque texte ou image est dans un bloc `<div class="bloc" style="…">`,
  rangé en colonnes (`col`) et en rangées (`rangee`). Le texte se modifie directement dans son bloc ; les valeurs
  `--x`, `--w` (décalage et largeur en %) et `--mt` (marge au-dessus) placent le bloc.
- Écrits : un fichier par écrit dans `_ecrits/`.
- À propos : `a-propos.md`. Accueil : `index.html`.
- Images : `assets/img/` (de préférence en WebP, 2400 px de large maximum).

Les fichiers se modifient directement depuis l'interface web de GitHub (crayon « Edit »).

## Aperçu en local

```
bundle install
bundle exec jekyll serve
```

## Import depuis Wix

Le contenu vient de l'ancien site Wix :
1. `scripts/import_wix.py` (lancé à la main par le workflow « Import depuis Wix ») aspire le HTML de chaque page
   dans `import/raw/` et les images, compressées en WebP, dans `assets/img/wix/` ;
2. le workflow « Captures du site Wix » (`scripts/capture_wix.js`) ouvre chaque page Wix dans un navigateur et
   relève la position de chaque élément (`import/captures/boites/`), les styles et le diaporama de l'accueil ; il
   télécharge aussi les recadrages faits dans l'éditeur Wix, les vidéos (`assets/video/wix/`) et le PDF
   (`assets/docs/`). Ses captures d'écran sont disponibles en artefact du workflow ;
3. `scripts/build_from_wix.py` régénère le corps des fichiers `_projets/*.md` à partir du HTML et des positions.
   Attention : il écrase les modifications faites à la main dans ces fichiers.
