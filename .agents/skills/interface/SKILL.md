---
name: interface
description: "Concevoir les trois vues du parcours Metiquo, avec composants sobres, thèmes complets, logos vérifiés et interactions accessibles sur tous les écrans."
---

# Interface et expérience

## Direction et périmètre visuel

Interface française de lecture et de simulation, pas un casino ni un terminal de trading. Mettre en avant l'événement exact, la fraîcheur et les limites ; pas de promesse de gains, compte à rebours incitatif, confettis, son, classement de « paris sûrs » ou couleur positive destinée à masquer un manque de données.

Deux destinations principales dans la navigation : **Rencontres** et **Simulations**. Le détail d'analyse est la troisième vue, ouverte depuis une rencontre. L'état des sources est un panneau secondaire accessible par « Données », pas une console d'administration. Chaque élément correspond à consulter, comprendre, simuler ou diagnostiquer une indisponibilité.

Typographie système, taille de texte courant 16 px, interligne proche de 1,5 ; chiffres tabulaires pour cotes, dates et mises. Échelle d'espacement 4/8/12/16/24/32/48 px. Largeur de lecture maximale autour de 1 120 px, marges latérales 16 px sur petit écran et 24–32 px ensuite. Rayons cohérents, ombres discrètes, pas de panneaux imbriqués sans fonction.

## Les trois vues

### Rencontres

En-tête avec nom Metiquo, navigation, état des données et thème. Titre « Rencontres » ; précision toujours visible « Partie 1 · Avant la série · LEC / LCK ». Filtre de ligue et filtre d'état seulement ; inutile d'ajouter recherche avancée ou calendrier complexe pour ce petit périmètre.

Liste chronologique des rencontres suivies : logos et noms complets des deux équipes, ligue, date/heure, état, dernière observation des cotes. La sélection éventuellement intéressante et son EV peuvent apparaître sur une seconde ligne ; l'intitulé de la partie reste prioritaire. Une seule action explicite « Voir l'analyse » ; ne pas rendre toute la ligne cliquable au détriment de la sélection de texte.

Distinguer **aucune rencontre prévue dans le périmètre**, **aucune rencontre analysable**, **aucun avantage suffisant** et **collecte indisponible**. Ne pas afficher un succès vide si le collecteur n'a pas répondu. Les rencontres hors capacité de suivi sont étiquetées comme telles, pas présentées comme fraîchement analysées. Un ancien relevé affiche son âge, sans badge positif.

Préserver filtres, position et focus au retour depuis l'analyse. Lors d'un rafraîchissement, ne pas réordonner brutalement la liste sous le pointeur ; annoncer discrètement les changements et conserver une clé d'identité stable par rencontre.

### Analyse d'une rencontre

Retour vers les rencontres ; noms et logos ; ligue ; date avec fuseau ; libellé très visible « **Vainqueur de la partie 1** ». Ne jamais abréger ce titre en « vainqueur » seul. Afficher état du marché et âge de la cote près du prix.

Présenter les deux sélections dans un composant commun : cote Stake.bet, probabilité du modèle, cote juste, écart de probabilité en points et EV en pourcentage de mise. Les unités sont explicites, les arrondis cohérents et les définitions accessibles au clavier/toucher, pas seulement au survol. La sélection n'est pas présumée être l'équipe favorite.

Sous les chiffres : explication courte à partir du vrai modèle, date des données, effectifs historiques et limite concernant les compositions futures. Un accordéon « Comment cette estimation est obtenue » contient formule simplifiée, version, période de test, métriques, seuils et test de sensibilité. Un petit tableau de calibration suffit ; aucune bibliothèque graphique n'est nécessaire.

Zone « Simulation » : sélection, mise fictive, valeurs qui seront enregistrées et bouton « Enregistrer une simulation ». Badge expérimental conservé quand approprié. Une analyse sans avantage peut être simulée ; une cote périmée ou un événement ambigu non. L'indisponibilité affiche son motif près de l'action, sans tooltip indispensable sur un bouton désactivé.

Si une valeur change pendant la saisie, garder la mise et demander confirmation des nouvelles valeurs. Ne pas faire passer une ancienne cote pour le prix actuellement disponible. Après succès, message discret avec accès à la simulation enregistrée, sans notification redondante.

### Simulations

Résumé de trois informations : profit fictif réalisé, rendement réalisé et nombre de simulations en attente. Puis historique : date, équipes, partie, sélection, cote enregistrée, probabilité d'origine, mise, état et profit. Filtre d'état simple ; mention visible du périmètre expérimental/qualifié, sans assimiler les deux.

