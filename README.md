# Portfolio de Baptiste Gaumont

Site statique Jekyll, publié par GitHub Pages (Settings → Pages → Deploy from branch → `main`, dossier `/`).

- Projets : un fichier par projet dans `_projets/` (titre, catégorie, image de couverture, liste d'images).
- Écrits : un fichier par écrit dans `_ecrits/`.
- À propos : `a-propos.md`.

Les images pointent encore vers les serveurs Wix. Le workflow « Import depuis Wix »
(`.github/workflows/import-wix.yml`) télécharge les textes et images de toutes les pages
dans `import/` et `assets/img/wix/`, pour les rapatrier dans le dépôt avant de résilier Wix.

Aperçu local : `bundle exec jekyll serve` ou `jekyll serve`.
