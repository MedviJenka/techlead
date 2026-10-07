# NOT-PRODUCTION: dev-only image that runs the Vite dev server (used by docker compose).
# A production image needs a multi-stage build (npm run build -> static files served by nginx or similar).
FROM node:22-alpine

WORKDIR /srv
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