Sur petit écran, transformer chaque ligne en fiche lisible, sans perdre les colonnes essentielles. L'ouverture d'une fiche donne la photographie d'origine et la modification du résultat. Dialog limité : en attente, gagné, perdu, annulé ; confirmer une correction et rappeler que le résultat est déclaré manuellement.

État vide : expliquer qu'une simulation se crée depuis une analyse, avec action vers Rencontres. Sans résultat réglé, afficher « Rendement non calculable », pas 0 % comme mesure de performance. Une perte fictive n'entraîne aucun appel à augmenter la mise.

### Panneau Données

Deux blocs, Stake.bet et Oracle’s Elixir : état compréhensible, dernière tentative, dernier succès, prochaine reprise ; pour Oracle, dernière partie présente et dernier import modifiant le contenu. Valeur absente = « Jamais réussi » ou « Non disponible », pas une date artificielle.

En cas d'erreur, résumé utilisateur et code diagnostic copiable sans secret. Bouton de reprise seulement après la pause imposée ; il rejoint la file existante, sans lancer une collecte parallèle. L'ouverture du panneau ne provoque aucun appel externe. Une maintenance de mapping/schéma est signalée ici ; pas de tableau de bord supplémentaire.

## Composants et états

Composants restreints : coquille de navigation, rencontre, bloc de métrique, badge d'état, bouton/lien, champ de mise, select, message inline, accordéon, dialogue et ligne/fiche de simulation. Réutiliser le même composant sur les trois vues, pas trois variantes stylistiques.

Pour chaque contrôle, traiter : normal, hover sur périphérique adapté, focus-visible, activation, sélection si pertinente, désactivation motivée, chargement et erreur. Ne pas simuler un bouton avec un élément neutre. Conserver la taille lors du chargement ; une erreur préserve la saisie et se rattache au champ par son identifiant accessible.

Le dialogue porte un nom accessible, place le focus utile, limite le focus à son contenu pendant l'ouverture, se ferme par Échap lorsque sûr et restaure le focus déclencheur. Un clic externe ne doit pas perdre silencieusement une correction commencée. Les accordéons restent utilisables au clavier et exposent leur état.

Les messages de réussite utilisent une zone de statut polie. Une erreur bloquante est annoncée une fois et reste consultable. Ni toast récurrent toutes les minutes, ni annonce vocale de chaque seconde écoulée. Une actualisation de données ne vole jamais le focus.

## Thèmes clair, sombre et système

Choix initial **Système** ; choix manuel Clair/Sombre/Système persistant. Appliquer le choix avant le premier affichage du contenu, avec un très petit script local de thème et une politique CSP compatible ; fallback CSS sur la préférence système. Aucun flash clair en mode sombre. Si le stockage local est indisponible, conserver un thème fonctionnel sans erreur bloquante.

Palette proposée, à vérifier sur les composants réellement rendus :

| Token sémantique | Clair | Sombre |
|---|---|---|
| Fond | `#F6F7FB` | `#0F1117` |
| Surface | `#FFFFFF` | `#171B24` |
| Texte principal | `#111827` | `#F1F5F9` |
| Texte secondaire | `#475569` | `#A8B3C4` |
| Bordure décorative | `#D8DEE9` | `#343E4E` |
| Bordure de contrôle | `#64748B` | `#8190A5` |
| Accent / focus | `#4338CA` | `#A5B4FC` |
| Texte sur bouton accent | `#FFFFFF` | `#111827` |
| Succès / avantage | `#166534` | `#86EFAC` |
| Avertissement | `#92400E` | `#FCD34D` |
| Erreur | `#B91C1C` | `#FDA4AF` |

Contrôle arithmétique effectué pendant la préparation : sur les surfaces indiquées, le plus faible contraste des textes du tableau, hors accent, est de 6,47:1 en clair et 8,13:1 en sombre ; celui des bordures de contrôle est respectivement 4,76:1 et 5,31:1. Ce calcul de palette ne constitue pas une validation des écrans, qui n'existent pas encore.

La bordure décorative n'est pas suffisante pour délimiter à elle seule un contrôle. Prévoir aussi surfaces sélectionnées, survol, champs invalides, placeholders, sélection de texte, caret, overlay, skeleton et scrollbar pour les deux thèmes. Aucun contrôle natif blanc oublié dans le thème sombre ; utiliser `color-scheme`. Une information n'est jamais donnée seulement par le vert/rouge.

