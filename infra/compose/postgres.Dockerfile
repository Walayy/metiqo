FROM postgres:18.4-alpine@sha256:9a8afca54e7861fd90fab5fdf4c42477a6b1cb7d293595148e674e0a3181de15

# Preserve the official entrypoint, replacing its privilege switch with Alpine's
# equivalent native tool instead of retaining an obsolete embedded Go runtime.
RUN apk upgrade --no-cache && apk add --no-cache su-exec \
    && rm /usr/local/bin/gosu \
    && sed -i 's/exec gosu postgres/exec su-exec postgres/' /usr/local/bin/docker-entrypoint.sh
