FROM node:22.20.0-bookworm-slim
WORKDIR /workspace
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/contracts/package.json packages/contracts/package.json
RUN npm ci
COPY apps/web apps/web
COPY packages/contracts packages/contracts
RUN mkdir -p apps/web/.next && chown -R node:node /workspace
USER node
CMD ["npm", "run", "dev", "--workspace", "@actiondesk/web"]
