# Audit de v1-ajout-live — 21 septembre 2026

Comparaison des deux commits de la branche (`038af53`, `8b4a185`) avec `v1` (`4c216b4`). L’arbre de travail était propre au début de l’audit. Les corrections sont locales, non publiées. Aucun effacement des données de la stack de travail ; collectes et tests d’écriture dans une base PostgreSQL isolée.

## Défauts confirmés et corrections

| Domaine | Défaut observé | Correction |
| --- | --- | --- |
| Périmètre | Le DOM des journées LoL contenait une recommandation Dota 2, effectivement importée sous PGL. | Vérification de la catégorie de la fiche ; exclusion des anciennes données hors LoL à la lecture, preuves conservées. |
| Contrat | Un ban Cassiopeia répété produisait 11 bans et faisait échouer la validation Zod de toute la liste. | Déduplication par équipe/champion, y compris pour les snapshots historiques. |
| Fraîcheur | Les événements du cache étaient republiés avec un nouveau `last_seen_at`, même pendant un blocage. | Seules les fiches effectivement relues sont publiées ; les blocages restent visibles. |
| Historique | Une unicité globale `(match_id, sha256)` empêchait d’enregistrer le retour A → B → A. | Migration `0008`, déduplication seulement consécutive, snapshots toujours immuables. |
| Résultats | Un historique Oracle 1–0 ou 2–0 pouvait transformer un BO5 en BO1 ou BO3. | Validation du nombre de victoires contre le format sourcé ; rejet des anciennes clôtures sans preuve. |
| Identités | Deux candidats exacts pouvaient être départagés arbitrairement ; le qualificatif Academy n’était protégé que dans un sens. | Rejet des ex æquo et protection symétrique des équipes secondaires. Pas de rapprochement entre compétitions différentes. |
| Oracle | Des rematches pouvaient partager les mêmes cartes ; les doublons de numéro étaient choisis par identifiant lexical. | Attribution d’une carte à une seule rencontre non ambiguë, contrôle de compétition et rejet des numéros concurrents. |
| Oracle | Une statistique manquante pouvait annuler la projection de tous les matchs ; les dates sans offset étaient supposées UTC. | Champs facultatifs conservés à `null`, carte incomplète isolée, fuseau explicite vérifié pour les dates naïves. |
| SofaScore | Le nombre de kills pouvait servir de vainqueur ; home/away était converti arbitrairement en bleu/rouge. | Aucune victoire déduite des kills ; côté inconnu explicitement conservé. |
| API | Les cartes partiellement capturées pouvaient faire rejeter un résultat terminé ou afficher un score incomplet. | Score de série sourcé prioritaire et conservation par numéro des cartes compatibles. |
| Catalogue | La rétention des anciennes identités annulait de fait la protection contre une baisse de couverture Riot. | Contrôle avant rétention, avec comptage des identités réellement redécouvertes. |
| Frontend | Le catalogue en cache infini pouvait manquer une nouvelle identité découverte pendant le polling. | Relecture ciblée du catalogue avant d’évaluer une référence manquante. |
| Interface | Les cartes non jouées d’une série terminée étaient « À venir » ; les totaux d’un roster vide affichaient zéro. | Libellés « Non jouée » / « Non publiée », statistiques inconnues marquées par un tiret. |
| Interface | Les deux colonnes de statistiques étaient trop comprimées à 768 px. | Passage à une colonne sur tablette ; clair/sombre conservés. |
| Assets | Le domaine réel importait le manifeste depuis les fixtures ; une synchronisation pouvait remplacer des portraits avant publication du manifeste. | Manifeste dans `domain/data`, chemins d’images versionnés, remplacement atomique par fichier, contrôles des identifiants et PNG, timeout réseau. |
| Tests | Le test PostgreSQL du scheduler comptait encore trois scripts et pouvait appeler le vrai collecteur SofaScore. | Quatre scripts vérifiés, collecte externe remplacée dans ce test. |

