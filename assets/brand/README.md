# Identité Metiquo

Pack fourni par le propriétaire du projet le 16 septembre 2026. Le symbole, son dégradé turquoise et son halo sont conservés sans redessin ni recoloration. `original-logo.png` est la source native 1254 × 1254 ; `manifest.json` consigne les exports retenus et leurs SHA-256. Le fichier `pack-readme.txt` conserve la description du pack.

Les fichiers distribués sont dans `apps/web/public/brand/light/` et `dark/`, séparés des logos esport sous `public/logos/` :

- WebP sans perte, 32/64/128/256 px, avec repli PNG et `srcset` pour la densité de pixels.
- ICO multirésolution pour l’onglet ; PNG 180 px pour les icônes Apple. Des replis standards existent aussi à `/favicon.ico` et `/apple-touch-icon.png`.
- Le composant `BrandMark` couvre sidebar, navigation mobile, fil d’Ariane et en-tête des erreurs. Le splash HTML utilise les mêmes exports avant le chargement de React.
- CSS sélectionne le thème déjà appliqué à `html` ; les deux variantes conservent la même géométrie. Le thème explicite de l’application met aussi à jour favicon, icône Apple et couleur du navigateur, dès le script initial.

Le SVG du pack est une enveloppe de PNG d’environ 1,37 Mo, sans tracé vectoriel. Il n’est pas distribué. Aucun JPEG, TIFF, BMP, AVIF ou ICNS superflu n’est chargé par le site. Les couleurs générales du site restent ses tokens existants.

Le pack complet reçu, avec tous les formats, est conservé localement dans `.cache/brand-import/metiquo-logo-pack/` ; il n’est ni versionné ni inclus dans le build. Les sources ci-dessus et les exports réellement utilisés sont versionnables.
