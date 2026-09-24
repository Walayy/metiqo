#!/usr/bin/env bash
set -euo pipefail

cd /opt/projects/metiqo
compose=(docker compose --env-file .env.docker -f compose.yaml -f compose.prod.yaml)
backup_dir=/var/backups/metiquo
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 700 "$backup_dir"
db_tmp="$(mktemp "$backup_dir/.${stamp}.db.XXXXXX")"
artifacts_tmp="$(mktemp "$backup_dir/.${stamp}.artifacts.XXXXXX")"
workers_stopped=false

cleanup() {
  status=$?
  trap - EXIT
  if "$workers_stopped"; then
    "${compose[@]}" start worker stake-worker settlement-worker >/dev/null || status=1
  fi
  if (( status != 0 )); then
    rm -f "$db_tmp" "$artifacts_tmp"
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ -z "$("${compose[@]}" ps -q db)" ]]; then
  echo 'Production database is not running.' >&2
  exit 1
fi
if [[ -n "$(docker ps -q --filter label=com.docker.compose.project=metiquo-stack --filter label=com.docker.compose.oneoff=True)" ]]; then
  echo 'A manual Compose job is running; retry the backup after it finishes.' >&2
  exit 1
fi

workers_stopped=true
"${compose[@]}" stop -t 45 worker stake-worker settlement-worker >/dev/null
"${compose[@]}" exec -T db pg_dump -U metiquo -d metiquo -Fc > "$db_tmp"
"${compose[@]}" exec -T db pg_restore --list < "$db_tmp" >/dev/null
docker run --rm --network none -v metiquo-stack_artifacts:/data:ro \
  --entrypoint tar metiquo-worker:local -czf - -C /data . > "$artifacts_tmp"
tar -tzf "$artifacts_tmp" >/dev/null

mv "$db_tmp" "$backup_dir/metiquo-$stamp.dump"
mv "$artifacts_tmp" "$backup_dir/metiquo-$stamp-artifacts.tar.gz"
chmod 600 "$backup_dir/metiquo-$stamp.dump" "$backup_dir/metiquo-$stamp-artifacts.tar.gz"
find "$backup_dir" -maxdepth 1 -type f -name 'metiquo-*.dump' -mtime +14 -delete
find "$backup_dir" -maxdepth 1 -type f -name 'metiquo-*-artifacts.tar.gz' -mtime +14 -delete
echo "Production backup created at $stamp UTC"
