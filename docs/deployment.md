# Déploiement de production

Le dépôt historique est `/opt/projects/metiqo`. Le déploiement public utilise
`compose.yaml` et `compose.prod.yaml`, Traefik du serveur sur le réseau Docker
`public-proxy`, PostgreSQL privé et pgAdmin accessible par tunnel SSH. Un
conteneur distinct fournit Chrome avec affichage virtuel au collecteur Stake ;
il utilise le même rôle SQL restreint que les autres workers. Les protections
de refus et délais de la source restent applicables.
Un challenge présenté par Stake sur l'IP du VPS interrompt la collecte et
déclenche la pause prévue ; il ne faut pas le contourner.
Nginx fait confiance à `X-Forwarded-For` seulement depuis le sous-réseau
Traefik `172.18.0.0/16` de ce VPS. Si le réseau `public-proxy` est recréé avec
un autre sous-réseau, adapter `infra/docker/nginx.conf` avant le redéploiement.

## Configuration locale au serveur

Le fichier `/opt/projects/metiqo/.env.docker` reste sur le serveur (mode `0600`,
ignoré par Git). Exécuter `npm run docker:init` pour créer les secrets aléatoires,
puis renseigner les variables de production :

```dotenv
METIQUO_AUTH_ORIGINS=["https://metiquo.com","https://www.metiquo.com"]
METIQUO_AUTH_COOKIE_SECURE=true
METIQUO_SMTP_HOST=smtp.resend.com
METIQUO_SMTP_PORT=465
METIQUO_SMTP_SECURITY=tls
METIQUO_SMTP_FROM=connexion@metiquo.com
METIQUO_SMTP_USERNAME=resend
METIQUO_SMTP_PASSWORD=<clé API Resend>
VITE_DATA_MODE=api
```

L'override de production exige ces paramètres SMTP et construit le frontend en
mode API. Le mode local garde Mailpit et ses réglages distincts. La clé Resend
n'entre jamais dans Git ni dans les arguments de construction du frontend.

Commande manuelle de déploiement, depuis le serveur et sur `master` :

```sh
cd /opt/projects/metiqo
docker compose --env-file .env.docker -f compose.yaml -f compose.prod.yaml up -d --build --wait
```

`docker compose ... ps` et `curl -f http://127.0.0.1:8080/health` permettent de
contrôler les services. Les migrations Alembic précèdent l'API. Les volumes sont
persistants ; ne pas utiliser `down -v` pour une mise à jour. Le premier accès
public HTTPS attend que les enregistrements A du domaine pointent vers le VPS.

## GitHub Actions

Seul un `push` sur `master` déclenche le workflow. Les tâches qualité, Docker,
migrations et interface doivent réussir avant le déploiement. Le job `deploy`
appelle, via SSH, le script versionné `scripts/deploy-production.sh` avec le SHA
contrôlé. La clé
publique dédiée est restreinte à sa copie stable
`/usr/local/sbin/metiquo-deploy` dans `authorized_keys` ; la clé
du serveur est épinglée dans `.github/metiquo_known_hosts`. Le script refuse un
arbre de travail modifié et un SHA dépassé par un nouveau `master`.

Dans **Settings → Secrets and variables → Actions** du dépôt GitHub, créer le
secret `METIQUO_DEPLOY_SSH_KEY` avec le contenu complet de
`/root/.ssh/metiquo_github_actions` sur le serveur. Ce fichier privé ne doit
jamais être ajouté au dépôt. Dans **Settings → Environments**, créer
`production` et le limiter à la branche `master`. Une fois le secret ajouté,
relancer le workflow `master` si son déploiement a échoué avant configuration.
La branche `develop` n'active aucun workflow.

## Domaine et email

Chez Hostinger, remplacer l'enregistrement A `@` actuel par `195.35.0.154`.
Le CNAME `www` existant peut continuer à pointer vers `metiquo.com`. Supprimer
les éventuels AAAA pointant ailleurs. Traefik demande ensuite les
certificats Let's Encrypt par challenge HTTP. Conserver le port 80 ouvert pour
ce challenge et la redirection HTTPS.

Le domaine d'envoi `metiquo.com` doit être vérifié dans Resend. Ajouter dans la
zone Hostinger les enregistrements DKIM, SPF et MX de **l'hôte `send`** affichés
par Resend, plus l'éventuel CNAME `rsend`. Le MX `send.metiquo.com` est destiné
au chemin de retour de l'envoi ; il ne remplace pas un MX de réception sur `@`.
Une fois les DNS propagés, lancer la vérification dans Resend, puis demander un
code de connexion avec sa propre adresse et confirmer sa livraison dans Resend.

## pgAdmin et accès SQL

pgAdmin écoute uniquement sur le serveur à `127.0.0.1:5050`. Depuis un poste
local, ouvrir un tunnel :

```sh
ssh -N -L 5050:127.0.0.1:5050 root@195.35.0.154
```

Ouvrir ensuite `http://127.0.0.1:5050` ; l'identifiant de pgAdmin est la valeur
de `PGADMIN_DEFAULT_EMAIL`, son mot de passe est `PGADMIN_DEFAULT_PASSWORD` dans
`.env.docker`. Le serveur **Metiquo — PostgreSQL** est préconfiguré ; saisir
`POSTGRES_PASSWORD` pour le rôle SQL `metiquo`. La base et pgAdmin restent privés.

Le compte administrateur de l'application se connecte indépendamment, par code
email. Son rôle SQL `admin` ne contourne jamais la vérification de sa boîte.
