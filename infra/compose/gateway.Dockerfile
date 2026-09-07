FROM golang:1.26.6-alpine@sha256:3889b425f035be855a72fb4755265311293b6d414521f0a519d819df32222d83 AS build
WORKDIR /build
COPY infra/gateway/build/go.mod infra/gateway/build/go.sum ./
RUN go mod download && go mod verify
COPY infra/gateway/build/main.go ./
RUN CGO_ENABLED=0 go build -mod=readonly -trimpath -o /caddy .

FROM caddy:2.11.4-alpine@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648
RUN apk upgrade --no-cache
COPY --from=build /caddy /usr/bin/caddy
