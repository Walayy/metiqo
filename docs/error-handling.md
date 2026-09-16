# Erreurs et reprise

Périmètre produit du 16 septembre 2026. Les écrans sont déclenchés par la navigation ou les erreurs réelles des requêtes ; aucune route de démonstration `/423` ou `/429` n’est publiée. Les mêmes composants fonctionnent avec l’API et les fixtures esport. L’authentification et l’administration utilisent toujours l’API réelle.

## Parcours

| Situation                                        | Réponse dans l’interface                             | Suite proposée                                                                                     |
| ------------------------------------------------ | ---------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Chemin inconnu ou `view` inconnu                 | 404 dédiée, thème et marque conservés                | Retour aux values                                                                                  |
| Détail de rencontre absent                       | 404 dans la modale de détail                         | Retour aux résultats, filtres conservés                                                            |
| 401, session absente ou expirée en Admin         | Connexion nécessaire                                 | Ouvre la modale email dans la vue demandée, ou retour aux values                                   |
| 403, droits insuffisants                         | Espace réservé                                       | Retour aux values ; aucune suggestion de contourner le contrôle                                    |
| 423 après vérification de l’email                | Compte suspendu                                      | Explication de la réactivation par un administrateur ; aucun faux délai ni lien de support inventé |
| 429                                              | Pause et décompte si `Retry-After` est présent       | Nouvelle tentative manuelle après échéance ; aucun renvoi automatique du code                      |
| 408/504 ou timeout du navigateur                 | Délai dépassé                                        | Réessayer manuellement                                                                             |
| 500/502/503                                      | Service indisponible                                 | Réessayer, avec attente si le serveur fournit un délai pour 503                                    |
| Coupure réseau                                   | Connexion interrompue                                | Vérifier la connexion et réessayer                                                                 |
| JSON invalide ou contrat Zod non conforme        | Données incomplètes                                  | Aucune présentation de chiffres non fiables ; réessayer                                            |
| 400/422 dans un formulaire                       | Retour de champ français, espace réservé             | Corriger les données ; le formulaire reste en place                                                |
| 409 en administration                            | Message métier contextuel                            | Actualiser les données / rouvrir le formulaire avant une nouvelle modification                     |
| 410/413 si renvoyés par l’API                    | Contenu retiré / demande trop volumineuse            | Retour aux values ; les erreurs de mutation restent contextualisées                                |
| Exception de rendu React                         | Écran de repli indépendant des données               | Recharger ou revenir aux values                                                                    |
| Échec des modules JavaScript ou démarrage > 15 s | Repli HTML autonome, utilisable sans CSS applicative | Recharger ou revenir aux values                                                                    |
| JavaScript désactivé                             | Explication HTML sans spinner permanent              | Activer JavaScript puis recharger                                                                  |

Les erreurs de service dans les formulaires remplacent temporairement leur contenu par un état explicite. Les saisies restent en mémoire tant que la modale reste ouverte ; « Reprendre » ne soumet rien. Fermer la modale garde le comportement existant de remise à zéro du formulaire. Une écriture dont la réponse a été perdue peut avoir été reçue : un lancement de script propose de vérifier l’historique avant de renouveler la demande.

## Transport et limites

- `lib/http.ts` conserve le statut HTTP même si une passerelle renvoie du HTML. Le contenu JSON des succès est validé par Zod. Les annulations de requêtes abandonnées ne sont pas converties en erreurs réseau.
- Timeout de 20 secondes. Au plus une nouvelle tentative automatique de lecture pour une panne réseau, un timeout ou un statut 5xx sans délai serveur ; aucune pour les interdictions, 429, les contrats invalides ou une écriture.
- `Retry-After` accepte des secondes ou une date HTTP. L’en-tête `Date`, lorsqu’il est disponible, corrige le décalage de l’horloge du navigateur. Le délai est un minimum avant un nouvel essai, pas une promesse de rétablissement.
- Les échéances 429/503 sont mémorisées par origine, chemin et méthode, sans email ni paramètre de recherche, dans `sessionStorage` et en mémoire. Les appels sont refusés localement jusqu’à échéance, même après F5. Ce mécanisme d’interface ne remplace jamais la limite persistante du backend. Un nouvel onglet ou une horloge modifiée ne contourne pas le contrôle serveur.
- Sans en-tête valide, aucun compte à rebours arbitraire. Le message demande de patienter ; l’utilisateur choisit quand réessayer. Les sondages périodiques de session et des scripts s’arrêtent après une erreur ; le retour du focus peut vérifier la session, en respectant toujours le délai serveur.
- Aucun basculement automatique en mock. Pas de redirection vers une URL reçue du serveur et pas de transmission de jeton dans un lien.

## Serveur et confidentialité

Le compte suspendu renvoie 423 après validation du code et consommation du challenge, ou pour une session existante valide dont le compte est suspendu. Une suspension administrative révoque normalement les sessions ; celles-ci deviennent donc anonymes (401 pour l’accès Admin), sans divulguer de statut à un détenteur de cookie révoqué. Une simple demande de code ne révèle ni existence ni suspension.

Les erreurs SQL renvoient un JSON 503 sûr, `Retry-After: 30` et `Cache-Control: no-store`. Les exceptions inattendues renvoient un JSON 500 générique, sans corps de demande ni paramètres SQL. Nginx conserve les réponses applicatives et transforme ses propres erreurs de passerelle 502/504 en JSON 503 avec le même délai. Les limites réelles 429 de l’authentification restent celles de PostgreSQL.

Dans Docker, un chemin frontend inexistant sert l’application avec un véritable statut HTTP 404, qui affiche ensuite son écran dédié. Les ressources `/assets/` absentes restent des 404 et ne reçoivent pas le HTML de la SPA. La racine et les paramètres de requête sont évalués côté navigateur : un `view` inconnu affiche 404 mais la réponse initiale de `/` reste HTTP 200. Le serveur de développement Vite conserve son fallback SPA HTTP 200.

## Accessibilité et vérifications

Titres explicites, focus sur l’explication, liens et boutons fonctionnels, zone d’attente sans annonce vocale à chaque seconde (seul le passage à l’état prêt est annoncé). Cibles de 44 px, clair/sombre, mobile/tablette/desktop, aucune animation de hauteur. Les erreurs en modale utilisent Radix, Escape, confinement et retour du focus. Les formulaires courts et les modales longues conservent leur défilement.

Tests : analyse des deux formats de délai, horloge décalée, persistance du blocage, fin d’attente, HTML d’erreur, coupure réseau, annulation, réponses invalides, choix d’action, routes inconnues ; backend : réponses sûres, limites persistantes et suspension révélée seulement après preuve. Les erreurs techniques du navigateur sont injectées par un proxy de vérification local isolé, absent du code de production et de MSW.

Références consultées le 16 septembre 2026 : [Retry-After (MDN)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After), [423 Locked (MDN)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/423), [Nginx error_page](https://nginx.org/en/docs/http/ngx_http_core_module.html#error_page). Le code 423 vient de WebDAV ; son utilisation pour une suspension est une convention explicite du contrat Metiquo.
