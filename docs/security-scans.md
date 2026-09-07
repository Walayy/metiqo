# Audits de sécurité du MVP

Exécuter `make docker-build`, puis `make scan-security` sur les sources à livrer.
Le job CI « Gate sécurité » exécute les mêmes commandes sans tolérance d'échec.
La protection de la branche de release doit exiger ce job ; sa configuration sur
GitHub se vérifie au gate de release. Une exécution locale ne prouve pas que la CI
distante a exécuté le commit.

## Périmètre et preuves

Gitleaks 8.30.1 analyse les fichiers présents et toutes les références Git locales.
En CI, le checkout récupère l'historique complet. Ses rapports sont expurgés.
Pip-audit 2.10.1 analyse l'export verrouillé avec empreintes de toutes les dépendances
Python, développement inclus. Pnpm 11.25.0 analyse le verrou frontend, développement
inclus. Trivy 0.74.0 analyse les dépendances OS et applicatives des images API,
worker, web, PostgreSQL et gateway réellement construites et identifiées par leur
SHA Docker. Le profil MinIO optionnel est hors du MVP filesystem ; son activation
demande d'ajouter son image au gate avant déploiement.

L'installateur ne lance que les archives officielles dont le SHA-256 correspond à
`config/security-tools.json`. Chaque exécution crée un répertoire inédit dans
`data/security`, avec les rapports JSON et leur empreinte, les versions des outils,
la date de la base Trivy, le commit et l'empreinte des sources. Une base Trivy de
plus de 48 heures, un scanner indisponible, un inventaire incomplet ou une image ou
des sources modifiées pendant le scan font échouer la commande. La CI conserve
les rapports pendant 14 jours, même en cas de refus.

## Politique bloquante

- Toute vulnérabilité critique non acceptée bloque la release, même sans correctif.
- Toute vulnérabilité Python bloque : pip-audit ne fournit pas une sévérité
  homogène permettant de minorer une alerte.
- Les vulnérabilités frontend élevées bloquent également.
- Les vulnérabilités élevées des images disposant d'une version corrigée bloquent.
  Les élevées sans correctif, les moyennes, faibles et sévérités OS inconnues restent
  explicitement dans `reported` et doivent être examinées à chaque release.
- Toute fuite de secret bloque. Aucun mécanisme d'exception de vulnérabilité ne
  peut accepter une fuite ou une erreur de scanner.

Le fichier `config/security-policy.json` ne contient actuellement aucune exception.
Une exception exige l'approbation de l'Owner et une modification relue de ce fichier :
écosystème, identifiant de vulnérabilité, package et version exacts, `approvedBy`,
`approvedAt`, `expiresAt`, `reason` et `evidence`. Le document `evidence` doit exister
sous `docs/`, décrire l'exposition, les preuves et les mesures compensatoires.
Sa durée ne peut excéder 30 jours ; une version différente ou une exception expirée
ne couvre pas l'alerte. Une correction disponible est préférée à une exception.
Les tests de politique injectent une alerte critique synthétique et vérifient le
code de sortie 1 ; un rapport absent produit le code 2.

## Mises à jour contrôlées

Examiner les avis upstream et relancer les audits avant chaque release et chaque
mise à jour. Créer un changement dédié, épingler les versions et empreintes,
examiner les verrous puis exécuter les tests concernés et le gate complet.
Ne pas utiliser de correction automatique qui modifie les contraintes sans revue.
Les exceptions sont réexaminées à chaque changement, jamais renouvelées tacitement.
Un audit réussi n'est valable que pour les sources, images et base d'avis consignées.

La correction initiale remplace `js-yaml` 4.2.0 par 4.3.1 dans le générateur de
contrats (avis `GHSA-52cp-r559-cp3m` et `GHSA-5p4m-2wfm-xmqj`). Les contrats régénérés
restent identiques. Les images ont été réduites et reconstruites :

- Python 3.13.14 sur Debian 13 conserve les clients PostgreSQL 18 natifs et leurs
  enregistrements de packages pour le scan, mais retire Perl et uv du runtime.
  Le PATH privilégie `/usr/lib/postgresql/18/bin` : les wrappers de maintenance
  Debian qui dépendent de Perl ne sont pas utilisables. Les dépendances `dpkg` de ces
  wrappers sont donc volontairement incomplètes ; une mise à jour se fait par
  reconstruction, jamais par apt dans le conteneur final. Les sauvegardes et
  restaurations réelles doivent passer après chaque changement de cette image.
- Node 24.20.0 utilise Alpine et le serveur Next standalone ; npm, Corepack et Yarn
  sont retirés du runtime. Les dépendances natives sont construites sur la même base.
- PostgreSQL 18.4 utilise Alpine à jour. Le basculement d'utilisateur de son
  entrypoint emploie `su-exec` natif à la place d'un `gosu` compilé avec un ancien Go.
- Caddy 2.11.4 est recompilé avec Go 1.26.6 et les correctifs crypto/net/text/grpc.
  `infra/gateway/build/go.mod` et `go.sum` verrouillent le graphe complet ; le build
  vérifie les modules et interdit toute modification du verrou. Les dépendances
  restent détectables dans le binaire Go par Trivy.

## Sources

- [Gitleaks et sa politique de détection](https://github.com/gitleaks/gitleaks).
- [Trivy 0.74.0](https://github.com/aquasecurity/trivy/releases/tag/v0.74.0).
- [Pip-audit](https://pypi.org/project/pip-audit/).
- [Pnpm audit](https://pnpm.io/cli/audit).
- [Avis js-yaml sur les fusions](https://github.com/advisories/GHSA-52cp-r559-cp3m).
- [Avis js-yaml sur les mappings ordonnés](https://github.com/advisories/GHSA-5p4m-2wfm-xmqj).
- [Versions Caddy](https://github.com/caddyserver/caddy/releases).
- [Versions Go](https://go.dev/dl/).
