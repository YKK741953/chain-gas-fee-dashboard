# Build stage
FROM node:20.15.1-alpine AS build
WORKDIR /app

COPY web/package.json ./package.json
RUN npm install

COPY web .
RUN npm run build

# Runtime stage
FROM nginx:1.27-alpine
WORKDIR /usr/share/nginx/html
COPY --from=build /app/dist .
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
