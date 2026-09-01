# Build context is the repository root — this image needs the pnpm workspace, not
# just apps/web.
FROM node:22-slim

ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    NEXT_TELEMETRY_DISABLED=1

RUN corepack enable

WORKDIR /app

# Manifests first so the install layer survives source edits.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/
COPY packages/schema/package.json ./packages/schema/

RUN pnpm install --frozen-lockfile

COPY . .

EXPOSE 3000

CMD ["pnpm", "--filter", "@codonlab/web", "dev"]
