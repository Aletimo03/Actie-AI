# The UI image: Vite builds the static files, unprivileged nginx serves them (port 8080)
# and proxies /api to the API. No Node at run time. Build from frontend/:
#   docker build -t actie-web frontend
# Base images pinned by digest, at least two weeks old: node 26.11.1, nginx 1.30.5 (stable).

FROM node:26.11.1-bookworm-slim@sha256:86f07bc9c5dce4578cf37e5a418b7bfc7f817cda25cde66e2b66e95ed86c4567 AS build
WORKDIR /app
# Dependencies first (lockfile, cooldown and no install scripts from .npmrc): cached
# until package-lock.json changes.
COPY package.json package-lock.json .npmrc ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.30.5-alpine@sha256:56b8272e43a0525f67aed68d1e0794a712d10e3e45a563e118e9a77c817e6f86
COPY nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
ENV API_UPSTREAM=http://api:8000
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:8080/healthz || exit 1
