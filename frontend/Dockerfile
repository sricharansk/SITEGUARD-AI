# Site Guard AI web app: production image. Next.js standalone server, non-root, health check on /api/health,
# configuration only from the environment (SITEGUARD_API_URL, SITEGUARD_ALLOWED_ORIGINS, SITEGUARD_API_TIMEOUT_MS,
# PORT, HOSTNAME; see frontend/README.md). Every setting is read by the server at request time, so one image runs
# in any environment; nothing secret is baked in (.dockerignore keeps .env* out of the build context).
#
# Build: docker build -t siteguard-web frontend   (or: docker compose up --build web)
# Run:   docker run -p 3000:3000 -e SITEGUARD_API_URL=http://api:8000 siteguard-web
#
# The session cookie is marked Secure in this image (NODE_ENV=production): serve it over HTTPS, or use
# http://localhost, which browsers treat as a secure context.
# Behind a TLS-inspecting proxy, pass its CA bundle as a build secret; it is mounted only while npm runs and is
# never written to a layer:  docker build --secret id=build_ca,src=/path/to/ca-bundle.pem ...

# Pinned by digest so rebuilds use the same base; bump the tag and digest together (docs/DEPLOYMENT.md).
ARG NODE_IMAGE=node:22.23.3-alpine3.24@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402

FROM ${NODE_IMAGE} AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    npm ci --no-audit --no-fund

FROM ${NODE_IMAGE} AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# `npm run build` also copies the static assets into .next/standalone (scripts/copy-standalone-assets.mjs).
RUN npm run build

FROM ${NODE_IMAGE} AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
# The standalone server needs only node: drop npm, npx, corepack and yarn from the runtime image.
RUN rm -rf /usr/local/lib/node_modules /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
      /usr/local/bin/yarn /usr/local/bin/yarnpkg /opt/yarn-* \
    && addgroup -S -g 10001 siteguard \
    && adduser -S -D -H -u 10001 -G siteguard -s /sbin/nologin siteguard
# Server code stays root-owned (read-only for the app user); only the Next.js cache directory is writable.
COPY --from=build /app/.next/standalone ./
RUN mkdir -p .next/cache && chown siteguard:siteguard .next/cache
USER siteguard
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -qO /dev/null http://127.0.0.1:3000/api/health || exit 1
CMD ["node", "server.js"]
