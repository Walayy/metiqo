# Fluidité, survols et phases de cote — 24 septembre 2026

## Mesure

Navigateur Codex Chromium, Windows, viewport 1440 × 900, Vite en mode API, React StrictMode. Données PostgreSQL réelles du 24 septembre : WSCI, 8 rencontres, 1 direct ; détail FUEGO–T1 Academy (10 joueurs). Fenêtres de 12 secondes, même instrumentation React Profiler + `requestAnimationFrame` + `PerformanceObserver(longtask)` avant et après. La liste est dépliée puis défilée d’une page ; le second scénario inclut l’ouverture du détail. Le [code de sonde](probe.ts.txt) est archivé mais retiré du frontend. Pour reproduire en développement : l’importer temporairement dans `main.tsx`, envelopper `AppRouter` dans un Profiler avec `onRender={auditRender}`, puis utiliser « Mesurer 12 s ». Ne pas livrer cette instrumentation.

| Scénario | Commits avant → après | Temps React cumulé | Frames > 33,4 ms | Longues tâches > 50 ms |
| --- | --- | --- | --- | --- |
| Liste dépliée, défilement | 12 → 3 | 385 → 78 ms (−80 %) | 2 → 2 | 0 → 0 |
| Ouverture du détail | 19 → 7 | 734 → 122 ms (−83 %) | 16 → 2 | 5 → 1 |

Le percentile 95 des intervalles rAF reste à environ **4,3 ms** dans les quatre captures, sur ce poste à fréquence élevée. Les longueurs cumulées des longues tâches du détail passent de 413 à 109 ms. Une première mesure intermédiaire de liste (75 ms) n’est pas retenue : le code était encore en cours de formatage. La capture finale ci-dessus est prise sans édition frontend pendant la fenêtre.

Ces échantillons courts mesurent le travail de React et du thread principal dans ce navigateur ; ils ne prouvent ni une absence universelle de ralentissements ni un taux d’images GPU garanti. Les données live et le polling continuent pendant les mesures. Le gain annoncé concerne la charge mesurée ; aucun « 100 % fluide sur tous les appareils » n’est déduit.

## Corrections

1. La page Matchs ne reçoit plus un nouvel état global chaque seconde. Une horloge partagée publie seulement les libellés temporels dont le texte change (`useSyncExternalStore`). Les tables, logos, infobulles et composants de détail restent stables. Les secondes restent affichées pour les débuts proches ; les âges relatifs et le passage de minuit continuent de s’actualiser. Les ticks sont suspendus quand le document est masqué.
2. La continuité de défilement conserve sa compensation lors d’un contenu plus court. Les mutations structurelles sont regroupées par frame ; les changements de texte passent par ResizeObserver uniquement si la taille change. L’observateur conserve ses abonnements au lieu de tous les supprimer/réinstaller à chaque mutation.
3. Un geste de défilement termine les surbrillances transitoires. Il n’exécute plus, pour chacune, une traversée de tous les ancêtres avec styles calculés, rectangles et hit-testing. Les modifications hors écran ne sont toujours pas rejouées au retour.
4. Les points d’état animent un petit halo en `opacity`/`transform`, autour d’un cœur qui reste visible. Aucun timer React n’anime les points. Le mode de mouvements réduits conserve un repère statique.
5. Les survols gardent leur feedback avec des marges internes. Les sources utilisent de petits SVG locaux sans requête externe supplémentaire. Les cotes pré-match/live ont des clés distinctes : une mise à jour live ne remonte pas la ligne historique.

## Vérification fonctionnelle

Les tests PostgreSQL couvrent les deux types de marchés, les équipes reçues en ordre inverse, les phases simultanées, une suspension, une sélection absente au dernier snapshot, les données datées dans le futur, la clôture, l’état bookmaker inconnu et le retrait du lien. Aucun prix n’est repris d’une autre phase pour combler un manque. Les tests frontend valident les phases et interdisent une value actuelle sur une cote historique.

Contrôles navigateur : Matchs et Scripts en clair/sombre, ordinateur 1440 × 900, tablette 768 × 1024 et mobile 390 × 844. Pas de débordement horizontal observé. Vérification des marges de survol, SVG locaux, halos d’état, ouverture exclusive des scripts avec Entrée, accès aux infobulles de cote avec Tab et fermeture avec Escape. Le scénario mock séparé vérifie les deux phases simultanées sur un match et une carte ; sur mobile, les cotes ont une cible de 44 px. Les données API du match live contrôlé ne possédaient qu’un relevé pré-match : aucune cote live n’a été inventée.

`npm run check` : TypeScript, ESLint, 79 tests frontend, build, Ruff, mypy et 183 tests backend hors intégration. Deux tests PostgreSQL ciblés passent dans `metiquo_loltv_test`. Les avertissements préexistants de taille du bundle mock et de dépréciation Starlette/httpx restent présents. Les garde-fous CSS et tests de mouvements réduits sont contrôlés ; la préférence système n’a pas été modifiée dans le navigateur. Pas de mesure sur appareil physique, Safari, ni lecteur d’écran complet.
