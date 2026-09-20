FROM node:24-bookworm-slim@sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553 AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci --workspace @metiquo/web --include-workspace-root
COPY apps/web apps/web
ARG VITE_DATA_MODE=mock
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_DONATION_URL=
ARG VITE_STAKE_REFERRAL_URL=
ENV VITE_DATA_MODE=$VITE_DATA_MODE VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_DONATION_URL=$VITE_DONATION_URL VITE_STAKE_REFERRAL_URL=$VITE_STAKE_REFERRAL_URL
# The compose overlay supplies VITE_DATA_MODE (mock or api). Use a neutral Vite
# mode so the root package's local mock default cannot override that build arg.
RUN npm run build --workspace @metiquo/web -- --mode production

FROM nginx:stable-alpine@sha256:dc5069ad14f19660b141b21236140b91656bf89bbc3e2417c70ae650cd66104c
COPY infra/docker/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/apps/web/dist /usr/share/nginx/html
USER nginx
EXPOSE 8080
ENTRYPOINT ["nginx", "-g", "daemon off;"]
