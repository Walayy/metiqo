# Authentification par email

Périmètre produit du 15 septembre 2026 : connexion et inscription réelles, sans mot de passe, dans une modale Radix. Aucune route de connexion, aucun compte bookmaker, aucune donnée d’authentification simulée par MSW. Le nom d’un rôle dans le frontend n’accorde aucun droit.

## Parcours et stockage

Dans la modale, les erreurs de saisie et de serveur apparaissent sous le champ concerné. Le composant UI `FieldFeedback` réserve la hauteur des textes possibles à la largeur et à la police courantes, y compris sur mobile. Aucun ajout de bloc ne déplace le bouton de validation. Validation à la soumission, puis correction pendant la saisie ; erreurs et confirmations annoncées aux lecteurs d’écran. Les champs vides ou codes incomplets ne déclenchent pas d’appel réseau. La transition de 160 ms porte sur l’opacité et une translation de 2 px ; elle est supprimée lorsque la réduction des animations est demandée.

- `POST /api/v1/auth/request-code` normalise l’adresse (espaces externes retirés, casse ignorée, pas de fusion des alias `+` ou des points), génère un code cryptographiquement aléatoire et envoie l’email par SMTP. Adresse existante ou nouvelle : même réponse, même email et même traitement.
- Le challenge conserve seulement le HMAC-SHA256 du code, lié à son UUID et au secret serveur, l’empreinte du cookie de demande, l’expiration et le compteur d’essais. Le navigateur reçoit un cookie HttpOnly de demande et l’UUID public. Un code intercepté dans un autre navigateur ne suffit pas. Une nouvelle demande pour la même adresse remplace le challenge précédent. Demander un code dans un autre onglet du même navigateur remplace aussi le cookie de demande : saisir le dernier code dans la fenêtre correspondante.
- La validation verrouille le challenge en base ; cinq erreurs le rendent inutilisable. La consommation, la création éventuelle de l’utilisateur, la rotation de la session précédente du navigateur et la nouvelle session sont atomiques. Le compte admin précréé doit vérifier sa boîte mail lors de sa première connexion.
- Chaque session possède 32 octets aléatoires ; PostgreSQL ne conserve que son SHA-256. Le cookie a `HttpOnly`, `SameSite=Lax`, `Path=/`, sans `Domain`. Sur HTTPS, `Secure` et le préfixe `__Host-` sont appliqués. Le mode HTTP est limité aux origines loopback et explicitement configuré dans Docker local.
- Session : 30 jours maximum, 7 jours sans activité. `/session` actualise l’activité au plus toutes les cinq minutes. Le frontend vérifie la session chaque minute quand l’onglet est actif et au retour du focus ; les autres onglets sont avertis par BroadcastChannel, sans transmettre de données de session. Le rôle est relu en base. Déconnexion : suppression serveur et expiration des cookies ; les favoris locaux sont conservés.
- Les réponses d’authentification, erreurs comprises, sont `Cache-Control: no-store`. Les erreurs de validation n’incluent pas les données reçues. Aucun code, token ou contenu SMTP n’est journalisé. Aucun token dans le stockage web.

## Protection des écritures et limites

Les trois POST exigent une `Origin` dans la liste explicite et `X-Metiquo-Auth: 1`. Aucune permission CORS ne permet de poster depuis un autre site. Nginx limite les corps à 8 Kio et remplace `X-Real-IP` ; l’API n’est pas publiée directement dans Compose. `METIQUO_AUTH_TRUST_PROXY=true` convient uniquement à ce réseau privé derrière le proxy. Avec Python exposé directement, garder `false` : les en-têtes IP clients sont ignorés.

Les compteurs PostgreSQL sont partagés entre processus et survivent aux redémarrages. Fenêtres démarrant au premier appel : un envoi par email / 60 secondes, cinq demandes par email / heure, trente demandes par IP / heure et cent demandes globales / minute. Vérification : soixante demandes par IP / dix minutes, avec au plus cinq erreurs sur chaque challenge. Les demandes refusées par une autre limite peuvent consommer les compteurs non saturés, de façon conservatrice. Les 429 donnent `Retry-After`. Une panne SMTP ne crée ni compte ni nouveau challenge valide ; les compteurs persistent et l’ancien challenge reste utilisable s’il était encore valide.

Les lignes expirées des challenges, des limites et des sessions sont purgées à la prochaine demande de code. Les sessions expirées par inactivité sont aussi retirées à leur prochaine lecture ; sinon elles restent au plus jusqu’à leur expiration absolue. Aucun historique esport n’est supprimé.

## Base et rôle administrateur

Migration `0002` : extension de `app_users`, tables `auth_challenges`, `auth_sessions`, `auth_rate_limits`, index et provisionnement de `admin@metiquo.fr`. Les identités externes historiques restent conservées avec un email nullable. Les nouvelles inscriptions utilisent l’émetteur interne `metiquo:email`.

