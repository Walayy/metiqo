---
name: interface
description: Construire l'interface française de Metiquo, sobre et responsive, avec deux thèmes, accessibilité complète et parcours Rencontres → Analyse → Simulation.
---

# Interface — décisions de conception

## Parcours et hiérarchie

Lire `AGENTS.md` pour la stack et les règles métier. L'interface ne recalcule jamais une validité plus permissive que le serveur. Elle expose peu d'actions, mais toutes les raisons de refus restent accessibles.

Navigation principale : **Rencontres**, **Simulations** ; **Paramètres** en accès secondaire. L'analyse est une page de rencontre, pas un tableau de bord supplémentaire. En-tête discret : Metiquo, navigation, état synthétique des sources, thème. Aucune donnée de compte Stake/Google, aucun solde, aucun ticket bookmaker.

| Écran cible | Informations et actions |
|---|---|
| `/rencontres` | Compétition, équipes/logos, date/heure, badge de disponibilité, cote Game 1 si qualifiée, état de l'analyse et accès au détail. Recherche équipe/compétition et filtres de disponibilité. |
| `/rencontres/{id}` | Rappel **« Game 1 — avant la série »**, équipes/compétition, deux sélections, cote Stake datée, probabilité Metiquo, cote juste, EV et explication courte. Mise fictive puis « Enregistrer la simulation » dans la même page. |
| `/simulations` | Historique paginé, état, sélection, cote/probabilité figées, mise, résultat, profit. Bilan simple et filtre d'état/période. Renseigner/corriger le résultat Game 1 sans réécrire la décision. |
| `/parametres` | État des sources, dernières tentatives/réussites, fraîcheur du contenu, lancement d'une actualisation, aide au renouvellement local de session et validation des alias en attente. Diagnostics assainis. |

L'installation propose une checklist courte : répertoires sûrs, fichier cookies Google configuré, profil Chrome dédié prêt, première synchronisation, qualification du modèle. Présenter ce qui manque sans inventer de données pour remplir l'écran. Une fois initialisé, consulter une rencontre et enregistrer une simulation ne demande aucune commande technique.

### Rencontres

Trier d'abord chronologiquement, avec filtre « Analysables » et distinction visible des blocages ; ne pas masquer par défaut toutes les ligues secondaires. Ne pas classer uniquement sur une EV élevée qui pourrait amplifier des erreurs. Conserver les filtres lors d'un retour depuis l'analyse.

États de carte distincts : « Analyse disponible », « Aucun avantage suffisant », « Historique insuffisant », « Équipe à identifier », « Cote à actualiser », « Marché à vérifier », « Marché absent », « Suspendu/fermé », « Source indisponible », « Série commencée ». Un catalogue connu ne rend pas une cote ancienne utilisable. Ne pas afficher de badge vert tant que tous les contrôles requis n'ont pas passé.

Une découverte partielle affiche son périmètre incomplet. Un écran vide sain dit « Aucune rencontre dans ce périmètre » ; un chargement en erreur dit « Impossible de consulter les rencontres », avec la dernière information valide datée. Jamais le même message pour ces deux cas.

### Analyse

En premier : identité et portée du pari, puis cote et probabilités. Afficher la cote et son âge près l'une de l'autre, avec l'heure absolue accessible sans dépendre du survol. Trois chiffres principaux suffisent : **probabilité Metiquo**, **cote juste**, **avantage théorique**. L'implicite brute, l'écart en points, la marge des deux sélections et les versions sont dans un détail repliable.

La courte explication provient des variables du modèle et affiche les effectifs/périodes réels. Qualité : phrases descriptives plutôt que jauge de confiance inventée. Afficher « Avantage théorique, non garanti » lorsqu'un écart est présenté. Aucun vocabulaire « pari sûr », « gain assuré » ou animation d'urgence.

Quand la cote expire, conserver les nombres comme **dernière observation**, changer le statut et empêcher la nouvelle simulation. Le serveur reste l'autorité, y compris si l'horloge ou le JavaScript client est erroné. Si un rafraîchissement change la cote, préserver la mise saisie, signaler le changement et demander la confirmation de la comparaison actualisée. Ne jamais réinitialiser tout le formulaire.

L'EV non positive n'est pas une erreur de collecte. L'état « analyse valide, aucun avantage suffisant » reste lisible et peut être simulé conformément au skill données. Un défaut d'identité ou de marché ne peut pas être contourné par le formulaire.

## Système visuel commun

Jinja2 fournit les macros de composants, HTMX les remplacements de fragments ; CSS et JavaScript natifs complètent seulement les comportements nécessaires. Pas de framework de composants concurrent. Ressources servies localement, pas de CDN requis pour lire ses analyses.

Palette initiale de projet, à vérifier en situation sur tous les états :

| Rôle | Thème clair | Thème sombre |
|---|---|---|
| Fond de page | `#F7F8FA` | `#0D1117` |
| Surface principale | `#FFFFFF` | `#151C26` |
| Texte principal | `#17202E` | `#E6EDF3` |
| Texte secondaire | `#596579` | `#A8B3C1` |
| Bordure décorative | `#D5DBE3` | `#2B3544` |
| Bordure de contrôle | `#78869A` | `#63748B` |
| Action/focus | `#0F766E` | `#5EEAD4` |
| Texte sur action pleine | `#FFFFFF` | `#0D1117` |
| Erreur | `#B42318` | `#FDA29B` |
| Attention | `#92400E` | `#FBBF24` |

Utiliser des tokens sémantiques pour surfaces, textes, contrôle, sélection, focus, graphiques, tooltip et notifications, pas une collection de couleurs locales. La couleur ne porte jamais seule un état. Les bordures décoratives ne remplacent pas les bordures/focus nécessaires à l'identification d'un contrôle.

