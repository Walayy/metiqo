#!/usr/bin/env bash
set -euo pipefail

# This script is also the forced command for the GitHub Actions SSH key.
request="${SSH_ORIGINAL_COMMAND:-${1:-}}"
if [[ ! "$request" =~ ^deploy\ [0-9a-f]{40}$ ]]; then
  echo 'Expected: deploy <40-character master commit SHA>' >&2
  exit 2
fi
sha="${request#deploy }"

exec 9>/var/lock/metiquo-deploy.lock
flock -w 300 9
cd /opt/projects/metiqo

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo 'Deployment checkout has local changes; refusing to overwrite them.' >&2
  exit 1
fi

git fetch --quiet origin master
git switch --quiet master
if [[ "$(git rev-parse origin/master)" != "$sha" ]]; then
  echo 'A newer master commit is available; skipping this stale deployment.'
  exit 0
fi
git merge --ff-only "$sha"

scripts/backup-production.sh
docker compose --env-file .env.docker -f compose.yaml -f compose.prod.yaml up -d --build --wait --wait-timeout 240
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8080/health >/dev/null
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8080/api/docs >/dev/null
install -m 755 scripts/deploy-production.sh /usr/local/sbin/metiquo-deploy.next
mv -f /usr/local/sbin/metiquo-deploy.next /usr/local/sbin/metiquo-deploy
echo "Deployed master ${sha}"
