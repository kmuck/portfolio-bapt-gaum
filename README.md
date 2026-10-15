# Portfolio de Baptiste Gaumont

Site statique Jekyll, publié sur GitHub Pages par le workflow `.github/workflows/pages.yml`
à chaque push sur `main`.

## Mise en ligne (une seule fois)

Settings → Pages → Build and deployment → Source : **GitHub Actions**.
Le site est alors servi sur `https://kmuck.github.io/portfolio-bapt-gaum/`.
Pour un nom de domaine, le renseigner dans Settings → Pages → Custom domain.

## Modifier le contenu

- Projets : un fichier par projet dans `_projets/` (titre, catégorie, image de couverture, puis le texte et les images).
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
1. `scripts/import_wix.py` (lancé par `.github/workflows/import-wix.yml`) aspire le HTML de chaque page
   dans `import/raw/` et les images, compressées en WebP, dans `assets/img/wix/` ;
2. `scripts/build_from_wix.py` régénère le corps des fichiers `_projets/*.md` à partir de ce HTML.
