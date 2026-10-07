# syntax=docker/dockerfile:1
#
# CylinGuard dashboard: built once, then served as static files.
#
# Multi-stage on purpose. `npm run dev` must never be what serves production - it ships the
# dev server, source maps and a websocket for hot reload, and it is slow. The build stage
# produces dist/ and is then discarded; the runtime image is nginx plus static assets, with
# no Node and no node_modules in it.

# ---------- build ----------
FROM node:22-alpine AS build

WORKDIR /app

# Lockfile first: `npm ci` installs exactly what is pinned and fails if package.json and the
# lockfile disagree, which is what makes the image reproducible. Its own layer, so editing a
# component does not reinstall 400 packages.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

# Baked in at build time: Vite inlines VITE_* into the bundle, so these cannot be changed by
# setting an environment variable on the running container. Both default to empty, which
# makes the app use same-origin relative paths - which is what the nginx in front of it
# serves. Override only when the API lives on another origin.
ARG VITE_API_URL=""
ARG VITE_WS_URL=""
ENV VITE_API_URL=$VITE_API_URL \
    VITE_WS_URL=$VITE_WS_URL

RUN npm run build

# ---------- runtime ----------
FROM nginx:1.27-alpine AS runtime

# Serves the SPA on port 80 inside the network. The edge nginx service proxies to it; this
# config only has to handle static files and the history-API fallback.
COPY docker/nginx-spa.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
