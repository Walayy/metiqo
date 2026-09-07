# Sécurité du MVP

## Exposition et AUTH_MODE

La configuration initiale autorise `AUTH_MODE=disabled` uniquement avec
`APP_PUBLISH_HOST=127.0.0.1` et `APP_PUBLIC_ORIGIN=http://localhost:3000`.
Les autres adresses loopback IPv4/IPv6 sont acceptées. Les interfaces génériques
`0.0.0.0` et `::`, les adresses publiques, link-local et de réseau partagé, ainsi
que les noms DNS arbitraires, sont refusés sans authentification.

Une adresse privée nécessite un réseau explicitement déclaré, par exemple :

```text
AUTH_MODE=disabled
APP_PUBLISH_HOST=192.168.10.4
APP_PUBLIC_ORIGIN=http://192.168.10.4:3000
AUTH_PRIVATE_NETWORKS=["192.168.10.0/24"]
```

Les réseaux déclarés doivent être des sous-réseaux de `10.0.0.0/8`,
`172.16.0.0/12`, `192.168.0.0/16` ou `fc00::/7`. La configuration refuse une plage
globale ou réservée. L'adresse de publication et celle de l'origine navigateur
doivent toutes deux être locales ou appartenir à un réseau déclaré. Aucun test
DNS ne permet de déclarer implicitement un hostname privé. L'origine doit être
une origine HTTP/HTTPS, sans identifiants, chemin, query ni fragment.

Compose utilise `APP_PUBLISH_HOST` pour les ports API, web et gateway et transmet
cette même valeur à la validation Python. Une configuration invalide empêche le
démarrage de l'API et du worker ; les dépendances de santé empêchent le démarrage
normal du web et du gateway. Les sockets internes des conteneurs continuent
d'écouter sur leur réseau Docker ; cette adresse interne est distincte de la
publication sur l'hôte. Le gateway utilise la même `APP_PUBLIC_ORIGIN`, en HTTPS
avec son autorité locale persistée ; les appareils clients doivent lui faire confiance.

Hors Compose, appliquer la même adresse de publication au serveur ou reverse proxy
effectivement démarré. Une redirection de ports/NAT ou un tunnel externe n'est pas
détectable par la configuration applicative ; il doit être déclaré avec l'origine
et l'adresse d'exposition correspondantes. Ne pas conserver une déclaration
loopback pour une application rendue accessible depuis un réseau public.

`AUTH_MODE=owner` exige une session sur les lectures privées et les mutations.
HTTPS est obligatoire hors loopback, y compris sur un réseau privé. L'API protège
directement ses routes ; le proxy Next transmet uniquement le cookie Owner.

Les tests couvrent la configuration, sa réévaluation par la fabrique API, le
refus d'un vrai démarrage du serveur API et la correspondance entre adresses publiées
et paramètres validés dans Compose.

## Bootstrap et sessions Owner

Appliquer les migrations, puis créer le compte unique depuis un terminal privé :

```sh
uv run --frozen oe auth bootstrap-owner --username owner
```

Le mot de passe est saisi deux fois sans écho, jamais en argument de commande.
Le minimum est 15 caractères, le maximum 1024 octets UTF-8. Pour un lancement
automatisé, `--password-file /run/secrets/owner_password` lit un fichier serveur
protégé ; ne pas créer ce fichier dans le dépôt. Le bootstrap refuse un deuxième
compte. Il peut précéder l'activation de `AUTH_MODE=owner`.