## Vérifications effectuées

- `npm run check` : TypeScript strict, ESLint, **58 tests frontend**, build mock, Ruff, format Python, mypy, **88 tests backend unitaires**, tous réussis.
- `uv run --frozen pytest` avec `TEST_DATABASE_URL` vers PostgreSQL 18 isolé : **129 tests réussis**, dont **41 tests d’intégration**. Les rôles SQL API/worker sont présents et leurs permissions sont vérifiées. Aucune suite d’intégration ignorée dans cet appel. La migration est également exercée sur un ancien BO5 réduit à tort en BO1, sans modification du snapshot source.
- `npm run build:api` réussi. Vérification de syntaxe et exécution réelle du script Data Dragon dans un dossier isolé : **173 portraits**, version **16.18.1**.
- Collecte réelle LoL Esports : **37 pages**, **36 ligues**, **265 équipes**, **299 URLs de logos**, publication réussie en base isolée le 21 septembre à 08:33 UTC.
- Collecte réelle Oracle `--latest` : archive de **23 196 970 octets**, **11 016 lignes de 2014** et **106 896 lignes de 2026**, soit **117 912 lignes**, import atomique réussi à 08:40 UTC. 2014 est le fichier compagnon de l’export groupé, pas une année codée en dur.
- Réponses de l’API corrigée contrôlées avec le schéma Zod réel : **74 rencontres LoL** de la base locale acceptées au moment du test. La base métier a été consultée sans modification par l’API de vérification.
- Navigateur : calendrier et centre du match, thèmes clair/sombre, desktop 1440 × 1000, tablette 768 × 1024, mobile 390 × 844 ; ouverture au clavier, flèches entre cartes, focus piégé, Escape et retour au bouton de rencontre. Défilement interne, titres fixes, absence de débordement de page aux tailles mesurées et portraits chargés. Les règles de réduction des mouvements ont aussi été relues dans le CSS.
- Contrôle complémentaire en mode mock : calendrier, série en direct, carte live sélectionnée, côtés bleu/rouge connus et cartes futures désactivées. Aucune erreur ou alerte dans la console de ce parcours.

## Limites et exploitation

- **SofaScore a répondu HTTP 403** lors de l’essai réel isolé. L’échec est correctement enregistré et n’altère pas les dernières données valides. Il n’est donc pas possible de certifier la disponibilité actuelle de cette source. Les parseurs et leur intégration ont été vérifiés avec des cas de régression et les observations déjà stockées ; aucun contournement de blocage n’a été ajouté.
- **Fuseau Oracle sans offset non vérifié** : `METIQUO_ORACLE_DATE_TIMEZONE` reste vide par défaut. Les CSV sont importés intégralement ; le rapprochement temporel de ces lignes attend une convention source confirmée. Les tests vérifient les timestamps explicites et les projections avec format indépendant. Ne pas définir UTC par commodité.
- Appliquer **`alembic upgrade head` avant le worker corrigé**. La stack Docker le fait via le service `migrate` lors du prochain démarrage construit. La migration `0008` a été vérifiée sur la base isolée ; elle n’a pas été appliquée à la base de travail pendant cet audit. Son downgrade refuse de supprimer des observations répétées pour rétablir l’ancienne contrainte.
- Le scheduler exécute ses jobs en série : une grosse collecte Oracle peut retarder un relevé live. Le cron SofaScore par défaut est **une minute**, mais ce n’est pas une garantie de fraîcheur à la minute. Les limites par lot et les refus de la source restent déterminants.
- Les deux avertissements de dépréciation Starlette/httpx/AnyIO et l’avertissement de taille du chunk MSW préexistants subsistent. Aucun changement de dépendance sans rapport avec les défauts vérifiés.
- Pas de certification d’exhaustivité des ligues, ni de vérification sur téléphone physique ou lecteur d’écran complet. Le scraping dépend toujours de la structure des pages externes.
