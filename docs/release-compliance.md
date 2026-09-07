# Portes de publication

Le MVP livré est destiné à l'usage personnel. `RELEASE_AUDIENCE=personal`,
`OE_COMMERCIAL_GATE=NO-GO`, `RIOT_PRODUCT_GATE=NO-GO` et
`STAKE_PROVIDER_ENABLED=false` sont les valeurs par défaut. Le build personnel
fonctionne avec ces refus. Aucune pièce d'autorisation n'a été obtenue ou validée
dans ce dépôt.

Le démarrage API et worker refuse `RELEASE_AUDIENCE=public` ou `commercial`
si l'une des deux portes reste à `NO-GO`. Avant toute ouverture à des tiers,
exécuter `make release-check AUDIENCE=public` ou `AUDIENCE=commercial` avec
l'environnement du déploiement. Cette commande ne déploie rien et sort avec
un code non nul lorsque la publication est bloquée (1 pour le script, 2 via Make).
`AUDIENCE=personal` contrôle le
prototype privé ; choisir ce mode ne constitue aucune autorisation de le proposer
à des tiers. Le profil Compose de production désigne le durcissement technique,
pas une permission de commercialiser.

## Levée manuelle documentée

Une personne responsable doit obtenir puis examiner les droits écrits, leur
périmètre, leur durée et la juridiction avant de modifier les deux flags. Un
simple `GO` sans preuve est refusé, y compris en mode personnel. Le manifeste
privé désigné par `RELEASE_EVIDENCE_FILE` doit contenir exactement les clés
`OE-COMMERCIAL` et `RIOT-PRODUCT`. Chaque entrée contient :

- `approvedBy` : identité non vide de la personne ayant effectué la revue ;
- `reviewedAt` et `expiresAt` : dates avec fuseau, couvrant l'instant du contrôle ;
- `scope` : liste des audiences explicitement couvertes, `public` et/ou `commercial` ;
- `proof` : fichier de preuve non vide sous le répertoire du manifeste ;
- `sha256` : empreinte SHA-256 exacte de cette pièce.

Le manifeste est limité à 64 Kio, chaque pièce à 10 Mio. Les chemins sortant du
répertoire, documents manquants, empreintes différentes, pièces périmées ou scopes
insuffisants sont refusés. Monter ce répertoire privé en lecture seule dans les
services concernés ; ne pas le committer, l'envoyer au navigateur ou l'archiver
dans les artefacts publics de CI. Redémarrer après changement ou révocation et
rejouer le contrôle à chaque release. L'intégrité technique d'une pièce ne prouve
ni son authenticité juridique ni la suffisance des droits : la décision reste
humaine. Les fixtures des tests sont explicitement synthétiques.

L'API de conformité publie uniquement l'audience, les états des portes et le
refus de publication. L'écran Paramètres les affiche sans pièces confidentielles.
Metiquo ne garantit aucun gain et n'exécute aucun pari réel. Le provider Stake
reste sans transport et non activable dans le code livré, même après levée des
autres portes.

## Sources à revalider avant chaque lancement

Consultation technique du 7 septembre 2026 ; elle ne lève aucune porte.

| Source officielle                                                                      | Constat et preuve attendue avant lancement                                                                                                                                                                                                                                                                                               |
| -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Oracle's Elixir — téléchargements](https://oracleselixir.com/tools/downloads)         | Relecture bloquée par HTTP 403 lors de cette vérification. Le cadre non commercial de la SFG reste à revalider auprès de la source. Obtenir une autorisation écrite couvrant téléchargement répété, stockage, transformation, dérivés, tiers, monétisation et conservation. Aucune permission actuelle n'est déduite de l'accès aux CSV. |
| [Riot — politiques générales](https://developer.riotgames.com/policies/general)        | La page consultée, datée du 29 mai 2025, exclut les fonctionnalités de betting/gambling et exige enregistrement et revue des produits. Obtenir une clarification écrite portant sur ce produit, les données dérivées, les marques et la non-affiliation ; un sponsoring esport ne vaut pas autorisation du produit.                      |
| [Stake — conditions](https://stake.com/policies/terms)                                 | Les sections 14.3–14.4 citent la France parmi les juridictions interdites et interdisent le contournement géographique ; la section 17.3 vise les services automatisés utilisant les informations du site. Le connecteur reste désactivé ; toute évolution doit repasser la porte dédiée.                                                |
| [ANJ — opérateurs agréés](https://www.anj.fr/offre-de-jeu-et-marche/operateurs-agrees) | Stake n'apparaît pas dans la liste consultée. Revalider l'opérateur, le territoire, l'offre et le cadre applicable avec une personne compétente avant tout usage réel. L'accès technique ou une licence étrangère ne remplace pas cette revue.                                                                                           |
| Flux licencié ou import manuel                                                         | Archiver les droits de collecte, conservation et redistribution de chaque fournisseur. L'import manuel valide un contrat de données, jamais une licence d'exploitation.                                                                                                                                                                  |

Les conditions peuvent changer. Aucun message à une source ou un conseiller n'a
été envoyé et aucun accord externe n'est simulé. Le gate personnel peut passer
avec les deux refus ; une release publique ou commerciale reste bloquée.
