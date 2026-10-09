# Site Guard AI web app: Next.js standalone server, run as a non-root user.
# Build: docker build -t siteguard-web frontend   (or: docker compose up --build web)
# Run:   docker run -p 3000:3000 -e SITEGUARD_API_URL=http://api:8000 siteguard-web
# The session cookie is marked Secure in this image (NODE_ENV=production): serve it over HTTPS, or use
# http://localhost, which browsers treat as a secure context.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# `npm run build` also copies the static assets into .next/standalone (scripts/copy-standalone-assets.mjs).
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S -g 10001 siteguard && adduser -S -D -H -u 10001 -G siteguard siteguard
COPY --from=build --chown=siteguard:siteguard /app/.next/standalone ./
USER siteguard
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/api/health > /dev/null || exit 1
CMD ["node", "server.js"]
