# Relevés de cotes Stake du 8 septembre 2026

`stake-observed-20260908.json` contient des observations réellement lues dans le
navigateur, sans connexion à un compte, le 8 septembre 2026 autour de 15:39 UTC.
Ce fichier figé est une preuve de lecture et une fixture de rejeu, pas un flux live.

Pages sources :

- [GIANTX – Natus Vincere](https://stake.bet/fr/sports/league-of-legends/international-1/lec-2026-summer-playoffs-t3/822193-giantx-natus-vincere),
  affiché le 11 septembre à 17:00 : vainqueur de série 2,05 / 1,78 ;
  vainqueur des maps 1 à 5, chacune 1,95 / 1,82.
- [Calendrier LoL](https://stake.bet/fr/sports/league-of-legends) :
  Team Vitality – Movistar KOI, affiché le 12 septembre à 17:00, 1,78 / 2,05.
  Le lien visible identifie l'événement `822195-team-vitality-movistar-koi`.

Les horaires affichés sont interprétés dans le fuseau de la session Europe/Paris.
L'horodatage du relevé est celui de notre observation, pas celui d'une mise à jour
du fournisseur. `timestamp_reliable=false` conserve cette distinction et force
les snapshots à rester informatifs. La valeur `best_of` reste inconnue.
Les identifiants `observed:*` sont nos clés locales de normalisation : ils ne sont
pas présentés comme des identifiants internes de l'API Stake.

Les règles de règlement ne sont pas certifiées : les trois politiques valent
`review`. Aucun handicap, total ou score exact n'est converti en marché vainqueur.
Seuls les marchés réellement lus et déjà représentables par le contrat sont inclus.
Les dates de la fixture ne doivent jamais être déplacées pour simuler du live.

Les accès HTTP directs au calendrier ont renvoyé 403 lors de cette vérification.
Les domaines de documentation et de données de l'API officielle ont renvoyé une
erreur de validation du nom dans le certificat TLS. La consultation du navigateur
n'établit donc pas qu'un flux automatisé fonctionne.

## Relevé DOM pour le scraper

`stake-dom-20260908.json` est une transcription compacte des résultats d’extraction
du DOM public GIANTX–Natus Vincere obtenus le 8 septembre 2026. Les six onglets ont
été consultés. Les handicaps ont été dépliés et les scores exacts affichés avec
« Tout » : 55 blocs, 154 sélections en comptant les vainqueurs présents dans deux
onglets. Le navigateur a confirmé l’égalité des valeurs des objectifs entre les
cinq cartes ; leurs libellés portent bien le numéro de carte correspondant.

Le fichier reproduit les champs du DOM nécessaires au parseur, sans prétendre
contenir l’heure de mise à jour de Stake. `REPLAY_TIME` dans les tests est une
horloge de simulation du rejeu et ne transforme jamais ce relevé en flux live.
`stake-page-replay.html` reproduit les conteneurs utiles et simule l’hydratation et
les changements d’onglet retardés pour tester Chromium sans dépendre du réseau.
Aucun de ces fichiers n’est utilisé par le collecteur en production.
