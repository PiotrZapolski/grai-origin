# Front GRAI ORIGIN: Next.js 14 built and served in production.
#
# The build context is the `web/` directory (see docker-compose.yml).
#
# Three stages, so the final image carries neither the npm cache nor the
# dev packages (typescript, tailwind, vitest) needed only for the build.
#
# We serve via `next start`, not standalone mode: standalone mode requires
# an `output` entry in next.config.mjs, and that file belongs to the
# application code, not to the deployment.

# --- deps: install dependencies ---------------------------------------------
FROM node:22-alpine AS deps
WORKDIR /app
# There is no package-lock.json in the repo, so `npm ci` has nothing to work from.
COPY package.json ./
RUN npm install --no-audit --no-fund

# --- build: compile the application -----------------------------------------
FROM node:22-alpine AS build
WORKDIR /app

# NEXT_PUBLIC_* is injected into the client bundle at BUILD time, not startup.
# An empty value is the default from web/lib/api.ts, i.e. calls relative to
# the same origin. Caddy serves front and API under one host, so that's the
# intended setup; only set it when the API stands at a different address.
ARG NEXT_PUBLIC_API_BASE=""
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE} \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

COPY --from=deps /app/node_modules ./node_modules
COPY . .
# The public/ directory is optional in Next, but the COPY in the runtime
# stage requires it to exist. We create an empty one if it's missing.
RUN mkdir -p public && npm run build \
    && npm prune --omit=dev

# --- runner: the production server itself -----------------------------------
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/.next ./.next
COPY --from=build --chown=node:node /app/public ./public
COPY --from=build --chown=node:node /app/package.json ./package.json
COPY --from=build --chown=node:node /app/next.config.mjs ./next.config.mjs

USER node
EXPOSE 3000
CMD ["node_modules/.bin/next", "start"]
