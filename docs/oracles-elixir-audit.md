# Audit Oracle’s Elixir — accès et téléchargement

Date : **15 septembre 2026**. Première série d’essais HTTP : 16:26–16:31 UTC. Seconde série : exports ZIP générés à 16:43 et 16:46 UTC, validation complète terminée à **16:49:31 UTC** (18:49:31 à Paris). Audit ponctuel, sans intégration au produit.

## Verdict

**Suite de l’audit :** une demande ultérieure a autorisé l’implémentation permanente du backend et du worker. Elle est documentée dans [backend.md](backend.md) et ses vérifications dans [verification.md](verification.md). Le présent rapport conserve les résultats de l’audit initial et ne décrit pas à lui seul l’état actuel du dépôt.

**Une méthode a permis de récupérer et valider les 13 fichiers sur 13 malgré le blocage des téléchargements individuels : le téléchargement groupé en ZIP depuis le dossier public Google Drive.** Elle a fonctionné sans compte Google connecté, sans clé API et sans cookies de connexion personnels.

Deux exports distincts ont réussi : une archive contenant 2014 et 2026, puis une autre contenant les 13 saisons. Le lien individuel 2026 renvoyait toujours « Quota exceeded » après la réussite du premier ZIP. Les fichiers 2014 et 2026 des deux exports ont exactement les mêmes SHA-256. La première conclusion, limitée aux liens individuels et aux fragments, est donc remplacée par ce résultat complet.

Résultat : **848 628 282 octets de CSV**, **1 223 472 lignes de données**, 165 colonnes par fichier et aucune ligne CSV de longueur incohérente. Cela valide la récupération de **100 % des fichiers visibles dans ce dossier lors du test**. Deux exports réussis ne constituent pas une garantie de disponibilité illimitée future du service Google.

## Méthode validée : demander un export ZIP groupé

### Procédure reproductible

