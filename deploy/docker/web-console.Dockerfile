FROM node:20-alpine AS build

WORKDIR /app/apps/web-console

COPY apps/web-console/package.json apps/web-console/package-lock.json ./
RUN npm ci

COPY apps/web-console ./
RUN npm run build

FROM nginx:1.27-alpine

COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/web-console/dist /usr/share/nginx/html

EXPOSE 80
