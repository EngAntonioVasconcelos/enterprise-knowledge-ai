# The web app. Stages: deps (locked install), dev (used by the development
# compose, code mounted), build, and production (a small Node server with
# only the built output, the base for deployment in Phase 10).
# Everything runs as the unprivileged "node" user, and the files it writes
# (node_modules, .next) belong to it from the start.
FROM node:24-slim AS deps
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
RUN chown node:node /app
USER node
COPY --chown=node:node package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM deps AS dev
# File changes made on Windows reach the container through a mount that
# does not send change events: watch by polling.
ENV WATCHPACK_POLLING=true
COPY --chown=node:node . .
# The development compose mounts anonymous volumes on node_modules and
# .next; a new volume starts as a copy of the folder here, owner included.
RUN mkdir -p .next
EXPOSE 3000
CMD ["npm", "run", "dev"]

FROM deps AS build
COPY --chown=node:node . .
RUN npm run build

FROM node:24-slim AS production
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