Les mots de passe utilisent Argon2id via `argon2-cffi==25.1.0`, bibliothèque
maintenue, avec ses paramètres par défaut (64 Mio, 3 passes, parallélisme 4).
Un login réussi réévalue le besoin de rehash. Voir la
[politique de paramètres officielle](https://argon2-cffi.readthedocs.io/en/stable/parameters.html).
Seules les empreintes sont stockées ; elles sont exclues des références d'audit.

La session contient 256 bits aléatoires. Le serveur conserve seulement son SHA-256 ;
le navigateur reçoit un cookie HTTP-only, SameSite=Lax, Path=/, sans Domain et
Secure sous HTTPS (`__Host-metiquo_owner`). Le cookie HTTP `metiquo_owner` est
réservé au loopback. Aucune valeur de session n'est renvoyée dans le JSON.
La connexion renouvelle la session précédente ; la déconnexion la révoque.

La politique par défaut expire après 30 minutes sans activité ou 12 heures
absolues, et effectue une rotation après 15 minutes. La rotation conserve
l'expiration absolue. Le cookie précédent dispose de 10 secondes pour les requêtes
déjà simultanées ; une seule rotation peut gagner. Les réglages
`AUTH_SESSION_IDLE_SECONDS`, `AUTH_SESSION_ABSOLUTE_SECONDS`,
`AUTH_SESSION_ROTATION_SECONDS` et `AUTH_SESSION_GRACE_SECONDS` sont validés.

```sh
uv run --frozen oe auth reset-password --username owner
```

La réinitialisation invalide toutes les sessions actives. Les connexions, échecs,
rotations, déconnexions et réinitialisations sont audités sans secrets. Les actions
connectées utilisent l'identité serveur `owner:<uuid>` dans l'audit, même si le
client fournit un autre acteur. L'historique révoqué ne peut être réactivé ni
supprimé par les commandes applicatives.

La preuve navigateur utilise un compte de fixture dans une base de test et couvre
bootstrap CLI, login erroné, login réussi, lecture protégée et déconnexion via Next.
Les protections HTTP ci-dessous complètent les sessions avant le gate P8.

## Frontières HTTP

Les mutations navigateur exigent l'origine exacte `APP_PUBLIC_ORIGIN` et
`X-Metiquo-CSRF: 1`, y compris pour login/logout. Les origines absentes ou `null`
sont refusées en mode Owner ; `Sec-Fetch-Site: cross-site` et `same-site` sont
refusés sur mutation. Un script d'un autre site ne peut pas ajouter cet en-tête
sans preflight ; aucun CORS externe n'est ouvert. Le proxy transmet ces en-têtes,
sans en fabriquer. Le mode disabled local conserve les appels serveur sans
métadonnées navigateur ; les requêtes avec Origin ou Fetch Metadata passent les
mêmes contrôles. Cette approche AJAX et le contrôle d'origine suivent les
[recommandations CSRF OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

Ouvrir exactement l'origine configurée : `localhost` et `127.0.0.1` représentent
deux origines différentes. Pour le gateway livré, déclarer
`APP_PUBLIC_ORIGIN=https://localhost:8443` et utiliser cette URL. Le proxy Next
n'accepte que les chemins `/api/v1/...` vers son backend serveur fixé.
API et proxy limitent les corps de mutation à 64 Kio, y compris avec un transfert
en plusieurs morceaux sans Content-Length. Pydantic refuse les champs inconnus
et les types invalides sans répéter le contenu de la requête dans les erreurs.

Les connexions disposent de 5 tentatives par minute et de 20 par quart d'heure ;
les autres mutations disposent de 60 tentatives par minute. Ce sont des fenêtres
fixes UTC, avec budgets globaux pour l'unique Owner : changer d'IP, de nom saisi
ou de cookie ne crée pas de nouveau budget. Les tentatives refusées consomment
le budget, et les réponses 429 portent Retry-After. Trois compteurs au maximum
sont partagés et mis à jour atomiquement en PostgreSQL en mode Owner ; un
redémarrage ne les réinitialise pas. Le mode disabled local utilise des compteurs
en mémoire. Un dépassement ne bloque pas les lectures de la session déjà ouverte.

Les réponses API portent nosniff, DENY, Referrer-Policy, Permissions-Policy,
Cache-Control no-store et une CSP fermée pour le JSON. HTTPS ajoute HSTS un an.
Le contrat reste disponible en JSON OpenAPI ; les pages de documentation
interactives utilisant des scripts CDN ne sont pas exposées par l'API.
Les erreurs inattendues deviennent un Problem Details générique ; les erreurs SQL
deviennent 503, sans stack, paramètres SQL, cookie ni mot de passe dans la réponse.

Next génère un nonce aléatoire de 256 bits pour chaque rendu dynamique, remplace
tout nonce fourni par le client et le transmet au script du thème. La CSP des
scripts utilise ce nonce et strict-dynamic, sans unsafe-inline ni unsafe-eval en
production. Les styles inline restent autorisés pour les composants et le thème ;
les objets, frames et destinations de formulaires externes sont interdits.
Le rendu dynamique et l'application du nonce suivent la
[documentation CSP de Next.js](https://nextjs.org/docs/app/guides/content-security-policy).
Les tests Chromium vérifient les nonces, le thème, la navigation et les mutations
permises/refusées, sans erreur console ou d'hydratation dans ce parcours.

## Secrets et conteneurs

`DATABASE_URL_FILE` et `OE_GOOGLE_DRIVE_BEARER_FILE` chargent une valeur UTF-8 depuis
un fichier serveur absolu, lisible, non vide et limité à 16 Kio. Chaque variable
est mutuellement exclusive avec sa variante contenant directement la valeur.
Les valeurs chargées deviennent des SecretStr et n'apparaissent ni dans le JSON
de configuration ni dans les erreurs de validation. La convention est compatible
avec les fichiers montés par Docker secrets ou un gestionnaire de secrets.

La surcharge `docker-compose.production.yml` utilise deux fichiers privés :

- `POSTGRES_PASSWORD_SECRET_FILE` : mot de passe PostgreSQL.
- `DATABASE_URL_SECRET_FILE` : DSN complet utilisant ce même mot de passe et le
  hostname interne `postgres`.

Ces variables contiennent des **chemins**, jamais les valeurs. Placer les fichiers
hors dépôt ou dans `.secrets/` avec les droits de lecture du seul opérateur et des
services concernés. Les secrets Compose sont des fichiers montés par service,
pas un coffre chiffré sur l'hôte ; protéger aussi le disque et les sauvegardes.
Voir le [modèle Docker Compose](https://docs.docker.com/compose/how-tos/use-secrets/).
Le worker peut recevoir le fichier OAuth optionnel par un montage distinct ; le
web et le gateway ne reçoivent aucun secret backend. Aucun credential bookmaker
n'est demandé ou chargé par le MVP.

```sh
docker compose -f docker-compose.yml -f docker-compose.production.yml config --quiet
```

La surcharge impose Owner, transmet les DSN par fichier, enlève le mode PostgreSQL
trust et configure SCRAM pour une base neuve. Seul le gateway publie un port ;
API, web et PostgreSQL restent internes. Définir `APP_PUBLIC_ORIGIN` en HTTPS et
adapter le certificat du gateway à cette origine. Sur une base déjà initialisée,
les options initdb ne modifient pas automatiquement le mot de passe ni pg_hba :
l'opérateur doit appliquer leur migration contrôlée avant de la déclarer prête.

API et worker s'exécutent avec l'UID 10001, le web avec 1000 et PostgreSQL avec son
utilisateur postgres. Les services persistants de production n'ont aucune
capacité Linux supplémentaire et utilisent no-new-privileges. Leurs racines sont
readonly ; les écritures vont aux volumes de données et tmpfs requis. L'init
éphémère des volumes reste root, sans réseau, pour attribuer leurs propriétaires.
L'API lit raw/modèles/quarantaine en readonly ; seul le worker les écrit.
Les fichiers `.env`, `.secrets`, clés privées et journaux sont exclus du contexte
de construction Docker. Les corps raw Oracle's Elixir sont publics ; les secrets
et cookies ne sont pas ajoutés aux payloads métier. Les sauvegardes externes
incluant les données privées sont chiffrées selon `docs/backups.md`.

Le test d'image vérifie l'UID, CapEff nul, no-new-privileges, le montage du secret
en lecture seule et le refus des écritures dans l'application/raw. Une instance
PostgreSQL éphémère issue de la surcharge démarre sans root, refuse une connexion
TCP sans mot de passe et accepte le secret monté ; ses volumes de test sont supprimés.
Le vrai bundle Next est construit avec deux secrets serveur sentinelles ; les
chunks publics et les logs de build sont contrôlés pour leur absence.

`make scan-secrets` utilise Gitleaks 8.30.1 (`GITLEAKS_BINARY` si absent du PATH).
Il scanne une copie des fichiers suivis et des sources non ignorées présentes,
puis tout l'historique Git local. Les rapports sont intégralement expurgés dans
`data/security/`. Un secret synthétique prouve que le scanner retourne un échec.
Deux UUID déterministes du fichier `docs/examples/paper-gate-fixture.json` sont
les seuls faux positifs exclus : valeur exacte **et** chemin exact, pour la seule
règle generic-api-key. Aucun dossier de code ni commit n'est exclu du scan.
L'installation reproductible et l'exécution CI de ces scans relèvent de SEC-005.
