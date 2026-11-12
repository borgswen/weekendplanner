FROM node:22-bookworm-slim

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund
COPY src ./src
COPY data ./data

ENV TZ=Europe/Amsterdam \
    NODE_ENV=production \
    POORT=8089

USER node
EXPOSE 8089
HEALTHCHECK CMD node -e "fetch('http://localhost:8089/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "src/server.js"]