L’API peut créer les colonnes d’identité nécessaires et marquer l’email vérifié ; elle ne peut ni insérer ni modifier `role` (défaut PostgreSQL `user`). L’administrateur est créé par le propriétaire de la base lors de la migration. Le worker perd tous les privilèges sur les quatre tables d’authentification. Les droits du catalogue restent en lecture pour l’API. Les futures opérations réservées devront contrôler le rôle au serveur : aucun endpoint d’administration n’existe dans cette livraison.

## Configuration

| Variable                                          | Usage                                                                                                                                                            |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `METIQUO_AUTH_SECRET`                             | Obligatoire pour l’API, minimum 32 caractères ; `docker:init` génère 32 octets aléatoires en hexadécimal. Ne jamais exposer via Vite.                            |
| `METIQUO_AUTH_ORIGINS`                            | Tableau JSON d’origines exactes, sans chemin ni slash final. Docker inclut les loopbacks aux ports 8080 et 5173. Ajuster pour tout port ou domaine personnalisé. |
| `METIQUO_AUTH_COOKIE_SECURE`                      | Défaut Python `true` ; Docker local `false`, accepté seulement pour des origines loopback.                                                                       |
| `METIQUO_AUTH_TRUST_PROXY`                        | Défaut Python `false`, Docker privé `true`. Ne pas faire confiance aux en-têtes d’une API directement exposée.                                                   |
| `METIQUO_SMTP_HOST` / `METIQUO_SMTP_PORT`         | Python `127.0.0.1:1025` ; Docker `mailpit:1025`. Délai SMTP 10 secondes.                                                                                         |
| `METIQUO_SMTP_SECURITY`                           | `none` pour Mailpit local, `starttls` ou `tls` pour un fournisseur. Certificats vérifiés.                                                                        |
| `METIQUO_SMTP_FROM`                               | Adresse d’envoi, défaut `connexion@metiquo.fr`. Utiliser un domaine vérifié par le fournisseur réel.                                                             |
| `METIQUO_SMTP_USERNAME` / `METIQUO_SMTP_PASSWORD` | Facultatifs, ensemble ; TLS requis. À transmettre explicitement dans l’environnement API, par exemple via un override Compose privé.                             |
| `MAILPIT_PORT`                                    | Interface HTTP locale : 8025.                                                                                                                                    |
| `SMTP_DEV_PORT` / `DB_DEV_PORT`                   | Override `compose.dev.yaml` : SMTP 1025 et PostgreSQL 54329, uniquement sur loopback.                                                                            |

`npm run docker:init` préserve les valeurs existantes et ajoute seulement le secret auth manquant. Un champ déjà présent mais vide doit être rempli explicitement ; l’API refuse une clé absente/courte au démarrage. Une rotation du secret invalide les challenges et remet les limites dans un nouvel espace ; elle n’invalide pas les sessions SHA-256 existantes. Leur révocation reste en base.

### Développement

Le plus simple : `npm run docker:up`, puis `npm run dev`. Le proxy Vite utilise `http://127.0.0.1:8080` ; son URL peut être remplacée par `METIQUO_DEV_API_TARGET` au démarrage de Vite. L’authentification utilise toujours `/api/v1/auth` sur la même origine, même si `VITE_API_BASE_URL` pointe ailleurs pour les données esport.

Pour Python local : démarrer `db` et `mailpit` avec les deux fichiers Compose, configurer `METIQUO_DATABASE_URL`, `METIQUO_AUTH_SECRET`, `METIQUO_AUTH_ORIGINS` (incluant `http://127.0.0.1:5173`) et `METIQUO_AUTH_COOKIE_SECURE=false`, puis `uv run alembic upgrade head` et `uv run uvicorn metiquo_api.main:create_app --factory`. Définir `METIQUO_DEV_API_TARGET=http://127.0.0.1:8000` pour Vite. `npm run preview` partage ce proxy ; ajouter explicitement son origine au port 4173 pour tester la connexion sur ce port.

### Mailpit et remplacement

Mailpit v1.31.1 est épinglé par digest. SMTP interne 1025, interface loopback 8025, sans relais vers Internet. Les emails contiennent une version texte et HTML sans code dans l’objet. Stockage en mémoire, limité à 500 messages et 24 heures, aucune authentification de l’interface locale. Un fournisseur SMTP réel devra remplacer ces réglages avant toute publication ; configurer HTTPS, origines, `Secure`, domaine expéditeur, SPF/DKIM/DMARC et délivrabilité. Mailpit donne accès à tous les codes locaux : garder son interface privée.

Sources consultées le 15 septembre 2026 : [Docker Mailpit](https://mailpit.axllent.org/docs/install/docker/), [SMTP Mailpit](https://mailpit.axllent.org/docs/configuration/smtp/), [sessions OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html). La connexion email dépend de la sécurité de la boîte mail ; elle ne constitue pas une authentification multifacteur. Aucun envoi externe ni déploiement n’a été effectué.