1. Ouvrir le [dossier public OE Public Match Data](https://drive.google.com/drive/folders/1gLSw0RLjBbtaNy0dgnGQDAZOHIgCe-HH) dans un navigateur. Aucun compte connecté n’a été nécessaire pendant ces essais.
2. Attendre le chargement de la liste. Sélectionner au moins deux fichiers avec Ctrl+clic. Pour tout récupérer : cliquer une ligne, puis Ctrl+A lorsque le focus est dans la liste des fichiers.
3. Faire un clic droit sur la sélection, puis choisir **Télécharger** dans le menu contextuel. Le bouton d’un fichier isolé passe par le téléchargement individuel qui était bloqué.
4. Attendre la fin de **« Compression de … fichiers au format ZIP… »**. La génération a pris de l’ordre de quelques minutes pour l’ensemble du dossier ; ce n’est pas un engagement de délai.
5. Récupérer l’archive produite. Le navigateur reçoit une URL sous **`https://storage.googleapis.com/drive-bulk-export-anonymous/`**. Lors de l’audit, cette URL est apparue dans un lien à l’intérieur d’une iframe de téléchargement. Elle a ensuite été téléchargée par un client HTTP indépendant, sans cookies de connexion.
6. Vérifier l’archive et les CSV avant de les publier dans le stockage de l’application.

Pour ne récupérer que 2026, la combinaison **2026 + 2014** a été validée : le ZIP fait **22 748 340 octets**, dont environ 2 Mo compressés pour 2014. Il suffit de conserver le CSV 2026 lors du traitement. Un futur collecteur peut sélectionner le plus petit CSV compagnon disponible plutôt que supposer l’existence éternelle du fichier 2014.

Le téléchargement de plusieurs fichiers par Ctrl+clic et le menu contextuel est un parcours [documenté par Google](https://support.google.com/drive/answer/2423534?co=GENIE.Platform%3DDesktop&hl=en). **La capacité de ce parcours à réussir pendant le blocage individuel est un résultat expérimental de cet audit**, pas une garantie annoncée dans cette documentation.

### Ce qui est automatisable

Le parcours ci-dessus a été exécuté par automatisation du navigateur : sélection, menu contextuel, génération et lecture du lien produit. La récupération de l’archive et sa validation ont été effectuées par des commandes et scripts temporaires. Aucun collecteur autonome de production n’est conservé dans le dépôt.

Le futur collecteur peut séparer deux opérations : un navigateur génère l’export et relève le lien produit ; un client HTTP télécharge ce lien et vérifie l’archive. Il doit découvrir le contenu du dossier, vérifier la sélection et obtenir un nouveau lien pour chaque export. **Ne pas figer l’URL d’archive de l’audit** : elle identifie un export particulier, pas la dernière version des CSV. Sa durée de disponibilité n’a pas été testée ; le cache HTTP annoncé ne constitue pas une garantie de conservation.

Ce chemin de transfert observé diffère de celui des liens individuels : ceux-ci aboutissent à `drive.usercontent.google.com/download`, tandis que l’archive est servie depuis Google Cloud Storage. Cette distinction explique le choix de méthode ; l’implémentation interne de ses quotas n’est pas connue.

### Preuves des deux exports

| Export                             | Archive reçue                | Résultat                                                               |
| ---------------------------------- | ---------------------------- | ---------------------------------------------------------------------- |
| 2014 + 2026, généré à 16:43:55 UTC | 22 748 340 octets, HTTP 200  | 2 fichiers intégraux ; contrôle CRC du ZIP et lecture complète des CSV |
| 2014–2026, généré à 16:46:18 UTC   | 233 672 676 octets, HTTP 200 | 13 fichiers intégraux ; aucune année absente ou en double              |

Les MD5 calculés sur les archives correspondent aux en-têtes `x-goog-hash` fournis par Google : `g6T+8l4bjRGlY3+P5IP6AQ==` pour le premier ZIP, `7sp9dxlyhHNSkpIgaUqpxA==` pour le second, au format Base64. Chaque entrée du ZIP a aussi été lue entièrement, ce qui vérifie son CRC.

| CSV  | Octets      | Lignes de données | Identifiants de parties distincts |
| ---- | ----------- | ----------------- | --------------------------------- |
| 2014 | 8 178 893   | 11 016            | 918                               |
| 2015 | 16 098 660  | 21 780            | 1 815                             |
| 2016 | 35 260 255  | 50 568            | 4 214                             |
| 2017 | 47 260 594  | 66 060            | 5 505                             |
| 2018 | 57 942 430  | 80 832            | 6 736                             |
| 2019 | 73 144 845  | 97 500            | 8 125                             |
| 2020 | 89 069 354  | 116 964           | 9 747                             |
| 2021 | 109 765 213 | 147 624           | 12 302                            |
| 2022 | 97 641 612  | 150 348           | 12 529                            |
| 2023 | 85 898 775  | 133 272           | 11 106                            |
| 2024 | 79 127 713  | 122 340           | 10 195                            |
| 2025 | 79 169 638  | 120 492           | 10 041                            |
| 2026 | 70 070 300  | 104 676           | 8 723                             |

Dans chaque fichier, les identifiants de parties sont renseignés et chacun apparaît sur 12 lignes. Cela décrit les exports observés ; ce n’est pas une règle à imposer aveuglément à de futurs formats. Les lignes ne sont pas des rencontres distinctes : elles comprennent les joueurs et les équipes.

SHA-256 des fichiers téléchargés deux fois :

- **2026** : `a019f706e3df09fabd64830e4315d84f56a824bd6e585faa15504ab948e24d00`.
- **2014** : `d72e733ce890f95b2ff58eba7470827e6806ee9773f13341b559e403f290bea0`.

Ces SHA-256 sont calculés localement. Le checksum de transport fourni par Google concerne le ZIP ; aucune récupération de `md5Checksum` individuel via l’API Drive authentifiée n’a été réalisée.

### Limites de contenu découvertes après récupération complète

Le CSV 2026 contient **1 512 lignes déclarées `partial`** par la source. Il contient également **648 lignes avec `year=2027`**, bien que leurs dates observées soient en 2026 ; un exemple concerne la ligue LIT, split Winter, le 28 août 2026. L’année du fichier, la date et le champ de saison `year` ne doivent donc pas être confondus ni corrigés automatiquement. Le dernier timestamp du champ `date` du CSV 2026 est `2026-09-15 09:47:51` ; son fuseau n’a pas été confirmé par cet audit.

Le succès du téléchargement ne prouve ni l’exhaustivité des compétitions mondiales ni l’exactitude de chaque statistique. Les champs incomplets et la provenance doivent être conservés lors d’un import.

## Périmètre et provenance

- Le dépôt ne contenait aucune intégration Oracle’s Elixir lors de l’inspection initiale. Le frontend, les fixtures et les contrats existants restent inchangés.
- La [page officielle de téléchargement](https://oracleselixir.com/tools/downloads) sert une application JavaScript. Son bundle public, `main.4629d2d3.js`, contient le lien vers le dossier ci-dessous. Le bundle a été examiné comme texte, sans exécuter son code.
- Dossier publié : [OE Public Match Data](https://drive.google.com/drive/folders/1gLSw0RLjBbtaNy0dgnGQDAZOHIgCe-HH), identifiant `1gLSw0RLjBbtaNy0dgnGQDAZOHIgCe-HH`.
- Le HTML public du dossier expose **13 fichiers annuels, de 2014 à 2026**. Ce constat décrit le listing observé, pas une couverture exhaustive des compétitions, rencontres ou statistiques.
- Les accès de test n’utilisent ni compte Google connecté, ni clé API, ni cookies de connexion personnels. `gdown` 6.1.0, déjà installé, a été exécuté avec `use_cookies=False`. Aucune dépendance n’a été installée.

### Inventaire observé

Tous les noms suivent le format `ANNÉE_LoL_esports_match_data_from_OraclesElixir.csv`. Les identifiants proviennent du dossier public ; ils ne doivent pas devenir une liste fermée dans une future intégration.

| Année | Identifiant Drive                   |
| ----- | ----------------------------------- |
| 2014  | `12syQsRH2QnKrQZTQQ6G5zyVeTG2pAYvu` |
| 2015  | `1qyckLuw0-hJM8XqFhlV9l1xAbr3H78T_` |
| 2016  | `1muyfpaIqk8_0BFkgLCWXDGNgWSXoPBwG` |
| 2017  | `11fx3nNjSYB0X8vKxLAbYOrS2Bu6avm9A` |
| 2018  | `1GsNetJQOMx0QJ6_FN8M1kwGvU_GPPcPZ` |
| 2019  | `11eKtScnZcpfZcD3w3UrD7nnpfLHvj9_t` |
| 2020  | `1dlSIczXShnv1vIfGNvBjgk-thMKA5j7d` |
| 2021  | `1fzwTTz77hcnYjOnO9ONeoPrkWCoOSecA` |
| 2022  | `1EHmptHyzY8owv0BAcNKtkQpMwfkURwRy` |
| 2023  | `1XXk2LO0CsNADBB1LRGOV5rUpyZdEZ8s2` |
| 2024  | `1IjIEhLc9n8eLKeY-yh_YigKVWbhgGBsN` |
| 2025  | `1v6LRphp2kYciU4SXp0PCjEMuev1bDejc` |
| 2026  | `1hnpbrUpBMS1TZI7IovfpKeZfWJH1Aptm` |

Les réponses partielles annoncent **70 070 300 octets** pour 2026 et `Last-Modified: Tue, 15 Sep 2026 13:05:02 GMT`. Pour 2014 : **8 178 893 octets**, modification le 8 juin 2026 à 22:53:28 UTC. Une ancienne saison peut donc avoir été réécrite récemment : ne pas supposer ses fichiers immuables.

## Essais individuels et partiels — chemins qui ont échoué

Dans ce tableau, « quota » signifie une page HTML intitulée **Google Drive - Quota exceeded**, de **2 009 octets**, reçue avec **HTTP 200**. Ce n’est ni un CSV vide ni une réussite.

| Essai                                                            | Résultat observé                                                              | Conclusion                                                                                       |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Lecture du dossier public                                        | HTTP 200, 13 fichiers identifiés                                              | Découverte possible pendant l’audit                                                              |
| Aperçu 2026                                                      | HTML accessible ; navigateur : fichier trop volumineux pour être prévisualisé | L’aperçu ne fournit pas le CSV complet                                                           |
| `drive.google.com/uc?export=download&id=…`, 2026                 | Redirection vers `drive.usercontent.google.com/download`, puis quota          | Téléchargement complet en échec                                                                  |
| Lien `/uc` du domaine `drive.usercontent.google.com`, sans Range | Quota                                                                         | Changer ce point d’entrée ne suffit pas                                                          |
| Téléchargement avec `confirm=t`                                  | Quota                                                                         | La confirmation ne résout pas le blocage observé                                                 |
| `gdown` 6.1.0, fichier 2026                                      | `FileURLRetrievalError`, message de quota                                     | Aucun fichier complet récupéré                                                                   |
| Bouton « Télécharger » dans l’aperçu Drive, navigateur anonyme   | Nouvelle page « Le quota autorisé a été atteint »                             | Échec également par le parcours utilisateur                                                      |
| Téléchargement complet du fichier 2014                           | Quota                                                                         | L’échec ne concerne pas uniquement l’année courante                                              |
| API v3 `files.get?alt=media`, sans clé ni OAuth                  | HTTP 403 : clé API valide manquante                                           | Authentification du projet nécessaire ; **le comportement avec un projet dédié reste non testé** |

### Piste Range : réussite partielle, insuffisante

Les requêtes suivantes ont réussi via le lien `/uc` de `drive.usercontent.google.com`, avec un en-tête HTTP `Range` :

| Plage 2026 demandée | Statut | Octets reçus |
| ------------------- | ------ | ------------ |
| `0-4095`            | 206    | 4 096        |
| `35000000-35065535` | 206    | 65 536       |
| `70066204-70070299` | 206    | 4 096        |

Pour ces trois réponses, les offsets, tailles et taille totale dans `Content-Range` sont cohérents. Le premier fragment contient **165 colonnes distinctes**, dont `gameid`, `datacompleteness`, `league`, `date`, `participantid`, `playerid`, `teamid` et `result`.

Cependant, les requêtes couvrant tout le fichier, les premiers 8 Mio, 1 Mio et 64 Kio, ainsi qu’une autre plage de 256 Kio ont renvoyé la page de quota. La demande du reste du fichier `4096-70070299`, avec `If-Range` basé sur la date observée, a également échoué. Le lien `drive.google.com/uc` avec `Range: bytes=0-4095` a lui aussi échoué.

Lors de la première série, **73 728 octets distincts du fichier 2026 avaient été récupérés par Range**, avec de grands trous entre les fragments. Lors de la seconde série, deux fragments consécutifs de 32 Kio ont réussi, mais le bloc suivant, commençant à l’octet 65 536, a renvoyé le quota. Aucun assemblage complet par Range n’a donc été réalisé. Les trois fragments de la première série correspondent exactement aux mêmes plages du CSV complet ensuite récupéré par ZIP.

La [documentation Google sur les téléchargements](https://developers.google.com/workspace/drive/api/guides/manage-downloads) décrit `Range` pour les téléchargements partiels via l’API. Elle ne garantit pas la suppression des quotas. Les essais des liens Web ci-dessus ne valident pas l’API authentifiée.

### Preuves compactes

Empreintes SHA-256 calculées localement, à titre de traçabilité des observations :

| Réponse                                              | SHA-256                                                            |
| ---------------------------------------------------- | ------------------------------------------------------------------ |
| Première page quota 2026, 2 009 octets, 16:26:43 UTC | `8e403bfafc4f8f19482faa5df93c692d160c0034d8d898bbb8659905991c85b8` |
| Fragment 2026 `0-4095`                               | `f9075624669995c2bc5b3f914eb17868fd680a001d647f7c1c0a476f1dc5a757` |
| Fragment 2026 `35000000-35065535`                    | `13c4e0979851d7cf6991d9452c503a420fafeae9acb247bebd311ec30b930bf6` |
| Fragment 2026 `70066204-70070299`                    | `354af1cfb5d31d109d0aec5a99f7f9cb1864808eb453933adf1591a7b48eebc9` |

Ces empreintes sont calculées localement. Leur correspondance avec les mêmes plages du CSV obtenu par ZIP a été vérifiée. Les réponses brutes temporaires sont supprimées après l’audit.

## Portée du résultat et limites de disponibilité

**Les 13 fichiers visibles ont bien été récupérés intégralement.** La méthode ZIP a réussi sur deux exports distincts pendant la même session. Elle résout le blocage rencontré aujourd’hui ; son fonctionnement permanent, sa capacité sous forte charge et la stabilité du parcours navigateur n’ont pas été éprouvés sur la durée.

Deux contraintes distinctes existent : les quotas du projet/utilisateur API et les restrictions de téléchargement du fichier partagé. Le blocage effectivement rencontré est celui du lien public ; il intervient sans consommation d’un projet API personnel.

La [documentation des limites Drive](https://developers.google.com/workspace/drive/api/guides/limits), mise à jour le 11 septembre 2026, annonce des quotas par projet, par utilisateur et sur les volumes. Elle mentionne aussi des contrôles supplémentaires du backend. Elle recommande d’espacer progressivement les nouvelles tentatives et précise qu’une hausse de quota n’est pas garantie. Une clé API personnelle permet d’identifier le projet ; elle ne constitue pas une exemption générale.

Le [projet officiel gdown](https://github.com/wkentaro/gdown#faq) reconnaît les restrictions liées au nombre d’accès à un même fichier. Une session connectée peut aider dans certains cas. Son expiration, les restrictions du fichier et l’absence d’engagement de disponibilité empêchent d’en faire une garantie permanente.

Les copies dans un autre Drive, les sessions Google connectées et l’API avec identifiants n’ont pas été testées ici. Leur efficacité n’est donc pas affirmée. Un miroir reste dépendant de la réussite de ses mises à jour, même lorsqu’elles utilisent le ZIP. La page d’erreur du téléchargement individuel évoque une attente pouvant atteindre 24 heures ; ce n’est pas une échéance de rétablissement garantie.

## Architecture recommandée pour une future intégration

### 1. Acquisition indépendante du frontend

Un seul collecteur côté serveur, hors du chemin des requêtes utilisateur. **Le chemin d’acquisition validé est l’export ZIP groupé piloté dans un navigateur anonyme**, suivi du téléchargement HTTP de l’archive produite. Le frontend lit les données importées depuis notre stockage.

Découvrir les CSV depuis le dossier, sélectionner les fichiers nécessaires et vérifier l’inventaire extrait. Préférer les noms et rôles accessibles du parcours aux classes CSS générées. Les sélecteurs et le comportement sur des dossiers plus grands que les 13 fichiers observés devront être testés avant industrialisation.

Une API Drive avec projet dédié est une option complémentaire pour le suivi des métadonnées. Google documente le listing public avec une clé API et la [ressource File](https://developers.google.com/workspace/drive/api/reference/rest/v3/files) expose notamment `id`, `size`, `modifiedTime`, `version` et `md5Checksum`. Ce chemin authentifié n’a pas été validé dans l’audit et n’est pas nécessaire à la réussite ZIP constatée. [Listing public via API](https://developers.google.com/workspace/drive/api/guides/search-files#list_files_in_a_public_folder).

Proposition initiale : vérifier les versions toutes les six heures, cadence à ajuster au besoin de fraîcheur, puis exporter les fichiers modifiés. Pour un seul fichier, ajouter un petit CSV compagnon afin de déclencher l’export groupé testé. Au volume mesuré, quatre archives 2026 + 2014 représentent environ **91 Mo par jour**, hors reprises et changements historiques. C’est un dimensionnement proposé, pas une fréquence de publication constatée. Continuer à surveiller les anciennes saisons, qui peuvent être corrigées.

### 2. Validation avant publication

Télécharger l’archive générée dans un fichier temporaire, vérifier sa longueur, comparer son MD5 avec `x-goog-hash` lorsqu’il est présent, puis vérifier les CRC des entrées et l’inventaire attendu. Extraire uniquement les fichiers prévus dans une zone dédiée en rejetant les chemins sortant de cette zone. Lire les CSV jusqu’à la fin et conserver une empreinte et une provenance par fichier. Ne publier aucune archive incomplète comme un succès.

Vérifier le statut et le contenu réel : un HTTP 200 ou une extension ne suffisent pas. Rejeter les pages HTML et les exports qui omettent des fichiers. Les 165 colonnes observées sont une version de schéma à suivre, pas une constante universelle à supposer pour tous les exports.

En cas de téléchargement interrompu, ne reprendre une archive que si son serveur accepte la reprise et que son identité est inchangée ; ce scénario reste à tester. Ne jamais ajouter aveuglément une réponse 200 à un fichier partiel. Contrôler aussi les modifications des fichiers source pendant la génération du ZIP et exporter de nouveau si nécessaire. Publier ensuite une version validée de façon atomique, en conservant la précédente.

### 3. Gestion des indisponibilités

Sur 429 ou erreur de débit transitoire : attente progressive avec aléa, respect de `Retry-After` lorsqu’il est fourni et nombre de tentatives borné. Sur blocage du fichier : suspendre les tentatives rapprochées et conserver la dernière version validée. Sur refus de permission ou disparition : signaler la cause sans boucle de retry aveugle. Les [erreurs Drive](https://developers.google.com/workspace/drive/api/guides/handle-errors) doivent être distinguées par leur raison, pas uniquement leur statut HTTP.

Exposer la date d’acquisition et la version réellement utilisées, sans présenter des données anciennes comme actuelles. Si aucun fichier validé n’a encore été acquis, signaler l’indisponibilité. Cela reste compatible avec l’absence de bascule silencieuse vers des mocks imposée au projet.

### 4. Indépendance réelle à l’acquisition

Si la fraîcheur doit rester assurée même pendant un quota Drive, obtenir du producteur un export versionné par un canal indépendant de Drive, accompagné de checksums et d’un engagement de service adapté. Un stockage propre résout la dépendance des lecteurs à Google ; un accord de livraison indépendant traite la dépendance à Google lors de l’acquisition. Même cette architecture ne permet pas de promettre une disponibilité absolue.

### Critères de validation restants

Avant de qualifier un futur collecteur de prêt :

- Industrialiser le parcours ZIP validé et ses contrôles, avec délais bornés, détection des erreurs et observabilité. La récupération intégrale des 13 CSV ainsi que la répétition 2014/2026 sont déjà validées par cet audit.
- Vérifier la pagination du listing et la détection d’un fichier ajouté, renommé, remplacé ou corrigé.
- Tester interruption réseau, reprise, réponse HTML 200, corruption, changement distant pendant transfert et restriction de téléchargement, sans écraser une version valide.
- Vérifier qu’un quota simulé laisse les données acquises disponibles et rend leur ancienneté observable.
- Mesurer le taux de réussite et le délai de mise à jour sur une durée représentative. Une réussite ponctuelle ne permet pas d’affirmer 100 % de disponibilité future.

Ces critères ne sont pas présentés comme déjà validés : aucun collecteur de production n’est livré par cet audit.

## Conditions d’utilisation pertinentes pour Metiquo

La page Oracle’s Elixir rattache l’utilisation des statistiques aux politiques de Riot. La [politique générale Riot](https://developer.riotgames.com/policies/general) comporte une restriction sur les fonctionnalités de paris. Son application au périmètre d’analyse de values de Metiquo doit être clarifiée avant exploitation : l’accès public aux CSV ne suffit pas à établir l’autorisation d’usage du produit. Aucune conclusion juridique générale n’est tirée ici.

## Vérifications et nettoyage

- **Première série : 7 tests temporaires réussis**, exécutés sur les réponses individuelles et partielles réellement reçues. Ils vérifient notamment le faux succès HTTP 200 et les fichiers incomplets ; ils n’établissaient pas une impossibilité de téléchargement groupé.
- **Seconde série : 2 exports ZIP réussis**, inventaire complet des 13 CSV, checksum Google des deux archives vérifié, CRC de chaque entrée vérifié, lecture intégrale de 1 223 472 lignes sans erreur de largeur, aucun identifiant de partie vide et égalité SHA-256 de 2014/2026 entre les exports. Les trois fragments initiaux correspondent au CSV 2026 complet.
- **`npm run check` réussi** : TypeScript, ESLint, 21 tests du projet et build de production.
- Parcours individuel et groupé vérifiés dans le navigateur anonyme. Aucun parcours de l’application modifié ; la matrice clair/sombre et responsive de Metiquo n’est pas applicable à cet audit documentaire.
- Le dossier temporaire de l’audit, les scripts de test et les données téléchargées sont supprimés après consignation des résultats. Seule la documentation de l’audit est conservée.