Typographie système locale, texte courant au moins 16 px, interligne autour de 1,5, valeurs chiffrées tabulaires. Échelle d'espacement 4/8/12/16/24/32 px ; rayons cohérents, ombres légères. Une action principale par zone. Les longs noms d'équipes/compétitions doivent rester compréhensibles : retour à la ligne ou détail accessible, jamais information essentielle seulement dans un tooltip.

Composants partagés : bouton/lien, champ et message d'erreur, badge d'état, bloc métrique, ligne/carte rencontre, identité avec logo, bannière source, tableau/liste responsive, état vide, chargement, dialogue de confirmation et notification. Définir états normal, hover, focus-visible, active, selected, disabled, busy, erreur et succès. Un bouton désactivé explique pourquoi dans un texte associé, pas seulement au survol.

## Thèmes, interactions et saisie

Par défaut suivre le thème système ; proposer Système/Clair/Sombre avec choix persistant. Initialiser le thème avant le premier affichage visible, par un petit mécanisme compatible avec la CSP. Revenir proprement au système lorsque le choix est réinitialisé. Aucune page, dialogue, contrôle natif, graphique, infobulle ou scrollbar ne doit rester dans l'autre thème.

Transitions discrètes de 120–180 ms sur couleur/opacité ; pas d'animation de la mise en page ou de compteur pouvant suggérer un gain. Respecter `prefers-reduced-motion` pour les transitions, squelettes de chargement et défilements.

Préserver sélection/copie des noms, probabilités, dates, cotes et identifiants utiles. Pas de `user-select:none` global. Curseur de lien/bouton sur les vraies actions, caret uniquement dans les zones éditables ; les cartes ne doivent pas sembler éditables. Hover uniquement comme enrichissement, jamais comme unique chemin d'accès. La saisie décimale française accepte explicitement la virgule, est normalisée puis validée côté serveur ; erreurs attachées au champ, valeur conservée.

**Scrollbars :** garder les scrollbars natives utilisables, contrastées dans les deux thèmes, sans masquage global ni largeur artificiellement minuscule. Prévenir le déplacement de contenu avec un gutter stable lorsque supporté. Éviter les doubles scrolls et cadres de hauteur fixe ; la page porte le défilement principal. Un dialogue trop haut défile sans cacher les actions ni piéger la navigation. Tester molette, trackpad, clavier et tactile.

## Responsive et accessibilité

Petits écrans : liste de cartes ou lignes réorganisées ; pas de tableau exigeant un scroll horizontal pour atteindre l'action principale. Tablette : colonnes selon l'espace réel. Ordinateur : largeur de lecture maîtrisée et tableau lorsque pertinent. Points de rupture indicatifs 640 et 1024 px, à adapter au contenu, pas au nom d'un appareil. À 320 px CSS et zoom élevé, aucune information essentielle ne se chevauche ou ne disparaît.

Viser WCAG 2.2 AA [U1] : contraste courant d'au moins 4,5:1, texte large 3:1, identification visuelle des contrôles/focus suffisante, navigation clavier complète et focus non masqué. Cibles tactiles de projet d'au moins 44×44 px pour les actions principales. Utiliser titres hiérarchisés, régions, labels, vrais boutons/liens et états ARIA appropriés. Les différences de couleur seules ne communiquent pas l'état d'une source.

Après un remplacement HTMX, garder ou restaurer un focus pertinent et la position de lecture ; annoncer le résultat utile, pas chaque variation de compteur. Un dialogue a un titre accessible, un ordre de tabulation cohérent et rend le focus à son déclencheur. Les graphiques nécessaires (bilan, calibration) possèdent libellés, unités, effectifs et alternative textuelle/tableau ; pas de bibliothèque graphique lourde par défaut.

### SVG, logos et fallbacks

Petite collection d'icônes SVG locales avec licence compatible et style uniforme, `currentColor` pour les icônes monochromes. Icône décorative masquée aux technologies d'assistance ; bouton sans texte doté d'un nom accessible. Ne pas inventer de logotype ressemblant à une équipe réelle.

Associer logos d'équipe/compétition uniquement à une identité canonique certaine, depuis une ressource locale validée ou une image explicitement identifiée dans le contexte source. Conserver provenance et information d'usage disponible ; aucun service de logos ni nouvelle source statistique n'est requis. URL d'image contrôlée, taille/type bornés ; pas de fetch arbitraire depuis l'interface. Ne pas intégrer du SVG externe brut : assainissement strict, aucun script/événement/ressource externe. Un échec d'image ne bloque pas l'analyse.

Fallback commun : monogramme ou pictogramme neutre dans le même conteneur et dimensions réservées. Les noms textuels restent toujours présents. Préserver les couleurs officielles d'un logo ; lui donner au besoin une pastille neutre pour les deux thèmes, sans filtre qui le dénature. Pas de saut de mise en page lorsque l'image arrive.

## Recette visuelle obligatoire

Tester les quatre écrans et les composants dans les deux thèmes : 320/375 px, tablette 768 px, ordinateur 1280/1440 px ; zoom 200 % et vérification de reflow à 400 % ; clavier, focus, tactile, motion réduite, noms longs, logo absent, données vides et panne source. Inclure la scrollbar et les dialogues, pas seulement la capture du premier écran.

Les tests automatiques ne suffisent pas à certifier l'accessibilité [U1]. Consigner ce qui a réellement été inspecté, corriger les débordements et incohérences de composants avant la recette finale. Objectif de réactivité : navigation et lecture locales sans attendre une nouvelle collecte ; chargements techniques présentés séparément avec état clair.

### Référence primaire

[U1] W3C, WCAG 2.2, consulté le 14 septembre 2026 : `https://www.w3.org/TR/WCAG22/`.