Objectifs vérifiables : WCAG 2.2 AA ; contraste texte normal ≥4,5:1, grand texte ≥3:1, informations non textuelles indispensables ≥3:1. Tester les combinaisons et états finaux, pas seulement les couleurs isolées. Référence officielle consultée le **14 septembre 2026** : [WCAG 2.2, référence rapide W3C](https://www.w3.org/WAI/WCAG22/quickref/).

## Logos et icônes SVG

Placer le logo de ligue à côté de son nom, les logos des équipes près de leur identité, et quelques icônes fonctionnelles dans la navigation, le thème, les états de données et les actions. Ne pas ajouter une icône à chaque nombre ou répéter le même symbole sans rôle.

Pour les icônes UI, conserver localement un petit sous-ensemble SVG Lucide, avec les mentions exigées : [licence officielle Lucide](https://lucide.dev/license), consultée le **14 septembre 2026**. Aucun paquet npm, CDN runtime ou police d'icônes n'est nécessaire. Enregistrer la provenance et l'empreinte des fichiers acquis lors de l'implémentation ; aucune version d'asset non téléchargé n'est inventée dans cette archive.

Pour LEC, LCK et les équipes activées : récupérer les **logos officiels dont l'usage est permis**, depuis les détenteurs ou leurs ressources de marque identifiées. Leur acquisition ponctuelle est une gestion d'assets, pas une nouvelle source de statistiques. Consigner une seule fois provenance, date et conditions ; ne pas scraper en permanence un service tiers de logos.

Associer les assets aux identifiants canoniques vérifiés. Un changement de nom ne justifie pas un mauvais logo. Si un asset manque ou échoue, monogramme neutre et nom complet restent visibles. Prévoir les variantes de marque autorisées pour clair/sombre ou une petite surface protectrice neutre ; **ne pas inverser/recolorer arbitrairement les logos officiels**. Les icônes UI utilisent la couleur du texte ; les marques conservent leurs couleurs.

SVG contrôlé localement : retirer scripts, gestionnaires d'événements, `foreignObject`, liens externes et ressources distantes ; ne jamais injecter du SVG brut fourni par une source réseau. Fixer dimensions et zone d'affichage pour éviter les décalages. Une icône décorative est ignorée par le lecteur d'écran ; une action uniquement iconique a un nom accessible. Le logo à côté du nom peut avoir un texte alternatif vide pour éviter la répétition.

## Mouvement, sélection et adaptation

Transitions de couleur/opacité brèves, environ 120–180 ms, réservées aux changements utiles. Ne pas animer en continu les prix ou les gains. Réserver l'espace des messages et chargements. Respecter `prefers-reduced-motion` : désactiver les animations non essentielles et les glissements. Le contenu important reste immédiatement disponible.

Permettre la sélection et la copie des équipes, cotes, probabilités, dates, explications et identifiants. `user-select: none` limité aux éléments décoratifs et contrôles dont cela améliore réellement l'usage, jamais au document entier. Le caret de saisie apparaît dans les champs éditables ; **ne pas casser la navigation au caret du navigateur ni imposer un caret invisible global**. Curseur pointeur sur les actions, texte sur le contenu sélectionnable, pas de fausse poignée de déplacement.

Conserver une **scrollbar visible et utilisable**, cohérente avec le thème sans la rendre trop fine. Pas de `overflow: hidden` global permanent, pas de masquage de scrollbar pour embellir une capture. Éviter les doubles scrolls imbriqués ; prévoir l'espace de scrollbar pour limiter les déplacements à l'ouverture d'un dialogue. Vérifier aussi ses coins, track/thumb et contrastes dans les deux thèmes.

Faire tenir le parcours à 320 px de largeur CSS, à 200 % de zoom et sans chevauchement sous clavier mobile. Cibles tactiles principales d'au moins 44×44 px ; pas d'interaction indispensable limitée au hover. Les barres collantes ne masquent ni focus ni contenu. Sur ordinateur, les tableaux peuvent rester denses mais lisibles ; sur mobile, préserver la hiérarchie plutôt que réduire les textes.

## Recette visuelle et fonctionnelle

Parcourir **les trois vues et le panneau Données**, aux largeurs 360, 768 et 1 440 px, dans les deux thèmes ; vérifier aussi 320 px et zoom 200 % pour le reflow. Exécuter le parcours sans souris : filtre → analyse → choix → mise → enregistrement → résultat → retour. Refaire au toucher ou en émulation tactile.

Inclure dans les fixtures : nom d'équipe très long, logo absent, date changée, aucune rencontre, collecte bloquée, HTML source invalide, cote périmée pendant la saisie, modèle expérimental, EV négative, chargement, erreur de sauvegarde et dialogue de correction. Sur chacun : aucun contenu coupé, aucun focus perdu, aucune perte de saisie, aucun état communiqué par la couleur seule.

Contrôler enfin la préférence de mouvement réduit, le thème dès la première image, les scrollbars, la sélection/copier-coller et les champs clavier français (virgule décimale). Une capture esthétique de l'état normal ne vaut pas validation du parcours et de tous ses états.
