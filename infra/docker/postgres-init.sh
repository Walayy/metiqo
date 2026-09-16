#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=api_password="$METIQUO_API_PASSWORD" --set=worker_password="$METIQUO_WORKER_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE metiquo_api LOGIN PASSWORD %L', :'api_password') \gexec
SELECT format('CREATE ROLE metiquo_worker LOGIN PASSWORD %L', :'worker_password') \gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO metiquo_api, metiquo_worker;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO metiquo_api;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO metiquo_worker;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO metiquo_worker;
SQL
