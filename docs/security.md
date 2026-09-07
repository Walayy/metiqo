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
publication sur l'hôte. Le gateway livré est configuré pour localhost : un
changement d'origine nécessite également sa configuration TLS correspondante.

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
Les protections HTTP complémentaires sont suivies par SEC-003 avant le gate P8.
