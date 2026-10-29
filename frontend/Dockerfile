# syntax=docker/dockerfile:1
# Organizador web: the React build served by Nginx, which is also the reverse proxy of the API (/api).
# Used by the `web` service of docker-compose.yml: the only port of the stack exposed on the home network.

# Images pinned by tag and digest, written in each FROM (not in an ARG) so Dependabot can update them.

# ---------------------------------------------------------------------------------------------------------
# node:24.22.0-alpine3.24 (Node 24.22.0, released 2026-10-14). Only builds: nothing of Node ships.
FROM node:24.22.0-alpine3.24@sha256:44fce696f38ba8c987c4db89954051000bbd05ffd8d8659ba15ed4a8602e937f AS build

WORKDIR /app
COPY package.json package-lock.json .npmrc ./
# Exactly the lockfile. No install scripts: none is needed on Linux (fsevents is macOS only) and it keeps
# swagger-ui-dist's telemetry dependency (@scarf/scarf) from running.
RUN npm ci --ignore-scripts --no-audit --no-fund

COPY . .
RUN npm run build

# ---------------------------------------------------------------------------------------------------------
# nginx:1.30.6-alpine3.24 (stable branch; nginx 1.30.6 released 2026-10-14)
FROM nginx:1.30.6-alpine3.24@sha256:47928bf67eb62a1863cb08d9ecb52d3e704304ba614eaee17884204677702951 AS runtime

# Only variables starting with NGINX_ go through envsubst (the templates use many $nginx_variables).
# NGINX_ENTRYPOINT_LOCAL_RESOLVERS: the image exports NGINX_LOCAL_RESOLVERS from /etc/resolv.conf (Docker
# DNS), used to resolve `api` at request time.
ENV NGINX_ENVSUBST_FILTER=^NGINX_ \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1

COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/templates/ /etc/nginx/templates/
COPY nginx/snippets/ /etc/nginx/snippets/
COPY --chmod=0755 nginx/upload-limit.envsh /docker-entrypoint.d/16-upload-limit.envsh
RUN rm -f /etc/nginx/conf.d/default.conf

COPY --from=build /app/dist /usr/share/nginx/html
# Swagger UI for /api/docs (served here, not by a CDN): only the files the docs page loads.
COPY --from=build /app/node_modules/swagger-ui-dist/swagger-ui-bundle.js \
                  /app/node_modules/swagger-ui-dist/swagger-ui.css \
                  /app/node_modules/swagger-ui-dist/favicon-32x32.png \
                  /usr/share/nginx/docs-assets/

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1/"]
