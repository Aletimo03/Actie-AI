# The UI image: Vite builds the static files, unprivileged nginx serves them (port 8080)
# and proxies /api to the API. No Node at run time. Build from frontend/:
#   docker build -t actie-web frontend
# Base images pinned by digest, at least two weeks old: node 26.11.1, nginx 1.30.5 (stable).

FROM node:26.12.0-bookworm-slim@sha256:742a0fe7320e09e0321222b68165e6ac731d30470e7ea7f98f9bfc3a6e1034fe AS build
WORKDIR /app
# Dependencies first (lockfile, cooldown and no install scripts from .npmrc): cached
# until package-lock.json changes.
COPY package.json package-lock.json .npmrc ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
# Readable by nginx's unprivileged user, whatever the permissions on the machine that builds.
RUN npm run build && chmod -R a+rX dist

FROM nginxinc/nginx-unprivileged:1.30.6-alpine@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03
COPY nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
ENV API_UPSTREAM=http://api:8000 REAL_IP_FROM=127.0.0.1/32
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:8080/healthz || exit 1
